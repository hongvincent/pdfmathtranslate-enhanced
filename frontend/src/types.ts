export type DashboardView =
  | "queue"
  | "new-job"
  | "profiles"
  | "history"
  | "logs"
  | "settings";

export type JobStatus =
  | "queued"
  | "validating"
  | "running"
  | "completed"
  | "failed"
  | "cancelled"
  | "paused";

export type OutputMode = "dual" | "mono" | "both";

export type StreamState = "idle" | "connecting" | "live" | "fallback";

export type EventLevel = "info" | "warning" | "error" | "success";

export type ProviderType = "openai" | "bedrock";

export type BedrockAuthMode = "stored_keys" | "mounted_aws_profile";

export interface ProviderProfile {
  id: string;
  name: string;
  providerType: ProviderType;
  provider: string;
  model?: string;
  snapshotModel?: string;
  useSnapshot?: boolean;
  baseUrl?: string;
  reasoningEffort?: string;
  timeoutSeconds?: number;
  temperature?: number;
  region?: string;
  modelId?: string;
  authMode?: BedrockAuthMode;
  profileName?: string;
  hasSecret?: boolean;
  isDefault?: boolean;
  validationStatus?: string;
  validationError?: string;
  validatedModels?: string[];
  createdAt?: string;
  updatedAt?: string;
}

export interface JobFile {
  name: string;
  sizeBytes?: number;
}

export interface JobArtifact {
  id: string;
  kind: string;
  label: string;
  filename: string;
  url: string;
  sizeBytes?: number;
  createdAt?: string;
}

export interface JobEvent {
  id?: string;
  type: string;
  level: EventLevel;
  message: string;
  timestamp: string;
  stage?: string;
  overallProgress?: number;
  partIndex?: number;
  totalParts?: number;
  details?: Record<string, unknown>;
}

export interface JobSummary {
  id: string;
  status: JobStatus;
  name: string;
  sourceLang: string;
  targetLang: string;
  profileId?: string;
  profileName?: string;
  queuePosition?: number;
  progress: number;
  currentStage?: string;
  createdAt?: string;
  startedAt?: string;
  updatedAt?: string;
  finishedAt?: string;
  files: JobFile[];
  artifactCount: number;
  error?: string;
  tokenUsage?: Record<string, unknown>;
  duplicateOf?: string;
}

export interface JobDetail extends JobSummary {
  artifacts: JobArtifact[];
  recentEvents: JobEvent[];
  outputMode?: OutputMode;
  pages?: string;
  saveGlossary?: boolean;
}

export interface SystemHealth {
  status: "ok" | "degraded" | "offline";
  version?: string;
  queueDepth?: number;
  activeJobs?: number;
  workerCount?: number;
  uptimeSeconds?: number;
  lastHeartbeat?: string;
  workerOnline?: boolean;
  databaseOk?: boolean;
  defaultProfileId?: string;
  lastJobOptions?: Record<string, unknown>;
  dataRoot?: string;
  warnings: string[];
}

export interface NewJobInput {
  files: File[];
  profileId?: string;
  sourceLang: string;
  targetLang: string;
  outputMode: OutputMode;
  pages?: string;
  qps?: number;
  saveGlossary: boolean;
}

export interface ProfileDraft {
  id?: string;
  name: string;
  providerType: ProviderType;
  isDefault?: boolean;
  model?: string;
  snapshotModel?: string;
  useSnapshot?: boolean;
  baseUrl?: string;
  apiKey?: string;
  reasoningEffort?: string;
  timeoutSeconds?: number;
  temperature?: number;
  region?: string;
  modelId?: string;
  authMode?: BedrockAuthMode;
  profileName?: string;
  accessKeyId?: string;
  secretAccessKey?: string;
  sessionToken?: string;
}

export interface DashboardPreferences {
  refreshMs: number;
  preferEventStream: boolean;
  showCompletedArtifacts: boolean;
}
