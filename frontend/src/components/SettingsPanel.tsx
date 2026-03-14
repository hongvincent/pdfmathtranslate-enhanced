import { formatDuration, formatTimestamp } from "../lib/format";
import type {
  DashboardPreferences,
  ProviderProfile,
  SystemHealth,
} from "../types";
import { StatusPill } from "./StatusPill";

const refreshOptions = [
  { label: "5 sec", value: 5000 },
  { label: "10 sec", value: 10000 },
  { label: "20 sec", value: 20000 },
  { label: "30 sec", value: 30000 },
];

export function SettingsPanel(props: {
  preferences: DashboardPreferences;
  onChange: (next: DashboardPreferences) => void;
  health: SystemHealth | null;
  profiles: ProviderProfile[];
}) {
  const { preferences, onChange, health, profiles } = props;

  return (
    <div className="panel-grid panel-grid--two">
      <section className="panel">
        <div className="section-heading">
          <div>
            <span className="eyebrow">Dashboard Settings</span>
            <h2>Operator preferences</h2>
          </div>
        </div>

        <div className="settings-list">
          <label className="settings-row">
            <div>
              <strong>Refresh cadence</strong>
              <small>Polling interval for jobs, health, and shared event feeds.</small>
            </div>
            <select
              value={preferences.refreshMs}
              onChange={(event) =>
                onChange({
                  ...preferences,
                  refreshMs: Number(event.target.value),
                })
              }
            >
              {refreshOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <label className="settings-row">
            <div>
              <strong>Prefer EventSource streaming</strong>
              <small>
                Connect to `/api/jobs/:id/events?stream=1` for active jobs when
                the backend supports SSE.
              </small>
            </div>
            <input
              type="checkbox"
              checked={preferences.preferEventStream}
              onChange={(event) =>
                onChange({
                  ...preferences,
                  preferEventStream: event.target.checked,
                })
              }
            />
          </label>

          <label className="settings-row">
            <div>
              <strong>Show artifact downloads</strong>
              <small>
                Keep download links visible in job detail panels once the backend
                reports output files.
              </small>
            </div>
            <input
              type="checkbox"
              checked={preferences.showCompletedArtifacts}
              onChange={(event) =>
                onChange({
                  ...preferences,
                  showCompletedArtifacts: event.target.checked,
                })
              }
            />
          </label>
        </div>
      </section>

      <section className="panel">
        <div className="section-heading">
          <div>
            <span className="eyebrow">Backend Health</span>
            <h2>{health?.version ?? "Waiting for backend"}</h2>
          </div>
          <StatusPill tone={health?.status ?? "offline"} />
        </div>

        <dl className="detail-grid">
          <div>
            <dt>Queue depth</dt>
            <dd>{health?.queueDepth ?? "n/a"}</dd>
          </div>
          <div>
            <dt>Active jobs</dt>
            <dd>{health?.activeJobs ?? "n/a"}</dd>
          </div>
          <div>
            <dt>Workers</dt>
            <dd>{health?.workerCount ?? "n/a"}</dd>
          </div>
          <div>
            <dt>Uptime</dt>
            <dd>{formatDuration(health?.uptimeSeconds)}</dd>
          </div>
          <div>
            <dt>Last heartbeat</dt>
            <dd>{formatTimestamp(health?.lastHeartbeat)}</dd>
          </div>
          <div>
            <dt>Profiles saved</dt>
            <dd>{profiles.length}</dd>
          </div>
        </dl>

        {health?.warnings.length ? (
          <div className="warning-stack">
            {health.warnings.map((warning) => (
              <div key={warning} className="warning-card">
                <StatusPill tone="warning" />
                <span>{warning}</span>
              </div>
            ))}
          </div>
        ) : (
          <p className="subtle-copy">
            No backend warnings were reported by the health endpoint.
          </p>
        )}
      </section>
    </div>
  );
}
