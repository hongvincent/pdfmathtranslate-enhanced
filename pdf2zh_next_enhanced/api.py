from __future__ import annotations

import asyncio
import json
import tempfile
import time
from contextlib import suppress
from pathlib import Path
from typing import Annotated
from typing import Any

from fastapi import FastAPI
from fastapi import File
from fastapi import Form
from fastapi import HTTPException
from fastapi import Response
from fastapi import UploadFile
from fastapi.responses import FileResponse
from fastapi.responses import HTMLResponse
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

from . import paths
from .file_validation import UnsupportedInputError
from .file_validation import validate_uploaded_file
from .providers import validate_profile
from .schemas import ArtifactKind
from .schemas import JobCreatePayload
from .schemas import JobOptions
from .schemas import ProviderProfileInput
from .schemas import ProviderProfileRecord
from .schemas import ProviderType
from .store import AppStore


def _provider_label(provider_type: ProviderType) -> str:
    if provider_type == ProviderType.OPENAI:
        return "OpenAI"
    if provider_type == ProviderType.BEDROCK:
        return "Bedrock"
    return provider_type.value


def _output_mode_from_options(options: dict[str, Any]) -> str:
    if options.get("no_dual") and not options.get("no_mono"):
        return "mono"
    if options.get("no_mono") and not options.get("no_dual"):
        return "dual"
    return "both"


def _build_payload_from_form(
    profile_id: str | None,
    source_lang: str | None,
    target_lang: str | None,
    output_mode: str | None,
    pages: str | None,
    qps: int | None,
    save_glossary: bool | None,
) -> JobCreatePayload:
    if not profile_id:
        raise HTTPException(status_code=400, detail="profile_id is required")

    no_mono = False
    no_dual = False
    if output_mode == "dual":
        no_mono = True
    elif output_mode == "mono":
        no_dual = True

    return JobCreatePayload(
        profile_id=profile_id,
        options=JobOptions(
            lang_in=source_lang or "en",
            lang_out=target_lang or "ko",
            pages=pages,
            qps=qps or 4,
            no_mono=no_mono,
            no_dual=no_dual,
            no_auto_extract_glossary=not bool(save_glossary),
            save_auto_extracted_glossary=bool(save_glossary),
        ),
    )
def _serialize_profile(profile: ProviderProfileRecord) -> dict[str, Any]:
    config = profile.config
    payload = {
        "id": profile.id,
        "name": profile.name,
        "provider_type": profile.provider_type.value,
        "provider": _provider_label(profile.provider_type),
        "config": config,
        "has_secret": profile.has_secret,
        "is_default": profile.is_default,
        "validation_status": profile.validation_status,
        "validation_error": profile.validation_error,
        "validated_models": profile.validated_models,
        "created_at": profile.created_at,
        "updated_at": profile.updated_at,
    }
    if profile.provider_type == ProviderType.OPENAI:
        payload.update(
            {
                "model": config.get("model"),
                "snapshot_model": config.get("snapshot_model"),
                "use_snapshot": config.get("use_snapshot"),
                "base_url": config.get("base_url"),
                "reasoning_effort": config.get("reasoning_effort"),
                "temperature": config.get("temperature"),
                "timeout_seconds": config.get("timeout_seconds"),
            }
        )
    elif profile.provider_type == ProviderType.BEDROCK:
        payload.update(
            {
                "region": config.get("region"),
                "model_id": config.get("model_id"),
                "auth_mode": config.get("auth_mode"),
                "profile_name": config.get("profile_name"),
                "temperature": config.get("temperature"),
                "timeout_seconds": config.get("timeout_seconds"),
            }
        )
    return payload


def _serialize_event(event: Any) -> dict[str, Any]:
    if hasattr(event, "model_dump"):
        payload = event.model_dump(mode="json")
        data = payload.pop("data", {})
        return {
            "id": payload.get("id"),
            "type": payload.get("event_type"),
            "level": payload.get("level"),
            "message": payload.get("message"),
            "timestamp": payload.get("created_at"),
            "details": data,
            **data,
        }

    data = event.get("data", {})
    return {
        "id": event.get("id"),
        "job_id": event.get("job_id"),
        "type": event.get("event_type"),
        "level": event.get("level"),
        "message": event.get("message"),
        "timestamp": event.get("created_at"),
        "status": event.get("status"),
        "stage": event.get("current_step"),
        "details": data,
        **data,
    }


def _serialize_artifact(job_id: str, artifact: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": artifact["id"],
        "kind": artifact["kind"],
        "filename": artifact["file_name"],
        "label": artifact["file_name"],
        "url": f"/api/jobs/{job_id}/artifacts/download/{artifact['id']}",
        "size_bytes": artifact["size_bytes"],
        "created_at": artifact["created_at"],
        "job_file_id": artifact.get("job_file_id"),
        "source_file_name": artifact.get("original_name"),
    }


def _serialize_job(store: AppStore, job_id: str, include_details: bool = False) -> dict[str, Any]:
    job = store.get_job(job_id)
    if job is None:
        raise KeyError(job_id)

    bundle = store.get_job_bundle(job_id)
    options = json.loads(bundle.job["options_json"])
    artifacts = store.list_job_artifacts(job_id)
    artifact_map: dict[str | None, list[dict[str, Any]]] = {}
    for artifact in artifacts:
        artifact_map.setdefault(artifact.get("job_file_id"), []).append(artifact)

    payload = {
        "id": job.id,
        "status": job.status.value,
        "profile_id": job.profile_id,
        "profile_name": job.profile_name,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "started_at": job.started_at,
        "finished_at": job.completed_at,
        "completed_at": job.completed_at,
        "error_message": job.error_message,
        "error_details": job.error_details,
        "token_usage": job.token_usage,
        "overall_progress": job.overall_progress,
        "progress": job.overall_progress,
        "current_step": job.current_step,
        "current_stage": job.current_step,
        "duplicate_of": job.duplicate_of,
        "lang_in": options.get("lang_in", "en"),
        "lang_out": options.get("lang_out", "ko"),
        "source_lang": options.get("lang_in", "en"),
        "target_lang": options.get("lang_out", "ko"),
        "pages": options.get("pages"),
        "qps": options.get("qps"),
        "output_mode": _output_mode_from_options(options),
        "save_glossary": bool(
            options.get("save_auto_extracted_glossary")
            and not options.get("no_auto_extract_glossary", True)
        ),
        "artifact_count": len(artifacts),
        "options": options,
        "files": [
            {
                "id": file_record.id,
                "name": file_record.original_name,
                "original_name": file_record.original_name,
                "size_bytes": file_record.size_bytes,
                "page_count": file_record.page_count,
                "status": file_record.status,
                "error_message": file_record.error_message,
                "artifacts": [
                    _serialize_artifact(job_id, artifact)
                    for artifact in artifact_map.get(file_record.id, [])
                ],
            }
            for file_record in job.files
        ],
    }

    if include_details:
        payload["artifacts"] = [_serialize_artifact(job_id, artifact) for artifact in artifacts]
        payload["recent_events"] = [
            _serialize_event(event) for event in store.get_job_events(job_id)
        ]

    return payload


def create_app() -> FastAPI:
    paths.ensure_data_dirs()
    app = FastAPI(title="PDFMathTranslate Enhanced", version="0.1.0")
    app.state.started_at = time.time()
    store = AppStore()

    @app.get("/api/system/health")
    @app.get("/api/health")
    async def system_health():
        health = store.health().model_dump(mode="json")
        health["uptime_seconds"] = int(time.time() - app.state.started_at)
        return health

    @app.get("/api/provider-profiles")
    @app.get("/api/profiles")
    async def list_provider_profiles():
        return [_serialize_profile(profile) for profile in store.list_provider_profiles()]

    @app.post("/api/provider-profiles")
    @app.post("/api/profiles")
    async def create_provider_profile(payload: ProviderProfileInput):
        return _serialize_profile(store.save_provider_profile(payload))

    @app.patch("/api/provider-profiles/{profile_id}")
    @app.patch("/api/profiles/{profile_id}")
    @app.put("/api/provider-profiles/{profile_id}")
    @app.put("/api/profiles/{profile_id}")
    async def update_provider_profile(profile_id: str, payload: ProviderProfileInput):
        if store.get_provider_profile(profile_id) is None:
            raise HTTPException(status_code=404, detail="Profile not found")
        return _serialize_profile(store.save_provider_profile(payload, profile_id=profile_id))

    @app.delete("/api/provider-profiles/{profile_id}", status_code=204)
    @app.delete("/api/profiles/{profile_id}", status_code=204)
    async def delete_provider_profile(profile_id: str):
        try:
            store.delete_provider_profile(profile_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Profile not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return Response(status_code=204)

    @app.post("/api/provider-profiles/{profile_id}/validate")
    @app.post("/api/profiles/{profile_id}/validate")
    async def validate_provider_profile(profile_id: str):
        try:
            profile = store.get_profile_runtime_payload(profile_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Profile not found") from exc
        try:
            result = validate_profile(profile)
        except Exception as exc:
            store.mark_profile_validation(profile_id, False, str(exc), [])
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        store.mark_profile_validation(profile_id, True, result.message, result.validated_models)
        return result.model_dump(mode="json")

    @app.get("/api/jobs")
    async def list_jobs():
        return [_serialize_job(store, job.id) for job in store.list_jobs()]

    @app.get("/api/jobs/{job_id}")
    async def get_job(job_id: str):
        try:
            return _serialize_job(store, job_id, include_details=True)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Job not found") from exc

    @app.post("/api/jobs")
    async def create_job(
        files: Annotated[list[UploadFile], File(...)],
        payload: Annotated[str | None, Form()] = None,
        profile_id: Annotated[str | None, Form()] = None,
        source_lang: Annotated[str | None, Form()] = None,
        target_lang: Annotated[str | None, Form()] = None,
        output_mode: Annotated[str | None, Form()] = None,
        pages: Annotated[str | None, Form()] = None,
        qps: Annotated[int | None, Form()] = None,
        save_glossary: Annotated[bool | None, Form()] = None,
    ):
        if not files:
            raise HTTPException(status_code=400, detail="At least one PDF file is required")

        if payload:
            try:
                parsed_payload = JobCreatePayload.model_validate_json(payload)
            except Exception as exc:
                raise HTTPException(status_code=400, detail=f"Invalid payload: {exc}") from exc
        else:
            parsed_payload = _build_payload_from_form(
                profile_id,
                source_lang,
                target_lang,
                output_mode,
                pages,
                qps,
                save_glossary,
            )

        temp_paths: list[Path] = []
        try:
            for upload in files:
                suffix = Path(upload.filename or "upload.pdf").suffix or ".pdf"
                content = await upload.read()
                try:
                    validate_uploaded_file(upload.filename or "upload", content, upload.content_type)
                except UnsupportedInputError as exc:
                    raise HTTPException(status_code=400, detail=str(exc)) from exc
                with tempfile.NamedTemporaryFile(
                    dir=paths.STATE_DIR,
                    suffix=suffix,
                    delete=False,
                ) as temp_file:
                    temp_file.write(content)
                    temp_paths.append(Path(temp_file.name))
            job, duplicate = store.create_job(parsed_payload, temp_paths)
            return {
                "job": _serialize_job(store, job.id, include_details=True),
                "duplicate": duplicate,
            }
        finally:
            for temp_path in temp_paths:
                with suppress(FileNotFoundError):
                    temp_path.unlink()

    @app.post("/api/jobs/{job_id}/cancel")
    async def cancel_job(job_id: str):
        job = store.request_job_cancel(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        return _serialize_job(store, job_id, include_details=True)

    @app.post("/api/jobs/{job_id}/retry")
    async def retry_job(job_id: str):
        try:
            job = store.clone_job_for_retry(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Job not found") from exc
        except UnsupportedInputError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _serialize_job(store, job.id, include_details=True)

    @app.get("/api/jobs/{job_id}/events")
    async def get_job_events(job_id: str, stream: int = 0, limit: int = 200):
        if store.get_job(job_id) is None:
            raise HTTPException(status_code=404, detail="Job not found")

        if not stream:
            events = store.get_job_events(job_id)
            if limit > 0:
                events = events[-limit:]
            return [_serialize_event(event) for event in events]

        async def event_generator():
            last_id = 0
            while True:
                events = store.get_job_events(job_id, after_id=last_id)
                for event in events:
                    last_id = event.id
                    yield {
                        "id": str(event.id),
                        "data": json.dumps(_serialize_event(event)),
                    }

                job = store.get_job(job_id)
                if job and job.status.value in {"completed", "failed", "cancelled"}:
                    if not events:
                        yield {
                            "data": json.dumps({"job_id": job_id, "type": "end", "status": job.status.value}),
                        }
                        break
                await asyncio.sleep(1)

        return EventSourceResponse(event_generator())

    @app.get("/api/events")
    async def list_events(limit: int = 200):
        return [_serialize_event(event) for event in store.list_events(limit)]

    @app.get("/api/jobs/{job_id}/artifacts")
    async def list_job_artifacts(job_id: str):
        if store.get_job(job_id) is None:
            raise HTTPException(status_code=404, detail="Job not found")
        return [
            _serialize_artifact(job_id, artifact) for artifact in store.list_job_artifacts(job_id)
        ]

    @app.get("/api/jobs/{job_id}/artifacts/download/{artifact_id}")
    async def download_job_artifact(job_id: str, artifact_id: str):
        artifact = store.get_artifact_by_id(artifact_id)
        if artifact is None or artifact["job_id"] != job_id:
            raise HTTPException(status_code=404, detail="Artifact not found")
        path = Path(artifact["storage_path"])
        if not path.exists():
            raise HTTPException(status_code=404, detail="Artifact file not found")
        return FileResponse(path, filename=artifact["file_name"])

    @app.get("/api/jobs/{job_id}/artifacts/{kind}")
    async def get_job_artifact(job_id: str, kind: str):
        try:
            artifact_kind = ArtifactKind(kind)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Unknown artifact kind: {kind}") from exc
        path = store.get_job_artifact_path(job_id, artifact_kind.value)
        if path is None or not path.exists():
            raise HTTPException(status_code=404, detail="Artifact not found")
        return FileResponse(path)

    if paths.FRONTEND_DIST_DIR.exists():
        assets_dir = paths.FRONTEND_DIST_DIR / "assets"
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

        @app.get("/", response_class=HTMLResponse)
        @app.get("/{path:path}", response_class=HTMLResponse)
        async def serve_frontend(path: str = ""):
            if path.startswith("api/"):
                raise HTTPException(status_code=404, detail="Not found")
            index_path = paths.FRONTEND_DIST_DIR / "index.html"
            return HTMLResponse(index_path.read_text(encoding="utf-8"))

    else:
        @app.get("/", response_class=JSONResponse)
        async def frontend_placeholder():
            return JSONResponse(
                {
                    "message": "Frontend has not been built yet.",
                    "hint": "Run the frontend build to serve the dashboard.",
                }
            )

    return app
