from __future__ import annotations

import asyncio
import socket
from contextlib import suppress
from pathlib import Path
from typing import Any

from pdf2zh_next.high_level import do_translate_async_stream

from .paths import ARTIFACTS_DIR
from .paths import WORKER_POLL_INTERVAL
from .paths import WORKER_STALE_SECONDS
from .schemas import ArtifactKind
from .store import AppStore
from .store import JobBundle
from .store import loads
from .upstream import build_settings_model

WORKER_HEARTBEAT_INTERVAL = 5.0


def _merge_token_usage(total: dict[str, Any], current: dict[str, Any] | None) -> dict[str, Any]:
    current = current or {}
    merged = {**total}
    for section, metrics in current.items():
        section_total = merged.setdefault(
            section,
            {
                "total": 0,
                "prompt": 0,
                "cache_hit_prompt": 0,
                "completion": 0,
            },
        )
        for metric, value in metrics.items():
            section_total[metric] = section_total.get(metric, 0) + (value or 0)
    return merged


async def _translate_file(
    store: AppStore,
    bundle: JobBundle,
    file_row: dict[str, Any],
    file_index: int,
    total_files: int,
    worker_name: str,
) -> tuple[Path | None, Path | None, Path | None, dict[str, Any]]:
    job_id = bundle.job["id"]
    options = loads(bundle.job["options_json"], {})
    output_dir = ARTIFACTS_DIR / job_id / "working" / file_row["id"]
    output_dir.mkdir(parents=True, exist_ok=True)
    settings = build_settings_model(
        bundle.profile_snapshot,
        options,
        output_dir=output_dir,
    )
    settings.basic.input_files = set()

    mono_path = None
    dual_path = None
    glossary_path = None
    token_usage: dict[str, Any] = {}
    loop = asyncio.get_running_loop()
    timeout_seconds = int(bundle.job["timeout_seconds"])
    deadline = loop.time() + timeout_seconds

    async def consume_events():
        nonlocal mono_path, dual_path, glossary_path, token_usage
        async for event in do_translate_async_stream(settings, Path(file_row["storage_path"])):
            if store.is_cancel_requested(job_id):
                raise asyncio.CancelledError()
            event_type = event["type"]
            if event_type in {"progress_start", "progress_update", "progress_end"}:
                file_progress = float(event.get("overall_progress", 0.0))
                overall_progress = ((file_index + (file_progress / 100.0)) / total_files) * 100.0
                stage = event.get("stage", "Translating")
                detail = {
                    "part_index": event.get("part_index"),
                    "total_parts": event.get("total_parts"),
                    "stage_current": event.get("stage_current"),
                    "stage_total": event.get("stage_total"),
                    "file_name": file_row["original_name"],
                    "file_progress": file_progress,
                }
                store.update_job_progress(
                    job_id,
                    round(overall_progress, 2),
                    f"{file_row['original_name']}: {stage}",
                    detail,
                )
            elif event_type == "finish":
                result = event["translate_result"]
                mono_path = getattr(result, "mono_pdf_path", None)
                dual_path = getattr(result, "dual_pdf_path", None)
                glossary_path = getattr(result, "auto_extracted_glossary_path", None)
                token_usage = event.get("token_usage", {})
                return
            elif event_type == "error":
                raise RuntimeError(event.get("error", "Unknown translation error"))

    translate_task = loop.create_task(consume_events())

    try:
        while True:
            if store.is_cancel_requested(job_id):
                translate_task.cancel()
                with suppress(asyncio.CancelledError):
                    await translate_task
                raise asyncio.CancelledError()

            remaining = deadline - loop.time()
            if remaining <= 0:
                translate_task.cancel()
                with suppress(asyncio.CancelledError):
                    await translate_task
                raise TimeoutError()

            store.touch_worker(
                worker_name,
                "busy",
                current_job_id=job_id,
                note=f"Translating {file_row['original_name']}",
            )
            try:
                await asyncio.wait_for(
                    asyncio.shield(translate_task),
                    timeout=min(WORKER_HEARTBEAT_INTERVAL, remaining),
                )
            except asyncio.TimeoutError:
                continue
            if translate_task.done():
                await translate_task
                break
    finally:
        if not translate_task.done():
            translate_task.cancel()
            with suppress(asyncio.CancelledError):
                await translate_task
    return mono_path, dual_path, glossary_path, token_usage


async def process_job(store: AppStore, bundle: JobBundle, worker_name: str) -> None:
    job_id = bundle.job["id"]
    total_files = len(bundle.files)
    aggregate_usage: dict[str, Any] = {}
    failures: list[str] = []

    for file_index, file_row in enumerate(bundle.files):
        if store.is_cancel_requested(job_id):
            store.cancel_job(job_id, "Job cancelled before file start")
            break

        store.mark_file_running(file_row["id"], f"Processing {file_row['original_name']}")
        store.mark_job_running(job_id, f"Processing {file_row['original_name']}")

        try:
            mono_path, dual_path, glossary_path, token_usage = await _translate_file(
                store,
                bundle,
                file_row,
                file_index,
                total_files,
                worker_name,
            )
            aggregate_usage = _merge_token_usage(aggregate_usage, token_usage)

            if mono_path and Path(mono_path).exists():
                store.record_artifact(job_id, file_row["id"], ArtifactKind.MONO_PDF, Path(mono_path))
            if dual_path and Path(dual_path).exists():
                store.record_artifact(job_id, file_row["id"], ArtifactKind.DUAL_PDF, Path(dual_path))
            if glossary_path and Path(glossary_path).exists():
                store.record_artifact(job_id, file_row["id"], ArtifactKind.GLOSSARY, Path(glossary_path))

            store.mark_file_finished(file_row["id"])
            completed_progress = ((file_index + 1) / total_files) * 100.0
            store.update_job_progress(
                job_id,
                round(completed_progress, 2),
                f"Completed {file_row['original_name']}",
                {"file_name": file_row["original_name"]},
            )
            store.append_event(
                job_id,
                "file_completed",
                f"Completed {file_row['original_name']}",
                data={"job_file_id": file_row["id"], "token_usage": token_usage},
            )
        except asyncio.CancelledError:
            store.cancel_job(job_id)
            break
        except TimeoutError:
            message = f"{file_row['original_name']} timed out"
            failures.append(message)
            store.mark_file_failed(file_row["id"], message)
            store.append_event(job_id, "file_failed", message, level="error")
        except Exception as exc:
            message = f"{file_row['original_name']} failed: {exc}"
            failures.append(message)
            store.mark_file_failed(file_row["id"], message)
            store.append_event(job_id, "file_failed", message, level="error")

    current_job = store.get_job(job_id)
    if current_job and current_job.status.value == "cancelled":
        log_path = store.render_log_artifact(job_id)
        store.record_artifact(job_id, None, ArtifactKind.LOG, log_path)
        return

    if failures:
        store.fail_job(job_id, "One or more files failed", "\n".join(failures))
    else:
        store.complete_job(job_id, aggregate_usage)

    log_path = store.render_log_artifact(job_id)
    store.record_artifact(job_id, None, ArtifactKind.LOG, log_path)


async def worker_loop(worker_name: str | None = None) -> None:
    worker_name = worker_name or f"{socket.gethostname()}-worker"
    store = AppStore()
    recovered = store.recover_stale_jobs(WORKER_STALE_SECONDS)
    store.touch_worker(worker_name, "idle", note=f"Recovered {recovered} stale jobs")

    while True:
        bundle = store.claim_next_job(worker_name)
        if bundle is None:
            store.touch_worker(worker_name, "idle")
            await asyncio.sleep(WORKER_POLL_INTERVAL)
            continue

        try:
            await process_job(store, bundle, worker_name)
        except Exception as exc:
            store.fail_job(bundle.job["id"], f"Worker crash: {exc}")
            with suppress(Exception):
                log_path = store.render_log_artifact(bundle.job["id"])
                store.record_artifact(bundle.job["id"], None, ArtifactKind.LOG, log_path)
        finally:
            store.touch_worker(worker_name, "idle")
