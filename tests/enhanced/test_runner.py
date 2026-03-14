from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from pdf2zh_next_enhanced import runner
from pdf2zh_next_enhanced.schemas import ArtifactKind
from pdf2zh_next_enhanced.schemas import JobCreatePayload
from pdf2zh_next_enhanced.schemas import JobStatus
from pdf2zh_next_enhanced.schemas import OpenAIProfileInput
from pdf2zh_next_enhanced.store import AppStore

from .test_store import _make_pdf
from .test_store import _patch_data_paths


def _create_bundle(tmp_path, monkeypatch):
    database_path = _patch_data_paths(tmp_path, monkeypatch)
    monkeypatch.setattr(runner, "ARTIFACTS_DIR", database_path.parent / "artifacts")
    store = AppStore(database_path)
    profile = store.save_provider_profile(
        OpenAIProfileInput(
            name=f"Runner Test {tmp_path.name}",
            model="gpt-5.4",
            api_key="sk-runner-test",
        )
    )
    source_pdf = _make_pdf(tmp_path / "runner.pdf")
    job, _ = store.create_job(JobCreatePayload(profile_id=profile.id), [source_pdf])
    bundle = store.get_job_bundle(job.id)
    return store, job, bundle


def _patch_settings_builder(monkeypatch):
    def fake_build_settings_model(_profile_snapshot, _options, output_dir):
        return SimpleNamespace(
            basic=SimpleNamespace(input_files=set()),
            output_dir=Path(output_dir),
        )

    monkeypatch.setattr(runner, "build_settings_model", fake_build_settings_model)


def test_process_job_records_artifacts_and_completes(tmp_path, monkeypatch):
    store, job, bundle = _create_bundle(tmp_path, monkeypatch)
    _patch_settings_builder(monkeypatch)

    async def fake_do_translate_async_stream(settings, _file_path):
        mono_path = settings.output_dir / "translated.pdf"
        _make_pdf(mono_path)
        yield {
            "type": "progress_update",
            "overall_progress": 50.0,
            "stage": "Translate Paragraphs",
        }
        yield {
            "type": "finish",
            "translate_result": SimpleNamespace(
                mono_pdf_path=mono_path,
                dual_pdf_path=None,
                auto_extracted_glossary_path=None,
            ),
            "token_usage": {
                "main": {
                    "total": 7,
                    "prompt": 5,
                    "cache_hit_prompt": 0,
                    "completion": 2,
                }
            },
        }

    monkeypatch.setattr(runner, "do_translate_async_stream", fake_do_translate_async_stream)

    asyncio.run(runner.process_job(store, bundle, "worker-test"))

    refreshed = store.get_job(job.id)
    assert refreshed is not None
    assert refreshed.status == JobStatus.COMPLETED
    assert refreshed.token_usage["main"]["total"] == 7

    artifacts = store.list_job_artifacts(job.id)
    kinds = {ArtifactKind(artifact["kind"]) for artifact in artifacts}
    assert ArtifactKind.MONO_PDF in kinds
    assert ArtifactKind.LOG in kinds


def test_translate_file_touches_worker_while_waiting(tmp_path, monkeypatch):
    store, job, bundle = _create_bundle(tmp_path, monkeypatch)
    _patch_settings_builder(monkeypatch)
    monkeypatch.setattr(runner, "WORKER_HEARTBEAT_INTERVAL", 0.01)

    heartbeat_calls: list[tuple[str, str | None, str | None]] = []
    original_touch_worker = store.touch_worker

    def touch_worker_spy(worker_name, status, current_job_id=None, note=None):
        heartbeat_calls.append((status, current_job_id, note))
        original_touch_worker(worker_name, status, current_job_id, note)

    monkeypatch.setattr(store, "touch_worker", touch_worker_spy)

    async def fake_do_translate_async_stream(settings, _file_path):
        await asyncio.sleep(0.035)
        mono_path = settings.output_dir / "translated.pdf"
        _make_pdf(mono_path)
        yield {
            "type": "finish",
            "translate_result": SimpleNamespace(
                mono_pdf_path=mono_path,
                dual_pdf_path=None,
                auto_extracted_glossary_path=None,
            ),
            "token_usage": {},
        }

    monkeypatch.setattr(runner, "do_translate_async_stream", fake_do_translate_async_stream)

    mono_path, _, _, _ = asyncio.run(
        runner._translate_file(store, bundle, bundle.files[0], 0, 1, "worker-test")
    )

    assert mono_path is not None
    assert Path(mono_path).exists()
    assert len(heartbeat_calls) >= 2
    assert all(call[0] == "busy" for call in heartbeat_calls)
    assert any(call[1] == job.id for call in heartbeat_calls)


def test_translate_file_stops_on_cancel_request(tmp_path, monkeypatch):
    store, job, bundle = _create_bundle(tmp_path, monkeypatch)
    _patch_settings_builder(monkeypatch)
    monkeypatch.setattr(runner, "WORKER_HEARTBEAT_INTERVAL", 0.01)

    async def fake_do_translate_async_stream(_settings, _file_path):
        await asyncio.sleep(1)
        yield {
            "type": "progress_update",
            "overall_progress": 10.0,
            "stage": "Translate Paragraphs",
        }

    monkeypatch.setattr(runner, "do_translate_async_stream", fake_do_translate_async_stream)

    async def exercise_cancel():
        async def request_cancel():
            await asyncio.sleep(0.03)
            store.request_job_cancel(job.id)

        cancel_task = asyncio.create_task(request_cancel())
        try:
            with pytest.raises(asyncio.CancelledError):
                await runner._translate_file(store, bundle, bundle.files[0], 0, 1, "worker-test")
        finally:
            await cancel_task

    asyncio.run(exercise_cancel())
    assert store.is_cancel_requested(job.id) is True
