from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated
from typing import Literal

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field


class ProviderType(str, Enum):
    OPENAI = "openai"
    BEDROCK = "bedrock"


class JobStatus(str, Enum):
    QUEUED = "queued"
    VALIDATING = "validating"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ArtifactKind(str, Enum):
    MONO_PDF = "mono_pdf"
    DUAL_PDF = "dual_pdf"
    GLOSSARY = "glossary"
    LOG = "log"


class OpenAIProfileInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_type: Literal[ProviderType.OPENAI] = ProviderType.OPENAI
    name: str
    base_url: str | None = None
    model: str = "gpt-5.4"
    snapshot_model: str = "gpt-5.4-2026-03-05"
    use_snapshot: bool = False
    reasoning_effort: str | None = "medium"
    temperature: float | None = None
    send_temperature: bool = False
    send_reasoning_effort: bool = True
    timeout_seconds: int | None = None
    api_key: str | None = None
    is_default: bool = False


class BedrockProfileInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_type: Literal[ProviderType.BEDROCK] = ProviderType.BEDROCK
    name: str
    region: str = "us-east-1"
    model_id: str = "amazon.nova-lite-v1:0"
    auth_mode: Literal["stored_keys", "mounted_aws_profile"] = "mounted_aws_profile"
    profile_name: str | None = None
    access_key_id: str | None = None
    secret_access_key: str | None = None
    session_token: str | None = None
    timeout_seconds: int | None = None
    temperature: float | None = None
    is_default: bool = False


ProviderProfileInput = Annotated[
    OpenAIProfileInput | BedrockProfileInput,
    Field(discriminator="provider_type"),
]


class ProviderProfileRecord(BaseModel):
    id: str
    provider_type: ProviderType
    name: str
    config: dict
    has_secret: bool
    is_default: bool = False
    validation_status: str | None = None
    validation_error: str | None = None
    validated_models: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class JobOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lang_in: str = "en"
    lang_out: str = "ko"
    pages: str | None = None
    qps: int = 4
    ignore_cache: bool = False
    no_mono: bool = False
    no_dual: bool = False
    dual_translate_first: bool = False
    use_alternating_pages_dual: bool = False
    translate_table_text: bool = True
    skip_scanned_detection: bool = False
    auto_enable_ocr_workaround: bool = False
    enhance_compatibility: bool = False
    custom_system_prompt: str | None = None
    no_auto_extract_glossary: bool = True
    save_auto_extracted_glossary: bool = False
    timeout_seconds: int = 3600


class JobCreatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_id: str
    options: JobOptions = Field(default_factory=JobOptions)


class JobArtifact(BaseModel):
    id: str
    kind: ArtifactKind
    file_name: str
    size_bytes: int
    created_at: datetime


class JobFileRecord(BaseModel):
    id: str
    original_name: str
    file_hash: str
    size_bytes: int
    page_count: int | None = None
    status: str
    artifacts: list[JobArtifact] = Field(default_factory=list)
    error_message: str | None = None


class JobEventRecord(BaseModel):
    id: int
    event_type: str
    level: str
    message: str
    created_at: datetime
    data: dict = Field(default_factory=dict)


class JobRecord(BaseModel):
    id: str
    status: JobStatus
    profile_id: str
    profile_name: str | None = None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
    error_details: str | None = None
    token_usage: dict = Field(default_factory=dict)
    overall_progress: float = 0.0
    current_step: str | None = None
    duplicate_of: str | None = None
    files: list[JobFileRecord] = Field(default_factory=list)


class JobSubmissionResponse(BaseModel):
    job: JobRecord
    duplicate: bool = False


class ProviderValidationResponse(BaseModel):
    ok: bool
    provider_type: ProviderType
    message: str
    validated_models: list[str] = Field(default_factory=list)


class SystemHealthResponse(BaseModel):
    status: str
    database_ok: bool
    worker_online: bool
    queue_depth: int
    profiles_count: int
    active_jobs: int = 0
    worker_count: int = 0
    running_job_id: str | None = None
    last_heartbeat: datetime | None = None
    last_job_options: dict = Field(default_factory=dict)
    default_profile_id: str | None = None
    warnings: list[str] = Field(default_factory=list)
    version: str = "enhanced-v1"
    uptime_seconds: int | None = None
    data_root: str
