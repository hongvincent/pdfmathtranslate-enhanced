import { useEffect, useState } from "react";
import { api, normalizeEvent } from "../api/client";
import type {
  JobArtifact,
  JobDetail,
  JobEvent,
  JobSummary,
  NewJobInput,
  ProfileDraft,
  ProviderProfile,
  StreamState,
  SystemHealth,
} from "../types";

const LIVE_STATUSES = new Set(["queued", "validating", "running", "paused"]);

type ActionState = {
  creatingJob: boolean;
  savingProfile: boolean;
  validatingProfileId: string | null;
  deletingProfileId: string | null;
  cancellingJobId: string | null;
  retryingJobId: string | null;
};

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

export function useDashboardData(options: {
  refreshMs: number;
  preferEventStream: boolean;
}) {
  const { refreshMs, preferEventStream } = options;

  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [profiles, setProfiles] = useState<ProviderProfile[]>([]);
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [globalEvents, setGlobalEvents] = useState<JobEvent[]>([]);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [selectedJob, setSelectedJob] = useState<JobDetail | null>(null);
  const [selectedArtifacts, setSelectedArtifacts] = useState<JobArtifact[]>([]);
  const [selectedEvents, setSelectedEvents] = useState<JobEvent[]>([]);
  const [streamState, setStreamState] = useState<StreamState>("idle");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [lastSyncedAt, setLastSyncedAt] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [actionState, setActionState] = useState<ActionState>({
    creatingJob: false,
    savingProfile: false,
    validatingProfileId: null,
    deletingProfileId: null,
    cancellingJobId: null,
    retryingJobId: null,
  });

  async function loadOverview(silent = false) {
    if (!silent) {
      setRefreshing(true);
    }

    const [jobsResult, profilesResult, healthResult, eventsResult] =
      await Promise.allSettled([
        api.listJobs(),
        api.listProfiles(),
        api.getHealth(),
        api.listEvents(),
      ]);

    let overviewError: string | null = null;

    if (jobsResult.status === "fulfilled") {
      setJobs(jobsResult.value);
    } else {
      overviewError = jobsResult.reason instanceof Error ? jobsResult.reason.message : "Failed to load jobs.";
    }

    if (profilesResult.status === "fulfilled") {
      setProfiles(profilesResult.value);
    }

    if (healthResult.status === "fulfilled") {
      setHealth(healthResult.value);
    }

    if (eventsResult.status === "fulfilled") {
      setGlobalEvents(eventsResult.value);
    }

    setError(overviewError);
    setLastSyncedAt(new Date().toISOString());
    setRefreshing(false);
    setLoading(false);
  }

  async function loadSelectedSnapshot(jobId: string) {
    try {
      const [detail, artifacts, events] = await Promise.all([
        api.getJob(jobId),
        api.listJobArtifacts(jobId),
        api.listJobEvents(jobId),
      ]);

      setSelectedJob({
        ...detail,
        artifacts,
        recentEvents: events,
      });
      setSelectedArtifacts(artifacts);
      setSelectedEvents(events);
      setJobs((currentJobs) =>
        currentJobs.map((job) => (job.id === detail.id ? { ...job, ...detail } : job)),
      );
      setError(null);
    } catch (nextError) {
      setError(
        nextError instanceof Error
          ? nextError.message
          : "Failed to load the selected job.",
      );
    }
  }

  useEffect(() => {
    let cancelled = false;

    async function start() {
      await loadOverview();
      if (cancelled) {
        return;
      }
    }

    start();

    const intervalId = window.setInterval(() => {
      void loadOverview(true);
    }, refreshMs);

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [refreshMs]);

  useEffect(() => {
    if (selectedJobId) {
      const stillExists = jobs.some((job) => job.id === selectedJobId);
      if (!stillExists && jobs.length > 0) {
        const fallback = jobs.find((job) => LIVE_STATUSES.has(job.status)) ?? jobs[0];
        setSelectedJobId(fallback?.id ?? null);
      }
      return;
    }

    if (jobs.length === 0) {
      return;
    }

    const defaultJob = jobs.find((job) => LIVE_STATUSES.has(job.status)) ?? jobs[0];
    setSelectedJobId(defaultJob?.id ?? null);
  }, [jobs, selectedJobId]);

  useEffect(() => {
    if (!selectedJobId) {
      setSelectedJob(null);
      setSelectedArtifacts([]);
      setSelectedEvents([]);
      setStreamState("idle");
      return;
    }

    void loadSelectedSnapshot(selectedJobId);

    const selectedSummary = jobs.find((job) => job.id === selectedJobId);
    const shouldPoll =
      !preferEventStream ||
      !selectedSummary ||
      !LIVE_STATUSES.has(selectedSummary.status);

    if (!shouldPoll) {
      return;
    }

    setStreamState(preferEventStream ? "fallback" : "idle");
    const intervalId = window.setInterval(() => {
      void loadSelectedSnapshot(selectedJobId);
    }, Math.max(4000, Math.floor(refreshMs / 2)));

    return () => {
      window.clearInterval(intervalId);
    };
  }, [jobs, preferEventStream, refreshMs, selectedJobId]);

  useEffect(() => {
    const selectedSummary = jobs.find((job) => job.id === selectedJobId);
    const canStream =
      preferEventStream &&
      selectedJobId &&
      selectedSummary &&
      LIVE_STATUSES.has(selectedSummary.status) &&
      typeof EventSource !== "undefined";

    if (!canStream || !selectedJobId) {
      if (preferEventStream && selectedJobId && typeof EventSource === "undefined") {
        setStreamState("fallback");
      }
      return;
    }

    setStreamState("connecting");
    const eventSource = api.streamJobEvents(selectedJobId);

    eventSource.onopen = () => {
      setStreamState("live");
    };

    eventSource.onmessage = (message) => {
      try {
        const payload = JSON.parse(message.data) as unknown;
        const nextEvent = normalizeEvent(payload);
        if (!nextEvent) {
          return;
        }

        setSelectedEvents((current) => dedupeEvents([nextEvent, ...current]));
        setGlobalEvents((current) => dedupeEvents([nextEvent, ...current]));
        setSelectedJob((current) => {
          if (!current) {
            return current;
          }

          const nextStatus =
            nextEvent.type === "finish"
              ? "completed"
              : nextEvent.type === "error"
                ? "failed"
                : current.status;

          const nextProgress =
            nextEvent.overallProgress !== undefined
              ? nextEvent.overallProgress
              : current.progress;

          return {
            ...current,
            status: nextStatus,
            progress: nextProgress,
            currentStage: nextEvent.stage ?? current.currentStage,
            updatedAt: nextEvent.timestamp,
            recentEvents: dedupeEvents([nextEvent, ...current.recentEvents]),
          };
        });
        setJobs((currentJobs) =>
          currentJobs.map((job) =>
            job.id === selectedJobId
              ? {
                  ...job,
                  status:
                    nextEvent.type === "finish"
                      ? "completed"
                      : nextEvent.type === "error"
                        ? "failed"
                        : job.status,
                  progress:
                    nextEvent.overallProgress !== undefined
                      ? nextEvent.overallProgress
                      : job.progress,
                  currentStage: nextEvent.stage ?? job.currentStage,
                  updatedAt: nextEvent.timestamp,
                }
              : job,
          ),
        );

        if (nextEvent.type === "finish" || nextEvent.type === "error") {
          void loadSelectedSnapshot(selectedJobId);
        }
      } catch {
        setStreamState("fallback");
      }
    };

    eventSource.onerror = () => {
      setStreamState("fallback");
      eventSource.close();
    };

    return () => {
      eventSource.close();
    };
  }, [jobs, preferEventStream, selectedJobId]);

  async function refreshAll() {
    setRefreshing(true);
    await loadOverview(true);
    if (selectedJobId) {
      await loadSelectedSnapshot(selectedJobId);
    }
    setRefreshing(false);
  }

  async function createJob(input: NewJobInput) {
    setActionState((current) => ({ ...current, creatingJob: true }));

    try {
      const job = await api.createJob(input);
      await loadOverview(true);
      if (job?.id) {
        setSelectedJobId(job.id);
        await loadSelectedSnapshot(job.id);
      }
      setError(null);
      return job;
    } catch (nextError) {
      setError(
        nextError instanceof Error
          ? nextError.message
          : "Failed to queue the new job.",
      );
      return null;
    } finally {
      setActionState((current) => ({ ...current, creatingJob: false }));
    }
  }

  async function saveProfile(draft: ProfileDraft) {
    setActionState((current) => ({ ...current, savingProfile: true }));

    try {
      const profile = draft.id
        ? await api.updateProfile(draft.id, draft)
        : await api.createProfile(draft);
      const nextProfiles = await api.listProfiles();
      setProfiles(nextProfiles);
      setError(null);
      return profile;
    } catch (nextError) {
      setError(
        nextError instanceof Error
          ? nextError.message
          : "Failed to save the provider profile.",
      );
      return null;
    } finally {
      setActionState((current) => ({ ...current, savingProfile: false }));
    }
  }

  async function validateProfile(profileId: string) {
    setActionState((current) => ({ ...current, validatingProfileId: profileId }));

    try {
      await api.validateProfile(profileId);
      const nextProfiles = await api.listProfiles();
      setProfiles(nextProfiles);
      setError(null);
      return true;
    } catch (nextError) {
      setError(
        nextError instanceof Error
          ? nextError.message
          : "Failed to validate the provider profile.",
      );
      const nextProfiles = await api.listProfiles().catch(() => null);
      if (nextProfiles) {
        setProfiles(nextProfiles);
      }
      return false;
    } finally {
      setActionState((current) => ({ ...current, validatingProfileId: null }));
    }
  }

  async function deleteProfile(profileId: string) {
    setActionState((current) => ({ ...current, deletingProfileId: profileId }));

    try {
      await api.deleteProfile(profileId);
      const nextProfiles = await api.listProfiles();
      setProfiles(nextProfiles);
      setError(null);
      return true;
    } catch (nextError) {
      setError(
        nextError instanceof Error
          ? nextError.message
          : "Failed to delete the provider profile.",
      );
      return false;
    } finally {
      setActionState((current) => ({ ...current, deletingProfileId: null }));
    }
  }

  async function cancelJob(jobId: string) {
    setActionState((current) => ({ ...current, cancellingJobId: jobId }));

    try {
      const job = await api.cancelJob(jobId);
      await loadOverview(true);
      await loadSelectedSnapshot(job.id);
      setError(null);
      return job;
    } catch (nextError) {
      setError(
        nextError instanceof Error ? nextError.message : "Failed to cancel the job.",
      );
      return null;
    } finally {
      setActionState((current) => ({ ...current, cancellingJobId: null }));
    }
  }

  async function retryJob(jobId: string) {
    setActionState((current) => ({ ...current, retryingJobId: jobId }));

    try {
      const job = await api.retryJob(jobId);
      await loadOverview(true);
      setSelectedJobId(job.id);
      await loadSelectedSnapshot(job.id);
      setError(null);
      return job;
    } catch (nextError) {
      setError(
        nextError instanceof Error ? nextError.message : "Failed to retry the job.",
      );
      return null;
    } finally {
      setActionState((current) => ({ ...current, retryingJobId: null }));
    }
  }

  return {
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
  };
}
