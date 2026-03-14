import { formatRelativeTime } from "../lib/format";
import type { JobSummary } from "../types";
import { StatusPill } from "./StatusPill";

export function JobTable(props: {
  jobs: JobSummary[];
  title: string;
  subtitle: string;
  selectedJobId: string | null;
  onSelect: (jobId: string) => void;
  emptyMessage: string;
}) {
  const { jobs, title, subtitle, selectedJobId, onSelect, emptyMessage } = props;

  return (
    <section className="panel">
      <div className="section-heading">
        <div>
          <span className="eyebrow">{title}</span>
          <h2>{subtitle}</h2>
        </div>
        <div className="section-heading__meta">{jobs.length} jobs</div>
      </div>

      {jobs.length === 0 ? (
        <div className="empty-state">
          <h3>No jobs here yet</h3>
          <p>{emptyMessage}</p>
        </div>
      ) : (
        <div className="table-shell">
          <table className="data-table">
            <thead>
              <tr>
                <th>Document</th>
                <th>Status</th>
                <th>Progress</th>
                <th>Profile</th>
                <th>Updated</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((job) => (
                <tr
                  key={job.id}
                  className={selectedJobId === job.id ? "is-selected" : ""}
                  onClick={() => onSelect(job.id)}
                >
                  <td>
                    <button
                      type="button"
                      className="row-button"
                      onClick={() => onSelect(job.id)}
                    >
                      <strong>{job.name}</strong>
                      <small>
                        {job.files.length > 1
                          ? `${job.files.length} PDFs`
                          : job.files[0]?.name ?? "Unnamed input"}
                      </small>
                    </button>
                  </td>
                  <td>
                    <StatusPill tone={job.status} />
                  </td>
                  <td>
                    <div className="progress-inline">
                      <div className="progress-bar">
                        <span style={{ width: `${job.progress}%` }} />
                      </div>
                      <small>
                        {Math.round(job.progress)}%{job.currentStage ? ` · ${job.currentStage}` : ""}
                      </small>
                    </div>
                  </td>
                  <td>
                    <strong>{job.profileName ?? "Manual"}</strong>
                    <small>
                      {job.sourceLang} to {job.targetLang}
                    </small>
                  </td>
                  <td>{formatRelativeTime(job.updatedAt ?? job.createdAt)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
