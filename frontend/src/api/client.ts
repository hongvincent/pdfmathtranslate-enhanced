import { clampProgress } from "../lib/format";
import type {
  JobArtifact,
  JobDetail,
  JobEvent,
  JobStatus,
  JobSummary,
  NewJobInput,
  ProfileDraft,
  ProviderProfile,
  SystemHealth,
} from "../types";

const API_BASE = "/api";

type JsonRecord = Record<string, unknown>;

function isRecord(value: unknown): value is JsonRecord {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function readValue<T>(source: JsonRecord, ...keys: string[]): T | undefined {
  for (const key of keys) {
    const value = source[key];
    if (value !== undefined && value !== null) {
      return value as T;
    }
  }

  return undefined;
}

function readNestedRecord(source: JsonRecord, key: string): JsonRecord | undefined {
  const value = source[key];
  return isRecord(value) ? value : undefined;
}

function readString(source: JsonRecord, ...keys: string[]): string | undefined {
  const value = readValue<unknown>(source, ...keys);
  if (typeof value === "string") {
    return value;
  }

  if (typeof value === "number") {
    return String(value);
  }

  return undefined;
}

function readNumber(source: JsonRecord, ...keys: string[]): number | undefined {
  const value = readValue<unknown>(source, ...keys);
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }

  if (typeof value === "string" && value.trim().length > 0) {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }

  return undefined;
}

function readBoolean(source: JsonRecord, ...keys: string[]): boolean | undefined {
  const value = readValue<unknown>(source, ...keys);
  if (typeof value === "boolean") {
    return value;
  }

  if (typeof value === "string") {
    if (value === "true") {
      return true;
    }

    if (value === "false") {
      return false;
    }
  }

  return undefined;
}

function readArray<T = unknown>(
  source: JsonRecord,
  ...keys: string[]
): T[] | undefined {
  const value = readValue<unknown>(source, ...keys);
  if (Array.isArray(value)) {
    return value as T[];
  }

  return undefined;
}

function getListEnvelope(payload: unknown, keys: string[]): unknown[] {
  if (Array.isArray(payload)) {
    return payload;
  }

  if (!isRecord(payload)) {
    return [];
  }

  for (const key of keys) {
    const value = payload[key];
    if (Array.isArray(value)) {
      return value;
    }
  }

  return [];
}

function inferEventLevel(type?: string, error?: string): JobEvent["level"] {
  if (error || type === "error" || type === "failed") {
    return "error";
  }

  if (type === "finish" || type === "completed") {
    return "success";
  }

  if (type === "warning" || type === "cancelled") {
    return "warning";
  }

  return "info";
}

function basename(path: string): string {
  const parts = path.split(/[\\/]/);
  return parts[parts.length - 1] ?? path;
}

function isPdfFile(file: File): boolean {
  const lowerName = file.name.toLowerCase();
  return lowerName.endsWith(".pdf") || file.type === "application/pdf";
}

function normalizeFiles(payload: JsonRecord) {
  const files = readArray<unknown>(payload, "files");
  if (!files?.length) {
    return [];
  }

  return files.map((item, index) => {
    if (!isRecord(item)) {
      return { name: `file-${index + 1}.pdf` };
    }

    return {
      name:
        readString(item, "name", "original_name", "filename") ??
        `file-${index + 1}.pdf`,
      sizeBytes: readNumber(item, "size_bytes", "sizeBytes", "size"),
    };
  });
}

function normalizeArtifact(item: unknown, index = 0): JobArtifact | null {
  if (!isRecord(item)) {
    return null;
  }

  const url = readString(item, "url", "download_url", "href");
  const filename =
    readString(item, "filename", "file_name", "name", "path") ??
    (url ? basename(url) : `artifact-${index + 1}`);

  return {
    id: readString(item, "id", "artifact_id") ?? `artifact-${index + 1}`,
    kind: readString(item, "kind", "type") ?? "output",
    label: readString(item, "label", "title") ?? filename,
    filename,
    url: url ?? "#",
    sizeBytes: readNumber(item, "size_bytes", "sizeBytes", "size"),
    createdAt: readString(item, "created_at", "createdAt"),
  };
}

export function normalizeEvent(item: unknown): JobEvent | null {
  if (!isRecord(item)) {
    return null;
  }

  const type = readString(item, "type", "event_type") ?? "event";
  const details = readNestedRecord(item, "details");
  const error = readString(item, "error");
  const progress = clampProgress(
    readNumber(
      item,
      "overall_progress",
      "overallProgress",
      "progress",
    ),
  );
  const message =
    readString(item, "message", "detail") ??
    error ??
    readString(item, "stage", "current_step") ??
    type;

  return {
    id: readString(item, "id", "event_id"),
    type,
    level:
      (readString(item, "level", "severity") as JobEvent["level"] | undefined) ??
      inferEventLevel(type, error),
    message,
    timestamp:
      readString(item, "timestamp", "created_at", "createdAt", "time") ??
      new Date().toISOString(),
    stage: readString(item, "stage", "current_step"),
    overallProgress:
      progress > 0 || type === "progress" || type === "completed"
        ? progress
        : undefined,
    partIndex: readNumber(item, "part_index", "partIndex"),
    totalParts: readNumber(item, "total_parts", "totalParts"),
    details,
  };
}

function normalizeProfile(item: unknown, index = 0): ProviderProfile | null {
  if (!isRecord(item)) {
    return null;
  }

  const config = readNestedRecord(item, "config") ?? {};
  const providerType =
    readString(item, "provider_type", "providerType") ?? "openai";

  return {
    id: readString(item, "id", "profile_id", "name") ?? `profile-${index + 1}`,
    name: readString(item, "name", "label") ?? `Profile ${index + 1}`,
    providerType: providerType === "bedrock" ? "bedrock" : "openai",
    provider:
      readString(item, "provider") ??
      (providerType === "bedrock" ? "Bedrock" : "OpenAI"),
    model:
      readString(item, "model") ??
      readString(config, "model"),
    snapshotModel:
      readString(item, "snapshot_model", "snapshotModel") ??
      readString(config, "snapshot_model"),
    useSnapshot:
      readBoolean(item, "use_snapshot", "useSnapshot") ??
      readBoolean(config, "use_snapshot"),
    baseUrl:
      readString(item, "base_url", "baseUrl") ??
      readString(config, "base_url"),
    reasoningEffort:
      readString(item, "reasoning_effort", "reasoningEffort") ??
      readString(config, "reasoning_effort"),
    timeoutSeconds:
      readNumber(item, "timeout_seconds", "timeoutSeconds") ??
      readNumber(config, "timeout_seconds"),
    temperature:
      readNumber(item, "temperature") ??
      readNumber(config, "temperature"),
    region:
      readString(item, "region") ??
      readString(config, "region"),
    modelId:
      readString(item, "model_id", "modelId") ??
      readString(config, "model_id"),
    authMode:
      (readString(item, "auth_mode", "authMode") ??
        readString(config, "auth_mode")) as ProviderProfile["authMode"],
    profileName:
      readString(item, "profile_name", "profileName") ??
      readString(config, "profile_name"),
    hasSecret: readBoolean(item, "has_secret", "hasSecret"),
    isDefault: readBoolean(item, "is_default", "isDefault"),
    validationStatus: readString(item, "validation_status", "validationStatus"),
    validationError: readString(item, "validation_error", "validationError"),
    validatedModels:
      readArray<unknown>(item, "validated_models", "validatedModels")?.filter(
        (value): value is string => typeof value === "string",
      ) ?? [],
    createdAt: readString(item, "created_at", "createdAt"),
    updatedAt: readString(item, "updated_at", "updatedAt"),
  };
}

function normalizeJob(item: unknown, index = 0): JobSummary | null {
  if (!isRecord(item)) {
    return null;
  }

  const files = normalizeFiles(item);
  const status =
    (readString(item, "status", "state") as JobStatus | undefined) ?? "queued";
  const progress = clampProgress(
    readNumber(item, "progress", "overall_progress", "overallProgress"),
  );

  return {
    id: readString(item, "id", "job_id") ?? `job-${index + 1}`,
    status,
    name:
      readString(item, "name", "title") ??
      files[0]?.name ??
      `Job ${index + 1}`,
    sourceLang: readString(item, "source_lang", "sourceLang", "lang_in") ?? "en",
    targetLang: readString(item, "target_lang", "targetLang", "lang_out") ?? "ko",
    profileId: readString(item, "profile_id", "profileId"),
    profileName: readString(item, "profile_name", "profileName"),
    queuePosition: readNumber(item, "queue_position", "queuePosition"),
    progress,
    currentStage: readString(item, "current_stage", "currentStage", "current_step"),
    createdAt: readString(item, "created_at", "createdAt"),
    startedAt: readString(item, "started_at", "startedAt"),
    updatedAt: readString(item, "updated_at", "updatedAt"),
    finishedAt: readString(item, "finished_at", "finishedAt", "completed_at"),
    files,
    artifactCount:
      readNumber(item, "artifact_count", "artifactCount") ??
      readArray(item, "artifacts")?.length ??
      0,
    error: readString(item, "error", "error_message", "errorMessage"),
    tokenUsage:
      (readValue<Record<string, unknown>>(item, "token_usage", "tokenUsage") ?? {}),
    duplicateOf: readString(item, "duplicate_of", "duplicateOf"),
  };
}

function normalizeJobDetail(payload: unknown): JobDetail {
  const base = normalizeJob(payload, 0) ?? {
    id: "unknown",
    status: "queued" as JobStatus,
    name: "Unknown job",
    sourceLang: "en",
    targetLang: "ko",
    progress: 0,
    files: [],
    artifactCount: 0,
  };

  const record = isRecord(payload) ? payload : {};
  const artifacts = getListEnvelope(record, ["artifacts"])
    .map((item, index) => normalizeArtifact(item, index))
    .filter((item): item is JobArtifact => item !== null);
  const recentEvents = getListEnvelope(record, ["recent_events", "events"])
    .map((item) => normalizeEvent(item))
    .filter((item): item is JobEvent => item !== null);

  return {
    ...base,
    artifacts,
    recentEvents,
    outputMode:
      (readString(record, "output_mode", "outputMode") as JobDetail["outputMode"]) ??
      undefined,
    pages: readString(record, "pages"),
    saveGlossary: readBoolean(record, "save_glossary", "saveGlossary"),
  };
}

function normalizeHealth(payload: unknown): SystemHealth {
  if (!isRecord(payload)) {
    return {
      status: "offline",
      warnings: ["Health endpoint did not return a JSON object."],
    };
  }

  return {
    status:
      (readString(payload, "status") as SystemHealth["status"] | undefined) ??
      "ok",
    version: readString(payload, "version"),
    queueDepth: readNumber(payload, "queue_depth", "queueDepth"),
    activeJobs: readNumber(payload, "active_jobs", "activeJobs"),
    workerCount: readNumber(payload, "worker_count", "workerCount"),
    uptimeSeconds: readNumber(payload, "uptime_seconds", "uptimeSeconds"),
    lastHeartbeat: readString(
      payload,
      "last_heartbeat",
      "lastHeartbeat",
      "timestamp",
    ),
    workerOnline: readBoolean(payload, "worker_online", "workerOnline"),
    databaseOk: readBoolean(payload, "database_ok", "databaseOk"),
    defaultProfileId: readString(payload, "default_profile_id", "defaultProfileId"),
    lastJobOptions:
      readValue<Record<string, unknown>>(
        payload,
        "last_job_options",
        "lastJobOptions",
      ) ?? {},
    dataRoot: readString(payload, "data_root", "dataRoot"),
    warnings:
      readArray<unknown>(payload, "warnings")?.filter(
        (warning): warning is string => typeof warning === "string",
      ) ?? [],
  };
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (!(init?.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  headers.set("Accept", "application/json");

  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers,
  });

  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const payload = await response.json();
      if (isRecord(payload)) {
        message = readString(payload, "detail", "message", "error") ?? message;
      }
    } catch {
      const text = await response.text();
      if (text.trim().length > 0) {
        message = text;
      }
    }
    throw new Error(message);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

function mapProfileDraftToPayload(profile: ProfileDraft): Record<string, unknown> {
  if (profile.providerType === "bedrock") {
    return {
      provider_type: "bedrock",
      name: profile.name,
      region: profile.region || "us-east-1",
      model_id: profile.modelId || "amazon.nova-lite-v1:0",
      auth_mode: profile.authMode || "mounted_aws_profile",
      profile_name: profile.profileName || null,
      access_key_id: profile.accessKeyId || null,
      secret_access_key: profile.secretAccessKey || null,
      session_token: profile.sessionToken || null,
      timeout_seconds: profile.timeoutSeconds ?? null,
      temperature: profile.temperature ?? null,
      is_default: Boolean(profile.isDefault),
    };
  }

  return {
    provider_type: "openai",
    name: profile.name,
    base_url: profile.baseUrl || null,
    model: profile.model || "gpt-5.4",
    snapshot_model: profile.snapshotModel || "gpt-5.4-2026-03-05",
    use_snapshot: Boolean(profile.useSnapshot),
    reasoning_effort: profile.reasoningEffort || "medium",
    temperature: profile.temperature ?? null,
    timeout_seconds: profile.timeoutSeconds ?? null,
    api_key: profile.apiKey || null,
    is_default: Boolean(profile.isDefault),
  };
}

function dedupeEvents(events: JobEvent[]): JobEvent[] {
  const seen = new Set<string>();
  return [...events]
    .sort(
      (left, right) =>
        new Date(right.timestamp).getTime() - new Date(left.timestamp).getTime(),
    )
    .filter((event) => {
      const key = `${event.id ?? ""}:${event.timestamp}:${event.type}:${event.message}`;
      if (seen.has(key)) {
        return false;
      }
      seen.add(key);
      return true;
    });
}

export const api = {
  async listJobs(): Promise<JobSummary[]> {
    const payload = await request<unknown>("/jobs");
    return getListEnvelope(payload, ["jobs", "items"])
      .map((item, index) => normalizeJob(item, index))
      .filter((item): item is JobSummary => item !== null);
  },

  async getJob(jobId: string): Promise<JobDetail> {
    const payload = await request<unknown>(`/jobs/${jobId}`);
    return normalizeJobDetail(payload);
  },

  async listProfiles(): Promise<ProviderProfile[]> {
    const payload = await request<unknown>("/provider-profiles");
    return getListEnvelope(payload, ["profiles", "items"])
      .map((item, index) => normalizeProfile(item, index))
      .filter((item): item is ProviderProfile => item !== null);
  },

  async createProfile(profile: ProfileDraft): Promise<ProviderProfile> {
    const payload = await request<unknown>("/provider-profiles", {
      method: "POST",
      body: JSON.stringify(mapProfileDraftToPayload(profile)),
    });
    return normalizeProfile(payload, 0) ?? {
      id: profile.id ?? profile.name,
      name: profile.name,
      providerType: profile.providerType,
      provider: profile.providerType === "bedrock" ? "Bedrock" : "OpenAI",
      model: profile.model,
      modelId: profile.modelId,
      isDefault: profile.isDefault,
    };
  },

  async updateProfile(profileId: string, profile: ProfileDraft): Promise<ProviderProfile> {
    const payload = await request<unknown>(`/provider-profiles/${profileId}`, {
      method: "PATCH",
      body: JSON.stringify(mapProfileDraftToPayload(profile)),
    });
    return normalizeProfile(payload, 0) ?? {
      id: profileId,
      name: profile.name,
      providerType: profile.providerType,
      provider: profile.providerType === "bedrock" ? "Bedrock" : "OpenAI",
      model: profile.model,
      modelId: profile.modelId,
      isDefault: profile.isDefault,
    };
  },

  async deleteProfile(profileId: string): Promise<void> {
    await request<void>(`/provider-profiles/${profileId}`, { method: "DELETE" });
  },

  async validateProfile(profileId: string): Promise<ProviderProfile> {
    const payload = await request<unknown>(`/provider-profiles/${profileId}/validate`, {
      method: "POST",
    });

    if (isRecord(payload)) {
      return {
        id: profileId,
        name: "",
        providerType:
          readString(payload, "provider_type") === "bedrock" ? "bedrock" : "openai",
        provider:
          readString(payload, "provider_type") === "bedrock" ? "Bedrock" : "OpenAI",
        validationStatus: readBoolean(payload, "ok") ? "ok" : "error",
        validationError: readString(payload, "message"),
        validatedModels:
          readArray<unknown>(payload, "validated_models")?.filter(
            (value): value is string => typeof value === "string",
          ) ?? [],
      };
    }

    throw new Error("Unexpected validation response.");
  },

  async createJob(input: NewJobInput): Promise<JobDetail | null> {
    if (!input.profileId) {
      throw new Error("Choose a provider profile before queueing a job.");
    }

    const invalidFiles = input.files.filter((file) => !isPdfFile(file));
    if (invalidFiles.length > 0) {
      const names = invalidFiles.map((file) => file.name).join(", ");
      throw new Error(
        `${names} ${invalidFiles.length === 1 ? "is" : "are"} not supported. Convert DOCX or other formats to PDF before queueing them.`,
      );
    }

    const payload = {
      profile_id: input.profileId,
      options: {
        lang_in: input.sourceLang,
        lang_out: input.targetLang,
        pages: input.pages ?? null,
        qps: input.qps ?? 4,
        no_mono: input.outputMode === "dual",
        no_dual: input.outputMode === "mono",
        no_auto_extract_glossary: !input.saveGlossary,
        save_auto_extracted_glossary: input.saveGlossary,
      },
    };

    const formData = new FormData();
    input.files.forEach((file) => formData.append("files", file));
    formData.append("payload", JSON.stringify(payload));

    const response = await request<unknown>("/jobs", {
      method: "POST",
      body: formData,
    });

    if (isRecord(response) && isRecord(response.job)) {
      return normalizeJobDetail(response.job);
    }

    return isRecord(response) ? normalizeJobDetail(response) : null;
  },

  async cancelJob(jobId: string): Promise<JobDetail> {
    const payload = await request<unknown>(`/jobs/${jobId}/cancel`, {
      method: "POST",
    });
    return normalizeJobDetail(payload);
  },

  async retryJob(jobId: string): Promise<JobDetail> {
    const payload = await request<unknown>(`/jobs/${jobId}/retry`, {
      method: "POST",
    });
    return normalizeJobDetail(payload);
  },

  async listJobArtifacts(jobId: string): Promise<JobArtifact[]> {
    const payload = await request<unknown>(`/jobs/${jobId}/artifacts`);
    return getListEnvelope(payload, ["artifacts", "items"])
      .map((item, index) => normalizeArtifact(item, index))
      .filter((item): item is JobArtifact => item !== null);
  },

  async listJobEvents(jobId: string, limit = 120): Promise<JobEvent[]> {
    const payload = await request<unknown>(`/jobs/${jobId}/events?limit=${limit}`);
    return dedupeEvents(
      getListEnvelope(payload, ["events", "items"])
        .map((item) => normalizeEvent(item))
        .filter((item): item is JobEvent => item !== null),
    );
  },

  streamJobEvents(jobId: string): EventSource {
    return new EventSource(`${API_BASE}/jobs/${jobId}/events?stream=1`);
  },

  async listEvents(limit = 160): Promise<JobEvent[]> {
    const payload = await request<unknown>(`/events?limit=${limit}`);
    return dedupeEvents(
      getListEnvelope(payload, ["events", "items"])
        .map((item) => normalizeEvent(item))
        .filter((item): item is JobEvent => item !== null),
    );
  },

  async getHealth(): Promise<SystemHealth> {
    const payload = await request<unknown>("/system/health");
    return normalizeHealth(payload);
  },
};
