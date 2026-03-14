import type { JobEvent, JobStatus } from "../types";

type Tone = JobStatus | JobEvent["level"] | "ok" | "degraded" | "offline";

const toneLabels: Record<Tone, string> = {
  queued: "Queued",
  validating: "Validating",
  running: "Running",
  completed: "Completed",
  failed: "Failed",
  cancelled: "Cancelled",
  paused: "Paused",
  info: "Info",
  warning: "Warning",
  error: "Error",
  success: "Success",
  ok: "Healthy",
  degraded: "Degraded",
  offline: "Offline",
};

export function StatusPill(props: { tone: Tone }) {
  const { tone } = props;

  return (
    <span className={`status-pill status-pill--${tone}`}>
      {toneLabels[tone] ?? tone}
    </span>
  );
}
