import { formatTimestamp } from "../lib/format";
import type { JobDetail, JobEvent, StreamState, SystemHealth } from "../types";
import { StatusPill } from "./StatusPill";

export function LogsPanel(props: {
  globalEvents: JobEvent[];
  selectedJob: JobDetail | null;
  selectedEvents: JobEvent[];
  health: SystemHealth | null;
  streamState: StreamState;
}) {
  const { globalEvents, selectedJob, selectedEvents, health, streamState } = props;

  return (
    <div className="panel-grid panel-grid--two">
      <section className="panel">
        <div className="section-heading">
          <div>
            <span className="eyebrow">System Logs</span>
            <h2>Recent backend events</h2>
          </div>
          {health ? <StatusPill tone={health.status} /> : null}
        </div>

        {globalEvents.length === 0 ? (
          <div className="empty-state">
            <h3>No events yet</h3>
            <p>The dashboard will display backend log entries once `/api/events` responds.</p>
          </div>
        ) : (
          <div className="event-list event-list--dense">
            {globalEvents.slice(0, 24).map((event, index) => (
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
      </section>

      <section className="panel">
        <div className="section-heading">
          <div>
            <span className="eyebrow">Job Feed</span>
            <h2>{selectedJob?.name ?? "Select a job from Queue or History"}</h2>
          </div>
          {selectedJob ? <StatusPill tone={selectedJob.status} /> : null}
        </div>

        <div className="subtle-copy">
          {streamState === "live"
            ? "Streaming directly from the selected job EventSource feed."
            : "Using snapshot polling or previously fetched events."}
        </div>

        {selectedEvents.length === 0 ? (
          <div className="empty-state">
            <h3>No selected job events</h3>
            <p>Pick a queued or completed job to inspect its event timeline here.</p>
          </div>
        ) : (
          <div className="event-list event-list--dense">
            {selectedEvents.slice(0, 24).map((event, index) => (
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
      </section>
    </div>
  );
}
