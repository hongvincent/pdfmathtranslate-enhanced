from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from pathlib import Path
from typing import Any

import fitz

from .crypto import decrypt_text
from .crypto import encrypt_text
from .file_validation import PDF_SIGNATURE
from .file_validation import validate_retry_source_file
from .paths import ARTIFACTS_DIR
from .paths import DATABASE_PATH
from .paths import DEFAULT_TIMEOUT_SECONDS
from .paths import LOGS_DIR
from .paths import UPLOADS_DIR
from .paths import WORKER_STALE_SECONDS
from .paths import ensure_data_dirs
from .schemas import ArtifactKind
from .schemas import BedrockProfileInput
from .schemas import JobArtifact
from .schemas import JobCreatePayload
from .schemas import JobEventRecord
from .schemas import JobFileRecord
from .schemas import JobRecord
from .schemas import JobStatus
from .schemas import OpenAIProfileInput
from .schemas import ProviderProfileInput
from .schemas import ProviderProfileRecord
from .schemas import ProviderType
from .schemas import SystemHealthResponse


def utcnow() -> datetime:
    return datetime.now(UTC)


def to_iso(value: datetime | None = None) -> str:
    value = value or utcnow()
    return value.isoformat()


def from_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def loads(value: str | None, default: Any = None) -> Any:
    if not value:
        return default
    return json.loads(value)


def sanitize_name(name: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in {".", "-", "_"} else "_" for ch in name)
    return safe.strip("._") or "file.pdf"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as file_obj:
        while chunk := file_obj.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def count_pdf_pages(path: Path) -> int | None:
    try:
        with fitz.open(path) as document:
            return document.page_count
    except Exception:
        return None


@dataclass
class JobBundle:
    job: dict[str, Any]
    files: list[dict[str, Any]]
    profile_snapshot: dict[str, Any]


class AppStore:
    def __init__(self, database_path: Path | None = None):
        ensure_data_dirs()
        self.database_path = database_path or DATABASE_PATH
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.database_path, timeout=30, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def init_db(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS provider_profiles (
                    id TEXT PRIMARY KEY,
                    provider_type TEXT NOT NULL,
                    name TEXT NOT NULL UNIQUE,
                    config_json TEXT NOT NULL,
                    secrets_json TEXT,
                    validation_status TEXT,
                    validation_error TEXT,
                    validated_models_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS app_settings (
                    key TEXT PRIMARY KEY,
                    value_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    profile_id TEXT NOT NULL,
                    profile_snapshot_json TEXT NOT NULL,
                    options_json TEXT NOT NULL,
                    dedupe_key TEXT,
                    duplicate_of TEXT,
                    cancel_requested INTEGER NOT NULL DEFAULT 0,
                    overall_progress REAL NOT NULL DEFAULT 0,
                    current_step TEXT,
                    token_usage_json TEXT,
                    timeout_seconds INTEGER NOT NULL DEFAULT 3600,
                    error_message TEXT,
                    error_details TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    FOREIGN KEY(profile_id) REFERENCES provider_profiles(id)
                );

                CREATE INDEX IF NOT EXISTS idx_jobs_status_created ON jobs(status, created_at);
                CREATE INDEX IF NOT EXISTS idx_jobs_dedupe ON jobs(dedupe_key);

                CREATE TABLE IF NOT EXISTS job_files (
                    id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    original_name TEXT NOT NULL,
                    storage_path TEXT NOT NULL,
                    file_hash TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    page_count INTEGER,
                    sort_order INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS job_artifacts (
                    id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    job_file_id TEXT,
                    kind TEXT NOT NULL,
                    file_name TEXT NOT NULL,
                    storage_path TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE,
                    FOREIGN KEY(job_file_id) REFERENCES job_files(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS job_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    level TEXT NOT NULL,
                    message TEXT NOT NULL,
                    data_json TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_job_events_job_id ON job_events(job_id, id);

                CREATE TABLE IF NOT EXISTS worker_state (
                    worker_name TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    current_job_id TEXT,
                    note TEXT,
                    last_seen_at TEXT NOT NULL
                );
                """
            )

    def get_setting(self, key: str, default: Any = None) -> Any:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT value_json FROM app_settings WHERE key = ?",
                (key,),
            ).fetchone()
        return loads(row["value_json"], default) if row else default

    def set_setting(self, key: str, value: Any) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO app_settings (key, value_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value_json = excluded.value_json,
                    updated_at = excluded.updated_at
                """,
                (key, dumps(value), to_iso()),
            )

    def _extract_profile_payload(
        self,
        payload: ProviderProfileInput,
        existing_secrets: dict[str, str | None] | None = None,
    ) -> tuple[dict[str, Any], dict[str, str | None]]:
        data = payload.model_dump()
        secrets: dict[str, str | None] = {}
        config = {
            "name": data["name"],
            "provider_type": data["provider_type"],
        }
        existing_secrets = existing_secrets or {}

        if isinstance(payload, OpenAIProfileInput):
            data.pop("is_default", None)
            api_key = data.pop("api_key", None)
            secrets["api_key"] = api_key or existing_secrets.get("api_key")
            for key in (
                "base_url",
                "model",
                "snapshot_model",
                "use_snapshot",
                "reasoning_effort",
                "temperature",
                "send_temperature",
                "send_reasoning_effort",
                "timeout_seconds",
            ):
                config[key] = data[key]
        elif isinstance(payload, BedrockProfileInput):
            data.pop("is_default", None)
            for secret_key in (
                "access_key_id",
                "secret_access_key",
                "session_token",
            ):
                candidate = data.pop(secret_key, None)
                secrets[secret_key] = candidate or existing_secrets.get(secret_key)
            for key in (
                "region",
                "model_id",
                "auth_mode",
                "profile_name",
                "timeout_seconds",
                "temperature",
            ):
                config[key] = data[key]
        else:
            raise ValueError(f"Unsupported profile payload: {type(payload)}")

        return config, secrets

    def _profile_row_to_record(self, row: sqlite3.Row) -> ProviderProfileRecord:
        config = loads(row["config_json"], {})
        secrets = {
            key: decrypt_text(value) if value else None
            for key, value in loads(row["secrets_json"], {}).items()
        }
        has_secret = any(bool(value) for value in secrets.values())
        return ProviderProfileRecord(
            id=row["id"],
            provider_type=ProviderType(row["provider_type"]),
            name=row["name"],
            config=config,
            has_secret=has_secret,
            is_default=self.get_setting("default_profile_id") == row["id"],
            validation_status=row["validation_status"],
            validation_error=row["validation_error"],
            validated_models=loads(row["validated_models_json"], []),
            created_at=from_iso(row["created_at"]) or utcnow(),
            updated_at=from_iso(row["updated_at"]) or utcnow(),
        )

    def list_provider_profiles(self) -> list[ProviderProfileRecord]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM provider_profiles ORDER BY updated_at DESC"
            ).fetchall()
        return [self._profile_row_to_record(row) for row in rows]

    def get_provider_profile(self, profile_id: str) -> ProviderProfileRecord | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM provider_profiles WHERE id = ?",
                (profile_id,),
            ).fetchone()
        return self._profile_row_to_record(row) if row else None

    def get_profile_runtime_payload(self, profile_id: str) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM provider_profiles WHERE id = ?",
                (profile_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Unknown profile: {profile_id}")

        config = loads(row["config_json"], {})
        secrets = {
            key: decrypt_text(value) if value else None
            for key, value in loads(row["secrets_json"], {}).items()
        }
        return {
            "id": row["id"],
            "name": row["name"],
            "provider_type": row["provider_type"],
            "config": config,
            "secrets": secrets,
        }

    def save_provider_profile(
        self,
        payload: ProviderProfileInput,
        profile_id: str | None = None,
    ) -> ProviderProfileRecord:
        existing_secrets: dict[str, str | None] = {}
        now = to_iso()
        if profile_id:
            with self.connect() as conn:
                row = conn.execute(
                    "SELECT secrets_json FROM provider_profiles WHERE id = ?",
                    (profile_id,),
                ).fetchone()
            if row:
                existing_secrets = {
                    key: decrypt_text(value) if value else None
                    for key, value in loads(row["secrets_json"], {}).items()
                }

        config, secrets = self._extract_profile_payload(payload, existing_secrets)
        encrypted_secrets = {
            key: encrypt_text(value)
            for key, value in secrets.items()
            if value not in (None, "")
        }

        profile_id = profile_id or str(uuid.uuid4())
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO provider_profiles (
                    id, provider_type, name, config_json, secrets_json,
                    validation_status, validation_error, validated_models_json,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    provider_type = excluded.provider_type,
                    name = excluded.name,
                    config_json = excluded.config_json,
                    secrets_json = excluded.secrets_json,
                    validation_status = NULL,
                    validation_error = NULL,
                    validated_models_json = excluded.validated_models_json,
                    updated_at = excluded.updated_at
                """,
                (
                    profile_id,
                    config["provider_type"],
                    config["name"],
                    dumps(config),
                    dumps(encrypted_secrets),
                    dumps([]),
                    now,
                    now,
                ),
            )
        if getattr(payload, "is_default", False) or self.get_setting("default_profile_id") is None:
            self.set_setting("default_profile_id", profile_id)
        profile = self.get_provider_profile(profile_id)
        assert profile is not None
        return profile

    def delete_provider_profile(self, profile_id: str) -> None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT id FROM provider_profiles WHERE id = ?",
                (profile_id,),
            ).fetchone()
            if row is None:
                raise KeyError(profile_id)
            usage = conn.execute(
                "SELECT COUNT(*) AS count FROM jobs WHERE profile_id = ?",
                (profile_id,),
            ).fetchone()["count"]
            if usage:
                raise ValueError("Cannot delete a profile that is referenced by existing jobs")
            conn.execute("DELETE FROM provider_profiles WHERE id = ?", (profile_id,))
        if self.get_setting("default_profile_id") == profile_id:
            next_profile = self.list_provider_profiles()
            self.set_setting("default_profile_id", next_profile[0].id if next_profile else None)

    def mark_profile_validation(
        self,
        profile_id: str,
        ok: bool,
        message: str,
        validated_models: list[str] | None = None,
    ) -> ProviderProfileRecord:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE provider_profiles
                SET validation_status = ?, validation_error = ?, validated_models_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    "ok" if ok else "error",
                    None if ok else message,
                    dumps(validated_models or []),
                    to_iso(),
                    profile_id,
                ),
            )
        profile = self.get_provider_profile(profile_id)
        assert profile is not None
        return profile

    def append_event(
        self,
        job_id: str,
        event_type: str,
        message: str,
        *,
        level: str = "info",
        data: dict[str, Any] | None = None,
    ) -> int:
        created_at = to_iso()
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO job_events (job_id, event_type, level, message, data_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (job_id, event_type, level, message, dumps(data or {}), created_at),
            )
            return int(cursor.lastrowid)

    def _collect_job_artifacts(
        self,
        conn: sqlite3.Connection,
        job_id: str,
    ) -> dict[str, list[JobArtifact]]:
        rows = conn.execute(
            "SELECT * FROM job_artifacts WHERE job_id = ? ORDER BY created_at ASC",
            (job_id,),
        ).fetchall()
        grouped: dict[str, list[JobArtifact]] = {}
        for row in rows:
            artifact = JobArtifact(
                id=row["id"],
                kind=ArtifactKind(row["kind"]),
                file_name=row["file_name"],
                size_bytes=row["size_bytes"],
                created_at=from_iso(row["created_at"]) or utcnow(),
            )
            grouped.setdefault(row["job_file_id"], []).append(artifact)
        return grouped

    def _job_row_to_record(self, conn: sqlite3.Connection, row: sqlite3.Row) -> JobRecord:
        file_rows = conn.execute(
            """
            SELECT jf.*
            FROM job_files jf
            WHERE jf.job_id = ?
            ORDER BY jf.sort_order ASC
            """,
            (row["id"],),
        ).fetchall()
        artifacts = self._collect_job_artifacts(conn, row["id"])
        profile = conn.execute(
            "SELECT name FROM provider_profiles WHERE id = ?",
            (row["profile_id"],),
        ).fetchone()
        files = [
            JobFileRecord(
                id=file_row["id"],
                original_name=file_row["original_name"],
                file_hash=file_row["file_hash"],
                size_bytes=file_row["size_bytes"],
                page_count=file_row["page_count"],
                status=file_row["status"],
                artifacts=artifacts.get(file_row["id"], []),
                error_message=file_row["error_message"],
            )
            for file_row in file_rows
        ]
        return JobRecord(
            id=row["id"],
            status=JobStatus(row["status"]),
            profile_id=row["profile_id"],
            profile_name=profile["name"] if profile else None,
            created_at=from_iso(row["created_at"]) or utcnow(),
            updated_at=from_iso(row["updated_at"]) or utcnow(),
            started_at=from_iso(row["started_at"]),
            completed_at=from_iso(row["completed_at"]),
            error_message=row["error_message"],
            error_details=row["error_details"],
            token_usage=loads(row["token_usage_json"], {}),
            overall_progress=row["overall_progress"] or 0.0,
            current_step=row["current_step"],
            duplicate_of=row["duplicate_of"],
            files=files,
        )

    def list_jobs(self, limit: int = 100) -> list[JobRecord]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [self._job_row_to_record(conn, row) for row in rows]

    def get_job(self, job_id: str) -> JobRecord | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
            return self._job_row_to_record(conn, row) if row else None

    def get_job_events(
        self,
        job_id: str,
        after_id: int | None = None,
    ) -> list[JobEventRecord]:
        query = """
            SELECT * FROM job_events
            WHERE job_id = ? {after_clause}
            ORDER BY id ASC
        """
        after_clause = ""
        params: list[Any] = [job_id]
        if after_id:
            after_clause = "AND id > ?"
            params.append(after_id)
        with self.connect() as conn:
            rows = conn.execute(query.format(after_clause=after_clause), tuple(params)).fetchall()
        return [
            JobEventRecord(
                id=row["id"],
                event_type=row["event_type"],
                level=row["level"],
                message=row["message"],
                created_at=from_iso(row["created_at"]) or utcnow(),
                data=loads(row["data_json"], {}),
            )
            for row in rows
        ]

    def list_events(self, limit: int = 200) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT e.*, j.current_step, j.status
                FROM job_events e
                JOIN jobs j ON j.id = e.job_id
                ORDER BY e.id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "job_id": row["job_id"],
                "event_type": row["event_type"],
                "level": row["level"],
                "message": row["message"],
                "created_at": row["created_at"],
                "data": loads(row["data_json"], {}),
                "status": row["status"],
                "current_step": row["current_step"],
            }
            for row in rows
        ]

    def list_job_artifacts(self, job_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT ja.*, jf.original_name
                FROM job_artifacts ja
                LEFT JOIN job_files jf ON jf.id = ja.job_file_id
                WHERE ja.job_id = ?
                ORDER BY ja.created_at ASC
                """,
                (job_id,),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "job_id": row["job_id"],
                "job_file_id": row["job_file_id"],
                "kind": row["kind"],
                "file_name": row["file_name"],
                "storage_path": row["storage_path"],
                "size_bytes": row["size_bytes"],
                "created_at": row["created_at"],
                "original_name": row["original_name"],
            }
            for row in rows
        ]

    def get_artifact_by_id(self, artifact_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT ja.*, jf.original_name
                FROM job_artifacts ja
                LEFT JOIN job_files jf ON jf.id = ja.job_file_id
                WHERE ja.id = ?
                """,
                (artifact_id,),
            ).fetchone()
        return dict(row) if row else None

    def _make_dedupe_key(
        self,
        file_hashes: list[str],
        profile_snapshot: dict[str, Any],
        options: dict[str, Any],
    ) -> str:
        digest_payload = {
            "files": sorted(file_hashes),
            "profile": profile_snapshot.get("config", {}),
            "options": options,
        }
        return hashlib.sha256(dumps(digest_payload).encode("utf-8")).hexdigest()

    def create_job(
        self,
        payload: JobCreatePayload,
        source_files: list[Path],
    ) -> tuple[JobRecord, bool]:
        runtime_profile = self.get_profile_runtime_payload(payload.profile_id)
        now = to_iso()
        job_id = str(uuid.uuid4())
        profile_snapshot = {
            "provider_type": runtime_profile["provider_type"],
            "name": runtime_profile["name"],
            "config": runtime_profile["config"],
            "secrets": {
                key: encrypt_text(value)
                for key, value in runtime_profile["secrets"].items()
                if value not in (None, "")
            },
        }
        options = payload.options.model_dump()
        upload_dir = UPLOADS_DIR / job_id
        upload_dir.mkdir(parents=True, exist_ok=True)

        file_hashes: list[str] = []
        prepared_files: list[dict[str, Any]] = []
        for index, source_file in enumerate(source_files):
            destination = upload_dir / f"{index:02d}-{sanitize_name(source_file.name)}"
            shutil.copy2(source_file, destination)
            file_hash = sha256_file(destination)
            file_hashes.append(file_hash)
            prepared_files.append(
                {
                    "id": str(uuid.uuid4()),
                    "original_name": source_file.name,
                    "storage_path": str(destination),
                    "file_hash": file_hash,
                    "size_bytes": destination.stat().st_size,
                    "page_count": count_pdf_pages(destination),
                    "sort_order": index,
                }
            )

        dedupe_key = self._make_dedupe_key(file_hashes, profile_snapshot, options)
        with self.connect() as conn:
            duplicate = conn.execute(
                """
                SELECT id FROM jobs
                WHERE dedupe_key = ?
                  AND status IN (?, ?, ?, ?)
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (
                    dedupe_key,
                    JobStatus.QUEUED.value,
                    JobStatus.VALIDATING.value,
                    JobStatus.RUNNING.value,
                    JobStatus.COMPLETED.value,
                ),
            ).fetchone()
        if duplicate:
            existing = self.get_job(duplicate["id"])
            assert existing is not None
            shutil.rmtree(upload_dir, ignore_errors=True)
            return existing, True

        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO jobs (
                    id, status, profile_id, profile_snapshot_json, options_json,
                    dedupe_key, timeout_seconds, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    JobStatus.QUEUED.value,
                    payload.profile_id,
                    dumps(profile_snapshot),
                    dumps(options),
                    dedupe_key,
                    options.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS),
                    now,
                    now,
                ),
            )
            for prepared in prepared_files:
                conn.execute(
                    """
                    INSERT INTO job_files (
                        id, job_id, original_name, storage_path, file_hash, size_bytes,
                        page_count, sort_order, status, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        prepared["id"],
                        job_id,
                        prepared["original_name"],
                        prepared["storage_path"],
                        prepared["file_hash"],
                        prepared["size_bytes"],
                        prepared["page_count"],
                        prepared["sort_order"],
                        JobStatus.QUEUED.value,
                        now,
                        now,
                    ),
                )
        self.set_setting("default_profile_id", payload.profile_id)
        self.set_setting("last_job_options", options)
        self.append_event(job_id, "submitted", "Job queued", data={"files": len(prepared_files)})
        job = self.get_job(job_id)
        assert job is not None
        return job, False

    def clone_job_for_retry(self, job_id: str) -> JobRecord:
        bundle = self.get_job_bundle(job_id)
        new_job_id = str(uuid.uuid4())
        now = to_iso()
        options = loads(bundle.job["options_json"], {})
        for file_row in bundle.files:
            original_path = Path(file_row["storage_path"])
            with original_path.open("rb") as handle:
                header = handle.read(len(PDF_SIGNATURE))
            validate_retry_source_file(file_row["original_name"], header)

        new_upload_dir = UPLOADS_DIR / new_job_id
        new_upload_dir.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO jobs (
                    id, status, profile_id, profile_snapshot_json, options_json,
                    timeout_seconds, created_at, updated_at, duplicate_of
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_job_id,
                    JobStatus.QUEUED.value,
                    bundle.job["profile_id"],
                    bundle.job["profile_snapshot_json"],
                    bundle.job["options_json"],
                    bundle.job["timeout_seconds"],
                    now,
                    now,
                    job_id,
                ),
            )
            for file_row in bundle.files:
                original_path = Path(file_row["storage_path"])
                new_path = new_upload_dir / sanitize_name(file_row["original_name"])
                shutil.copy2(original_path, new_path)
                conn.execute(
                    """
                    INSERT INTO job_files (
                        id, job_id, original_name, storage_path, file_hash, size_bytes,
                        page_count, sort_order, status, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        new_job_id,
                        file_row["original_name"],
                        str(new_path),
                        sha256_file(new_path),
                        new_path.stat().st_size,
                        count_pdf_pages(new_path),
                        file_row["sort_order"],
                        JobStatus.QUEUED.value,
                        now,
                        now,
                    ),
                )
        self.append_event(new_job_id, "retried", f"Retry created from job {job_id}")
        job = self.get_job(new_job_id)
        assert job is not None
        return job

    def request_job_cancel(self, job_id: str) -> JobRecord | None:
        event_type = "cancel_requested"
        event_message = "Cancellation requested"
        with self.connect() as conn:
            row = conn.execute(
                "SELECT status FROM jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
            if row is None:
                return None
            if row["status"] == JobStatus.QUEUED.value:
                conn.execute(
                    """
                    UPDATE jobs
                    SET status = ?, cancel_requested = 1, updated_at = ?, completed_at = ?
                    WHERE id = ?
                    """,
                    (JobStatus.CANCELLED.value, to_iso(), to_iso(), job_id),
                )
                conn.execute(
                    "UPDATE job_files SET status = ?, updated_at = ? WHERE job_id = ?",
                    (JobStatus.CANCELLED.value, to_iso(), job_id),
                )
                event_type = "cancelled"
                event_message = "Queued job cancelled"
            else:
                conn.execute(
                    "UPDATE jobs SET cancel_requested = 1, updated_at = ? WHERE id = ?",
                    (to_iso(), job_id),
                )
        self.append_event(job_id, event_type, event_message)
        return self.get_job(job_id)

    def is_cancel_requested(self, job_id: str) -> bool:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT cancel_requested FROM jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
        return bool(row and row["cancel_requested"])

    def claim_next_job(self, worker_name: str) -> JobBundle | None:
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """
                SELECT * FROM jobs
                WHERE status = ?
                ORDER BY created_at ASC
                LIMIT 1
                """,
                (JobStatus.QUEUED.value,),
            ).fetchone()
            if row is None:
                return None
            now = to_iso()
            conn.execute(
                """
                UPDATE jobs
                SET status = ?, started_at = COALESCE(started_at, ?), updated_at = ?, current_step = ?
                WHERE id = ?
                """,
                (JobStatus.VALIDATING.value, now, now, "Worker picked up job", row["id"]),
            )
            file_rows = conn.execute(
                "SELECT * FROM job_files WHERE job_id = ? ORDER BY sort_order ASC",
                (row["id"],),
            ).fetchall()
            profile_snapshot = loads(row["profile_snapshot_json"], {})
        self.touch_worker(worker_name, "busy", row["id"])
        self.append_event(row["id"], "claimed", f"Worker {worker_name} claimed job")
        return JobBundle(job=dict(row), files=[dict(file_row) for file_row in file_rows], profile_snapshot=profile_snapshot)

    def touch_worker(
        self,
        worker_name: str,
        status: str,
        current_job_id: str | None = None,
        note: str | None = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO worker_state (worker_name, status, current_job_id, note, last_seen_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(worker_name) DO UPDATE SET
                    status = excluded.status,
                    current_job_id = excluded.current_job_id,
                    note = excluded.note,
                    last_seen_at = excluded.last_seen_at
                """,
                (worker_name, status, current_job_id, note, to_iso()),
            )

    def mark_job_running(self, job_id: str, step: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE jobs
                SET status = ?, current_step = ?, updated_at = ?
                WHERE id = ?
                """,
                (JobStatus.RUNNING.value, step, to_iso(), job_id),
            )
        self.append_event(job_id, "running", step)

    def mark_file_running(self, job_file_id: str, message: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE job_files SET status = ?, updated_at = ? WHERE id = ?",
                (JobStatus.RUNNING.value, to_iso(), job_file_id),
            )
        row = self.get_job_file(job_file_id)
        if row:
            self.append_event(row["job_id"], "file_running", message, data={"job_file_id": job_file_id})

    def update_job_progress(self, job_id: str, progress: float, step: str, data: dict[str, Any] | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE jobs
                SET overall_progress = ?, current_step = ?, updated_at = ?
                WHERE id = ?
                """,
                (progress, step, to_iso(), job_id),
            )
        self.append_event(job_id, "progress", step, data={"overall_progress": progress, **(data or {})})

    def get_job_file(self, job_file_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM job_files WHERE id = ?",
                (job_file_id,),
            ).fetchone()
        return dict(row) if row else None

    def record_artifact(
        self,
        job_id: str,
        job_file_id: str | None,
        kind: ArtifactKind,
        source_path: Path,
    ) -> JobArtifact:
        artifact_id = str(uuid.uuid4())
        destination_dir = ARTIFACTS_DIR / job_id
        destination_dir.mkdir(parents=True, exist_ok=True)
        file_name = source_path.name
        destination_path = destination_dir / file_name
        if source_path.resolve() != destination_path.resolve():
            shutil.copy2(source_path, destination_path)
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO job_artifacts (id, job_id, job_file_id, kind, file_name, storage_path, size_bytes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    artifact_id,
                    job_id,
                    job_file_id,
                    kind.value,
                    file_name,
                    str(destination_path),
                    destination_path.stat().st_size,
                    to_iso(),
                ),
            )
        return JobArtifact(
            id=artifact_id,
            kind=kind,
            file_name=file_name,
            size_bytes=destination_path.stat().st_size,
            created_at=utcnow(),
        )

    def mark_file_finished(self, job_file_id: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE job_files SET status = ?, updated_at = ? WHERE id = ?",
                (JobStatus.COMPLETED.value, to_iso(), job_file_id),
            )

    def mark_file_failed(self, job_file_id: str, error_message: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE job_files
                SET status = ?, error_message = ?, updated_at = ?
                WHERE id = ?
                """,
                (JobStatus.FAILED.value, error_message, to_iso(), job_file_id),
            )

    def complete_job(self, job_id: str, token_usage: dict[str, Any] | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE jobs
                SET status = ?, overall_progress = 100, current_step = ?, token_usage_json = ?,
                    updated_at = ?, completed_at = ?
                WHERE id = ?
                """,
                (
                    JobStatus.COMPLETED.value,
                    "Completed",
                    dumps(token_usage or {}),
                    to_iso(),
                    to_iso(),
                    job_id,
                ),
            )
        self.append_event(job_id, "completed", "Job completed", data={"token_usage": token_usage or {}})

    def fail_job(self, job_id: str, error_message: str, error_details: str | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE jobs
                SET status = ?, error_message = ?, error_details = ?, current_step = ?, updated_at = ?, completed_at = ?
                WHERE id = ?
                """,
                (
                    JobStatus.FAILED.value,
                    error_message,
                    error_details,
                    "Failed",
                    to_iso(),
                    to_iso(),
                    job_id,
                ),
            )
        self.append_event(job_id, "failed", error_message, level="error", data={"details": error_details or ""})

    def cancel_job(self, job_id: str, message: str = "Job cancelled") -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE jobs
                SET status = ?, current_step = ?, updated_at = ?, completed_at = ?
                WHERE id = ?
                """,
                (JobStatus.CANCELLED.value, message, to_iso(), to_iso(), job_id),
            )
            conn.execute(
                """
                UPDATE job_files
                SET status = CASE WHEN status = ? THEN ? ELSE status END,
                    updated_at = ?
                WHERE job_id = ?
                """,
                (
                    JobStatus.RUNNING.value,
                    JobStatus.CANCELLED.value,
                    to_iso(),
                    job_id,
                ),
            )
        self.append_event(job_id, "cancelled", message, level="warning")

    def get_job_bundle(self, job_id: str) -> JobBundle:
        with self.connect() as conn:
            job = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if job is None:
                raise KeyError(job_id)
            files = conn.execute(
                "SELECT * FROM job_files WHERE job_id = ? ORDER BY sort_order ASC",
                (job_id,),
            ).fetchall()
        return JobBundle(
            job=dict(job),
            files=[dict(file_row) for file_row in files],
            profile_snapshot=loads(job["profile_snapshot_json"], {}),
        )

    def get_artifact_path(self, job_id: str, kind: ArtifactKind) -> Path | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT storage_path
                FROM job_artifacts
                WHERE job_id = ? AND kind = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (job_id, kind.value),
            ).fetchone()
        return Path(row["storage_path"]) if row else None

    def get_job_artifact_path(self, job_id: str, kind: str) -> Path | None:
        return self.get_artifact_path(job_id, ArtifactKind(kind))

    def render_log_artifact(self, job_id: str) -> Path:
        events = self.get_job_events(job_id)
        log_path = LOGS_DIR / f"{job_id}.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("w", encoding="utf-8") as file_obj:
            for event in events:
                file_obj.write(
                    f"[{event.created_at.isoformat()}] {event.level.upper()} {event.event_type}: {event.message}\n"
                )
                if event.data:
                    file_obj.write(f"  {dumps(event.data)}\n")
        return log_path

    def recover_stale_jobs(self, stale_seconds: int) -> int:
        recovered = 0
        cutoff = utcnow().timestamp() - stale_seconds
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT id, updated_at FROM jobs WHERE status IN (?, ?)",
                (JobStatus.VALIDATING.value, JobStatus.RUNNING.value),
            ).fetchall()
            for row in rows:
                updated_at = from_iso(row["updated_at"])
                if updated_at and updated_at.timestamp() < cutoff:
                    conn.execute(
                        """
                        UPDATE jobs
                        SET status = ?, error_message = ?, current_step = ?, updated_at = ?, completed_at = ?
                        WHERE id = ?
                        """,
                        (
                            JobStatus.FAILED.value,
                            "Recovered after stale worker timeout",
                            "Recovered",
                            to_iso(),
                            to_iso(),
                            row["id"],
                        ),
                    )
                    recovered += 1
        return recovered

    def health(self) -> SystemHealthResponse:
        with self.connect() as conn:
            queue_depth = conn.execute(
                "SELECT COUNT(*) AS count FROM jobs WHERE status = ?",
                (JobStatus.QUEUED.value,),
            ).fetchone()["count"]
            active_jobs = conn.execute(
                "SELECT COUNT(*) AS count FROM jobs WHERE status IN (?, ?, ?)",
                (
                    JobStatus.QUEUED.value,
                    JobStatus.VALIDATING.value,
                    JobStatus.RUNNING.value,
                ),
            ).fetchone()["count"]
            profiles_count = conn.execute(
                "SELECT COUNT(*) AS count FROM provider_profiles"
            ).fetchone()["count"]
            workers = conn.execute(
                "SELECT * FROM worker_state ORDER BY last_seen_at DESC"
            ).fetchall()
        worker_online = False
        running_job_id = None
        last_heartbeat = None
        worker = workers[0] if workers else None
        if worker:
            last_heartbeat = from_iso(worker["last_seen_at"])
            worker_online = (
                utcnow().timestamp() - (last_heartbeat or utcnow()).timestamp()
            ) < 30
            running_job_id = worker["current_job_id"]
        worker_count = sum(
            1
            for row in workers
            if (seen_at := from_iso(row["last_seen_at"]))
            and (utcnow().timestamp() - seen_at.timestamp()) < WORKER_STALE_SECONDS
        )
        warnings: list[str] = []
        if not worker_count:
            warnings.append("No worker has registered a heartbeat yet.")
        elif not worker_online:
            warnings.append("The most recent worker heartbeat is stale.")
        return SystemHealthResponse(
            status="ok" if not warnings else "degraded",
            database_ok=True,
            worker_online=worker_online,
            queue_depth=queue_depth,
            profiles_count=profiles_count,
            active_jobs=active_jobs,
            worker_count=worker_count,
            running_job_id=running_job_id,
            last_heartbeat=last_heartbeat,
            last_job_options=self.get_setting("last_job_options", {}),
            default_profile_id=self.get_setting("default_profile_id"),
            warnings=warnings,
            data_root=str(DATABASE_PATH.parent),
        )
