from __future__ import annotations

import json

from fastapi.testclient import TestClient
from pdf2zh_next_enhanced.api import create_app
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
