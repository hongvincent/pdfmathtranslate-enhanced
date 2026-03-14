import { startTransition, useEffect, useState } from "react";
import { MetricCard } from "./components/MetricCard";
import { JobInspector } from "./components/JobInspector";
import { JobTable } from "./components/JobTable";
import { LogsPanel } from "./components/LogsPanel";
import { NewJobForm } from "./components/NewJobForm";
import { ProfileManager } from "./components/ProfileManager";
import { SettingsPanel } from "./components/SettingsPanel";
import { Sidebar } from "./components/Sidebar";
import { StatusPill } from "./components/StatusPill";
import {
  formatCompactNumber,
  formatRelativeTime,
} from "./lib/format";
import { useDashboardData } from "./hooks/useDashboardData";
import type {
  DashboardPreferences,
  DashboardView,
} from "./types";

const preferencesKey = "pdfmathtranslate-control-room.preferences";

const defaultPreferences: DashboardPreferences = {
  refreshMs: 10000,
  preferEventStream: true,
  showCompletedArtifacts: true,
};

const heroCopy: Record<
  DashboardView,
  { title: string; subtitle: string }
> = {
  queue: {
    title: "Queue and execution flow",
    subtitle: "Watch active translations, current throughput, and the live selected job feed.",
  },
  "new-job": {
    title: "Launch a new translation batch",
    subtitle: "Upload one or many PDFs, pick a provider preset, and send the batch to `/api/jobs`.",
  },
  profiles: {
    title: "Curate provider presets",
    subtitle: "Manage backend-side model profiles so new jobs stay repeatable and easy to queue.",
  },
  history: {
    title: "Review completed output",
    subtitle: "Inspect finished, failed, or cancelled work alongside any generated artifacts.",
  },
  logs: {
    title: "Trace the system",
    subtitle: "Combine system event history with a selected job's detailed event stream.",
  },
  settings: {
    title: "Tune the dashboard",
    subtitle: "Control polling cadence, event streaming preferences, and health visibility.",
  },
};

function loadPreferences(): DashboardPreferences {
  try {
    const saved = window.localStorage.getItem(preferencesKey);
    if (!saved) {
      return defaultPreferences;
    }

    return {
      ...defaultPreferences,
      ...(JSON.parse(saved) as Partial<DashboardPreferences>),
    };
  } catch {
    return defaultPreferences;
  }
}

function App() {
  const [activeView, setActiveView] = useState<DashboardView>("queue");
  const [preferences, setPreferences] = useState<DashboardPreferences>(loadPreferences);
  const [notice, setNotice] = useState<string | null>(null);

  const dashboard = useDashboardData({
    refreshMs: preferences.refreshMs,
    preferEventStream: preferences.preferEventStream,
  });

  const {
    jobs,
    profiles,
    health,
    globalEvents,
    selectedJobId,
    selectedJob,
    selectedArtifacts,
    selectedEvents,
    streamState,
    loading,
    refreshing,
    lastSyncedAt,
    error,
    actionState,
    setSelectedJobId,
    refreshAll,
    createJob,
    saveProfile,
    validateProfile,
    deleteProfile,
    cancelJob,
    retryJob,
  } = dashboard;

  useEffect(() => {
    window.localStorage.setItem(preferencesKey, JSON.stringify(preferences));
  }, [preferences]);

  const queueJobs = jobs.filter(
    (job) =>
      job.status === "queued" ||
      job.status === "validating" ||
      job.status === "running" ||
      job.status === "paused",
  );
  const historyJobs = jobs.filter((job) => !queueJobs.some((liveJob) => liveJob.id === job.id));
  const completedJobs = jobs.filter((job) => job.status === "completed").length;
  const failedJobs = jobs.filter((job) => job.status === "failed").length;
  const queueDepth = health?.queueDepth ?? queueJobs.length;
  const successRate = jobs.length === 0 ? 0 : Math.round((completedJobs / jobs.length) * 100);
  const hero = heroCopy[activeView];

  async function handleCreateJob(input: Parameters<typeof createJob>[0]) {
    const created = await createJob(input);
    if (!created) {
      return;
    }

    startTransition(() => {
      setActiveView("queue");
      if (created.id) {
        setSelectedJobId(created.id);
      }
    });
    setNotice(`Queued ${input.files.length} PDF${input.files.length > 1 ? "s" : ""} for translation.`);
  }

  async function handleSaveProfile(input: Parameters<typeof saveProfile>[0]) {
    const profile = await saveProfile(input);
    if (profile) {
      setNotice(`Saved provider profile "${profile.name}".`);
      startTransition(() => {
        setActiveView("profiles");
      });
    }
  }

  async function handleDeleteProfile(profileId: string) {
    const didDelete = await deleteProfile(profileId);
    if (didDelete) {
      setNotice("Deleted provider profile.");
    }
  }

  async function handleValidateProfile(profileId: string) {
    const validated = await validateProfile(profileId);
    if (validated) {
      setNotice("Validated provider profile credentials.");
    }
  }

  async function handleCancelJob(jobId: string) {
    const job = await cancelJob(jobId);
    if (job) {
      setNotice(`Cancellation requested for ${job.name}.`);
    }
  }

  async function handleRetryJob(jobId: string) {
    const job = await retryJob(jobId);
    if (job) {
      setNotice(`Queued retry for ${job.name}.`);
      startTransition(() => {
        setActiveView("queue");
      });
    }
  }

  return (
    <div className="app-shell">
      <Sidebar
        activeView={activeView}
        onChange={setActiveView}
        queueCount={queueJobs.length}
        historyCount={historyJobs.length}
        profileCount={profiles.length}
        health={health}
      />

      <main className="main-panel">
        <header className="hero">
          <div className="hero__copy">
            <span className="eyebrow">Single-user dashboard</span>
            <h2>{hero.title}</h2>
            <p>{hero.subtitle}</p>
          </div>

          <div className="hero__actions">
            <div className="hero__status">
              <span className="eyebrow">Backend</span>
              <StatusPill tone={health?.status ?? "offline"} />
            </div>
            <button type="button" className="ghost-button" onClick={() => void refreshAll()}>
              {refreshing ? "Refreshing..." : "Refresh now"}
            </button>
          </div>
        </header>

        <section className="metric-grid">
          <MetricCard
            label="Queue depth"
            value={formatCompactNumber(queueDepth)}
            hint={`${queueJobs.length} jobs are currently active in the dashboard.`}
          />
          <MetricCard
            label="Completed"
            value={formatCompactNumber(completedJobs)}
            hint={`${successRate}% of tracked jobs ended in a completed state.`}
          />
          <MetricCard
            label="Profiles"
            value={formatCompactNumber(profiles.length)}
            hint="Reusable provider presets keep submissions consistent."
          />
          <MetricCard
            label="Failures"
            value={formatCompactNumber(failedJobs)}
            hint="Failed jobs stay visible in History for quick triage."
          />
        </section>

        {loading ? (
          <section className="panel">
            <div className="empty-state">
              <h3>Connecting to backend API</h3>
              <p>Loading jobs, profiles, health, and events from `/api`.</p>
            </div>
          </section>
        ) : (
          <>
            {notice ? (
              <div className="banner banner--success">
                <span>{notice}</span>
                <button type="button" onClick={() => setNotice(null)}>
                  Dismiss
                </button>
              </div>
            ) : null}

            {error ? (
              <div className="banner banner--error">
                <span>{error}</span>
                <button type="button" onClick={() => void refreshAll()}>
                  Retry
                </button>
              </div>
            ) : null}

            <div className="meta-row">
              <span>Last synced {formatRelativeTime(lastSyncedAt ?? undefined)}</span>
              {selectedJobId ? <span>Selected job: {selectedJobId}</span> : null}
            </div>

            {activeView === "queue" ? (
              <div className="panel-grid panel-grid--wide">
                <JobTable
                  jobs={queueJobs}
                  title="Queue"
                  subtitle="Active translations"
                  selectedJobId={selectedJobId}
                  onSelect={setSelectedJobId}
                  emptyMessage="Once the backend starts reporting queued or running jobs, they will appear here."
                />
                <JobInspector
                  job={selectedJob}
                  artifacts={selectedArtifacts}
                  events={selectedEvents}
                  streamState={streamState}
                  emptyMessage="Choose a queued job to inspect progress, files, and recent events."
                  showArtifacts={preferences.showCompletedArtifacts}
                  cancellingJobId={actionState.cancellingJobId}
                  retryingJobId={actionState.retryingJobId}
                  onCancel={handleCancelJob}
                  onRetry={handleRetryJob}
                />
              </div>
            ) : null}

            {activeView === "new-job" ? (
              <NewJobForm
                profiles={profiles}
                health={health}
                loading={actionState.creatingJob}
                onSubmit={handleCreateJob}
              />
            ) : null}

            {activeView === "profiles" ? (
              <ProfileManager
                profiles={profiles}
                saving={actionState.savingProfile}
                validatingProfileId={actionState.validatingProfileId}
                deletingProfileId={actionState.deletingProfileId}
                onSave={handleSaveProfile}
                onValidate={handleValidateProfile}
                onDelete={handleDeleteProfile}
              />
            ) : null}

            {activeView === "history" ? (
              <div className="panel-grid panel-grid--wide">
                <JobTable
                  jobs={historyJobs}
                  title="History"
                  subtitle="Completed and archived work"
                  selectedJobId={selectedJobId}
                  onSelect={setSelectedJobId}
                  emptyMessage="Finished, failed, and cancelled jobs will accumulate here."
                />
                <JobInspector
                  job={selectedJob}
                  artifacts={selectedArtifacts}
                  events={selectedEvents}
                  streamState={streamState}
                  emptyMessage="Select a history row to inspect artifacts and the event timeline."
                  showArtifacts={preferences.showCompletedArtifacts}
                  cancellingJobId={actionState.cancellingJobId}
                  retryingJobId={actionState.retryingJobId}
                  onCancel={handleCancelJob}
                  onRetry={handleRetryJob}
                />
              </div>
            ) : null}

            {activeView === "logs" ? (
              <LogsPanel
                globalEvents={globalEvents}
                selectedJob={selectedJob}
                selectedEvents={selectedEvents}
                health={health}
                streamState={streamState}
              />
            ) : null}

            {activeView === "settings" ? (
              <SettingsPanel
                preferences={preferences}
                onChange={setPreferences}
                health={health}
                profiles={profiles}
              />
            ) : null}
          </>
        )}
      </main>
    </div>
  );
}

export default App;
