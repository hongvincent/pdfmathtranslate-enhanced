import {
  formatBytes,
  formatRelativeTime,
  formatTimestamp,
} from "../lib/format";
import type { JobArtifact, JobDetail, JobEvent, StreamState } from "../types";
import { StatusPill } from "./StatusPill";

export function JobInspector(props: {
  job: JobDetail | null;
  artifacts: JobArtifact[];
  events: JobEvent[];
  streamState: StreamState;
  emptyMessage: string;
  showArtifacts: boolean;
  cancellingJobId: string | null;
  retryingJobId: string | null;
  onCancel: (jobId: string) => Promise<void>;
  onRetry: (jobId: string) => Promise<void>;
}) {
  const {
    job,
    artifacts,
    events,
    streamState,
    emptyMessage,
    showArtifacts,
    cancellingJobId,
    retryingJobId,
    onCancel,
    onRetry,
  } = props;

  if (!job) {
    return (
      <section className="panel">
        <div className="empty-state">
          <h3>Select a job</h3>
          <p>{emptyMessage}</p>
        </div>
      </section>
    );
  }

  return (
    <section className="panel panel--sticky">
      <div className="section-heading">
        <div>
          <span className="eyebrow">Job Detail</span>
          <h2>{job.name}</h2>
        </div>
        <div className="profile-card__actions">
          <StatusPill tone={job.status} />
          {job.status === "queued" || job.status === "validating" || job.status === "running" ? (
            <button
              type="button"
              className="ghost-button"
              onClick={() => void onCancel(job.id)}
              disabled={cancellingJobId === job.id}
            >
              {cancellingJobId === job.id ? "Cancelling..." : "Cancel"}
            </button>
          ) : null}
          {job.status === "failed" || job.status === "cancelled" || job.status === "completed" ? (
            <button
              type="button"
              className="ghost-button"
              onClick={() => void onRetry(job.id)}
              disabled={retryingJobId === job.id}
            >
              {retryingJobId === job.id ? "Retrying..." : "Retry"}
            </button>
          ) : null}
        </div>
      </div>

      <div className="job-hero">
        <div className="job-hero__progress">
          <div className="progress-bar progress-bar--large">
            <span style={{ width: `${job.progress}%` }} />
          </div>
          <strong>{Math.round(job.progress)}% complete</strong>
          <small>{job.currentStage ?? "Waiting for backend updates."}</small>
        </div>
        <div className="job-hero__stream">
          <span className="eyebrow">Live feed</span>
          <strong>{streamState === "live" ? "EventSource connected" : "Polling snapshot mode"}</strong>
        </div>
      </div>

      <dl className="detail-grid">
        <div>
          <dt>Profile</dt>
          <dd>{job.profileName ?? "Manual"}</dd>
        </div>
        <div>
          <dt>Queue position</dt>
          <dd>{job.queuePosition ?? "n/a"}</dd>
        </div>
        <div>
          <dt>Languages</dt>
          <dd>
            {job.sourceLang} to {job.targetLang}
          </dd>
        </div>
        <div>
          <dt>Created</dt>
          <dd>{formatTimestamp(job.createdAt)}</dd>
        </div>
        <div>
          <dt>Updated</dt>
          <dd>{formatRelativeTime(job.updatedAt ?? job.createdAt)}</dd>
        </div>
        <div>
          <dt>Pages</dt>
          <dd>{job.pages ?? "full document"}</dd>
        </div>
      </dl>

      {job.tokenUsage && Object.keys(job.tokenUsage).length > 0 ? (
        <div className="stack-block">
          <span className="eyebrow">Token Usage</span>
          <pre className="subtle-copy">{JSON.stringify(job.tokenUsage, null, 2)}</pre>
        </div>
      ) : null}

      <div className="stack-block">
        <span className="eyebrow">Input Files</span>
        <div className="card-list card-list--compact">
          {job.files.map((file) => (
            <div key={file.name} className="list-row">
              <strong>{file.name}</strong>
              <small>{formatBytes(file.sizeBytes)}</small>
            </div>
          ))}
        </div>
      </div>

      {showArtifacts ? (
        <div className="stack-block">
          <span className="eyebrow">Artifacts</span>
          {artifacts.length === 0 ? (
            <p className="subtle-copy">No downloadable outputs reported yet.</p>
          ) : (
            <div className="card-list card-list--compact">
              {artifacts.map((artifact) => (
                <a
                  key={artifact.id}
                  className="artifact-link"
                  href={artifact.url}
                  target="_blank"
                  rel="noreferrer"
                >
                  <div>
                    <strong>{artifact.label}</strong>
                    <small>{artifact.filename}</small>
                  </div>
                  <small>{formatBytes(artifact.sizeBytes)}</small>
                </a>
              ))}
            </div>
          )}
        </div>
      ) : null}

      <div className="stack-block">
        <span className="eyebrow">Recent Events</span>
        {events.length === 0 ? (
          <p className="subtle-copy">The backend has not published any job events yet.</p>
        ) : (
          <div className="event-list">
            {events.slice(0, 10).map((event, index) => (
              <div key={`${event.id ?? event.timestamp}-${index}`} className="event-row">
                <div className="event-row__meta">
                  <StatusPill tone={event.level} />
                  <small>{formatTimestamp(event.timestamp)}</small>
                </div>
                <strong>{event.message}</strong>
                {event.stage ? <small>{event.stage}</small> : null}
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
