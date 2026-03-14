from __future__ import annotations

import io
import json

import pdf2zh_next_enhanced.api as api_module
import pdf2zh_next_enhanced.store as store_module
from fastapi.testclient import TestClient
from pdf2zh_next_enhanced.api import create_app
from pdf2zh_next_enhanced.file_validation import PreparedInputFile
from pdf2zh_next_enhanced.schemas import JobCreatePayload
from pdf2zh_next_enhanced.schemas import OpenAIProfileInput
from pdf2zh_next_enhanced.store import AppStore

from .test_store import _make_pdf
from .test_store import _patch_data_paths


def test_profile_endpoints_and_health_aliases(tmp_path, monkeypatch):
    database_path = _patch_data_paths(tmp_path, monkeypatch)
    client = TestClient(create_app())

    response = client.post(
        "/api/provider-profiles",
        json={
            "provider_type": "openai",
            "name": "Primary OpenAI",
            "model": "gpt-5.4",
            "api_key": "sk-test-key",
            "is_default": True,
        },
    )
    assert response.status_code == 200
    profile_id = response.json()["id"]

    secondary = client.post(
        "/api/profiles",
        json={
            "provider_type": "openai",
            "name": "Secondary OpenAI",
            "model": "gpt-5.4",
            "api_key": "sk-secondary-key",
        },
    )
    assert secondary.status_code == 200
    secondary_id = secondary.json()["id"]

    profiles = client.get("/api/profiles")
    assert profiles.status_code == 200
    payload = profiles.json()
    assert len(payload) == 2
    assert payload[0]["provider_type"] == "openai"

    health = client.get("/api/health")
    assert health.status_code == 200
    health_payload = health.json()
    assert health_payload["default_profile_id"] == profile_id
    assert health_payload["profiles_count"] == 2
    assert health_payload["database_ok"] is True

    delete = client.delete(f"/api/provider-profiles/{secondary_id}")
    assert delete.status_code == 204

    store = AppStore(database_path)
    assert store.get_provider_profile(secondary_id) is None


def test_job_submission_events_and_duplicate_detection(tmp_path, monkeypatch):
    _patch_data_paths(tmp_path, monkeypatch)
    client = TestClient(create_app())

    profile_response = client.post(
        "/api/provider-profiles",
        json={
            "provider_type": "openai",
            "name": "Queue Profile",
            "model": "gpt-5.4",
            "api_key": "sk-queue-key",
        },
    )
    profile_id = profile_response.json()["id"]
    pdf_path = _make_pdf(tmp_path / "paper.pdf")

    with pdf_path.open("rb") as file_obj:
        response = client.post(
            "/api/jobs",
            files={"files": ("paper.pdf", file_obj, "application/pdf")},
            data={
                "payload": json.dumps(
                    {
                        "profile_id": profile_id,
                        "options": {
                            "lang_in": "en",
                            "lang_out": "ko",
                            "qps": 2,
                            "no_mono": False,
                            "no_dual": False,
                            "no_auto_extract_glossary": True,
                            "save_auto_extracted_glossary": False,
                        },
                    }
                )
            },
        )
    assert response.status_code == 200
    body = response.json()
    assert body["duplicate"] is False
    job_id = body["job"]["id"]
    assert body["job"]["source_lang"] == "en"
    assert body["job"]["target_lang"] == "ko"

    with pdf_path.open("rb") as file_obj:
        duplicate = client.post(
            "/api/jobs",
            files={"files": ("paper.pdf", file_obj, "application/pdf")},
            data={
                "payload": json.dumps(
                    {
                        "profile_id": profile_id,
                        "options": {
                            "lang_in": "en",
                            "lang_out": "ko",
                            "qps": 2,
                            "no_mono": False,
                            "no_dual": False,
                            "no_auto_extract_glossary": True,
                            "save_auto_extracted_glossary": False,
                        },
                    }
                )
            },
        )
    assert duplicate.status_code == 200
    assert duplicate.json()["duplicate"] is True
    assert duplicate.json()["job"]["id"] == job_id

    jobs = client.get("/api/jobs")
    assert jobs.status_code == 200
    assert jobs.json()[0]["id"] == job_id

    events = client.get(f"/api/jobs/{job_id}/events")
    assert events.status_code == 200
    assert any(event["type"] == "submitted" for event in events.json())

    global_events = client.get("/api/events")
    assert global_events.status_code == 200
    assert any(event["job_id"] == job_id for event in global_events.json())

    artifacts = client.get(f"/api/jobs/{job_id}/artifacts")
    assert artifacts.status_code == 200
    assert artifacts.json() == []


def test_job_submission_auto_converts_docx_upload(tmp_path, monkeypatch):
    _patch_data_paths(tmp_path, monkeypatch)
    client = TestClient(create_app())

    profile_response = client.post(
        "/api/provider-profiles",
        json={
            "provider_type": "openai",
            "name": "DOCX Guard",
            "model": "gpt-5.4",
            "api_key": "sk-docx-guard",
        },
    )
    profile_id = profile_response.json()["id"]

    def fake_prepare_uploaded_file(filename, _content, _content_type, working_dir):
        pdf_path = _make_pdf(working_dir / "paper.pdf")
        return PreparedInputFile(
            path=pdf_path,
            original_name=filename,
            storage_name="paper.pdf",
            converted=True,
        )

    monkeypatch.setattr(api_module, "prepare_uploaded_file", fake_prepare_uploaded_file)

    response = client.post(
        "/api/jobs",
        files={
            "files": (
                "paper.docx",
                io.BytesIO(b"PK\x03\x04fake-docx"),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
        data={
            "payload": json.dumps(
                {
                    "profile_id": profile_id,
                    "options": {
                        "lang_in": "en",
                        "lang_out": "ko",
                        "qps": 1,
                        "no_mono": True,
                        "no_dual": False,
                        "no_auto_extract_glossary": True,
                        "save_auto_extracted_glossary": False,
                    },
                }
            )
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["duplicate"] is False
    assert body["job"]["files"][0]["original_name"] == "paper.docx"
    assert body["job"]["files"][0]["name"] == "paper.docx"


def test_job_submission_rejects_unsupported_upload(tmp_path, monkeypatch):
    _patch_data_paths(tmp_path, monkeypatch)
    client = TestClient(create_app())

    profile_response = client.post(
        "/api/provider-profiles",
        json={
            "provider_type": "openai",
            "name": "Unsupported Guard",
            "model": "gpt-5.4",
            "api_key": "sk-unsupported-guard",
        },
    )
    profile_id = profile_response.json()["id"]

    response = client.post(
        "/api/jobs",
        files={"files": ("paper.zip", io.BytesIO(b"PK\x03\x04fake-zip"), "application/zip")},
        data={
            "payload": json.dumps(
                {
                    "profile_id": profile_id,
                    "options": {
                        "lang_in": "en",
                        "lang_out": "ko",
                        "qps": 1,
                        "no_mono": True,
                        "no_dual": False,
                        "no_auto_extract_glossary": True,
                        "save_auto_extracted_glossary": False,
                    },
                }
            )
        },
    )

    assert response.status_code == 400
    assert "not supported for automatic conversion" in response.json()["detail"]


def test_retry_auto_converts_legacy_docx_job(tmp_path, monkeypatch):
    database_path = _patch_data_paths(tmp_path, monkeypatch)
    client = TestClient(create_app())
    store = AppStore(database_path)
    profile = store.save_provider_profile(
        OpenAIProfileInput(
            name="Legacy DOCX",
            model="gpt-5.4",
            api_key="sk-legacy-docx",
        )
    )
    legacy_docx = tmp_path / "legacy.docx"
    legacy_docx.write_bytes(b"PK\x03\x04legacy-docx")
    legacy_job, _ = store.create_job(JobCreatePayload(profile_id=profile.id), [legacy_docx])

    def fake_prepare_retry_source_file(_source_path, original_name, working_dir):
        working_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = _make_pdf(working_dir / "legacy.pdf")
        return PreparedInputFile(
            path=pdf_path,
            original_name=original_name,
            storage_name="legacy.pdf",
            converted=True,
        )

    monkeypatch.setattr(store_module, "prepare_retry_source_file", fake_prepare_retry_source_file)

    response = client.post(f"/api/jobs/{legacy_job.id}/retry")

    assert response.status_code == 200
    assert response.json()["duplicate_of"] == legacy_job.id
    assert response.json()["files"][0]["original_name"] == "legacy.docx"
