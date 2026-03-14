from __future__ import annotations

from pathlib import Path

from pdf2zh_next_enhanced.schemas import JobCreatePayload
from pdf2zh_next_enhanced.schemas import JobStatus
from pdf2zh_next_enhanced.schemas import OpenAIProfileInput
from pdf2zh_next_enhanced.store import AppStore


def _patch_data_paths(tmp_path, monkeypatch):
    import pdf2zh_next_enhanced.crypto as crypto_module
    import pdf2zh_next_enhanced.paths as paths_module
    import pdf2zh_next_enhanced.store as store_module

    data_root = tmp_path / "data"
    uploads_dir = data_root / "uploads"
    artifacts_dir = data_root / "artifacts"
    logs_dir = data_root / "logs"
    secrets_dir = data_root / "secrets"
    state_dir = data_root / "state"
    database_path = data_root / "app.db"

    for path in (data_root, uploads_dir, artifacts_dir, logs_dir, secrets_dir, state_dir):
        path.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(paths_module, "DATA_ROOT", data_root)
    monkeypatch.setattr(paths_module, "UPLOADS_DIR", uploads_dir)
    monkeypatch.setattr(paths_module, "ARTIFACTS_DIR", artifacts_dir)
    monkeypatch.setattr(paths_module, "LOGS_DIR", logs_dir)
    monkeypatch.setattr(paths_module, "SECRETS_DIR", secrets_dir)
    monkeypatch.setattr(paths_module, "STATE_DIR", state_dir)
    monkeypatch.setattr(paths_module, "DATABASE_PATH", database_path)
    monkeypatch.setattr(paths_module, "ENCRYPTION_KEY_PATH", secrets_dir / "app.key")

    monkeypatch.setattr(store_module, "UPLOADS_DIR", uploads_dir)
    monkeypatch.setattr(store_module, "ARTIFACTS_DIR", artifacts_dir)
    monkeypatch.setattr(store_module, "LOGS_DIR", logs_dir)
    monkeypatch.setattr(store_module, "DATABASE_PATH", database_path)

    monkeypatch.setattr(crypto_module, "ENCRYPTION_KEY_PATH", secrets_dir / "app.key")
    return database_path


def _make_pdf(path: Path) -> Path:
    path.write_bytes(
        b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Count 0>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"
    )
    return path


def test_profile_round_trip_and_health(tmp_path, monkeypatch):
    database_path = _patch_data_paths(tmp_path, monkeypatch)
    store = AppStore(database_path)

    profile = store.save_provider_profile(
        OpenAIProfileInput(
            name="Primary OpenAI",
            model="gpt-5.4",
            api_key="sk-test-key",
        )
    )

    runtime_payload = store.get_profile_runtime_payload(profile.id)
    health = store.health()

    assert profile.has_secret is True
    assert runtime_payload["secrets"]["api_key"] == "sk-test-key"
    assert health.profiles_count == 1
    assert health.default_profile_id == profile.id


def test_job_duplicate_detection(tmp_path, monkeypatch):
    database_path = _patch_data_paths(tmp_path, monkeypatch)
    store = AppStore(database_path)
    profile = store.save_provider_profile(
        OpenAIProfileInput(
            name="Duplicate Test",
            model="gpt-5.4",
            api_key="sk-dup-test",
        )
    )
    source_pdf = _make_pdf(tmp_path / "paper.pdf")
    payload = JobCreatePayload(profile_id=profile.id)

    first_job, first_duplicate = store.create_job(payload, [source_pdf])
    second_job, second_duplicate = store.create_job(payload, [source_pdf])

    assert first_duplicate is False
    assert second_duplicate is True
    assert second_job.id == first_job.id


def test_retry_and_cancel_lifecycle(tmp_path, monkeypatch):
    database_path = _patch_data_paths(tmp_path, monkeypatch)
    store = AppStore(database_path)
    profile = store.save_provider_profile(
        OpenAIProfileInput(
            name="Lifecycle Test",
            model="gpt-5.4",
            api_key="sk-life-test",
        )
    )
    source_pdf = _make_pdf(tmp_path / "retry.pdf")
    original_job, _ = store.create_job(JobCreatePayload(profile_id=profile.id), [source_pdf])

    cancelled = store.request_job_cancel(original_job.id)
    retry_job = store.clone_job_for_retry(original_job.id)

    assert cancelled is not None
    assert cancelled.status == JobStatus.CANCELLED
    assert retry_job.duplicate_of == original_job.id
    assert retry_job.status == JobStatus.QUEUED
