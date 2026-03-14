import type { DashboardView, SystemHealth } from "../types";
import { StatusPill } from "./StatusPill";

const items: Array<{ id: DashboardView; label: string; helper: string }> = [
  { id: "queue", label: "Queue", helper: "Live throughput" },
  { id: "new-job", label: "New Job", helper: "Launch translations" },
  { id: "profiles", label: "Profiles", helper: "Provider presets" },
  { id: "history", label: "History", helper: "Completed work" },
  { id: "logs", label: "Logs", helper: "Events and traces" },
  { id: "settings", label: "Settings", helper: "Dashboard controls" },
];

export function Sidebar(props: {
  activeView: DashboardView;
  onChange: (view: DashboardView) => void;
  queueCount: number;
  historyCount: number;
  profileCount: number;
  health: SystemHealth | null;
}) {
  const { activeView, onChange, queueCount, historyCount, profileCount, health } = props;

  return (
    <aside className="sidebar">
      <div className="sidebar__brand">
        <span className="eyebrow">PDFMathTranslate</span>
        <h1>Control Room</h1>
        <p>
          Single-operator dashboard for staged PDF translation, provider tuning,
          and live event visibility.
        </p>
      </div>

      <nav className="sidebar__nav" aria-label="Primary">
        {items.map((item) => (
          <button
            key={item.id}
            type="button"
            className={`nav-item ${activeView === item.id ? "nav-item--active" : ""}`}
            onClick={() => onChange(item.id)}
          >
            <span>{item.label}</span>
            <small>{item.helper}</small>
          </button>
        ))}
      </nav>

      <div className="sidebar__meta">
        <div>
          <span className="eyebrow">Queue</span>
          <strong>{queueCount}</strong>
        </div>
        <div>
          <span className="eyebrow">History</span>
          <strong>{historyCount}</strong>
        </div>
        <div>
          <span className="eyebrow">Profiles</span>
          <strong>{profileCount}</strong>
        </div>
      </div>

      <div className="sidebar__health">
        <div>
          <span className="eyebrow">Backend</span>
          <h2>{health?.version ?? "Awaiting handshake"}</h2>
        </div>
        <StatusPill tone={health?.status ?? "offline"} />
      </div>
    </aside>
  );
}
