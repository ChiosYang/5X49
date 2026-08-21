"use client";

import { useEffect, useMemo, useRef } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle, CheckCircle2, Clock3, Loader2, ListRestart, ListTodo, X } from "lucide-react";
import { useCancelJob, useJobCache, useJobs, useRetryJob } from "@/hooks/useJobs";
import type { Job } from "@/types/movie";

const TERMINAL_STATUSES = new Set(["succeeded", "failed", "cancelled"]);

function jobLabel(type: string) {
  const labels: Record<string, string> = {
    "library.reconcile": "Library scan",
    "library.scan_folder": "Folder scan",
    "library.mark_path_missing": "Missing file update",
    "library.refresh_movie": "Movie refresh",
    "metadata.scrape_library": "Metadata scrape",
    "organizer.organize_root": "Root organization",
    "organizer.confirm_root_video": "Root confirmation",
    "analysis.analyze_movie": "Film analysis",
    "external_scores.refresh_movie": "Score refresh",
    "external_scores.refresh_library": "Score refresh",
  };

  return labels[type] || type;
}

function statusIcon(job: Job) {
  if (job.status === "running" || job.status === "cancelling") {
    return <Loader2 className="h-3.5 w-3.5 animate-spin text-ink" />;
  }
  if (job.status === "queued") {
    return <Clock3 className="h-3.5 w-3.5 text-ink-muted" />;
  }
  if (job.status === "failed") {
    return <AlertTriangle className="h-3.5 w-3.5 text-danger" />;
  }
  return <CheckCircle2 className="h-3.5 w-3.5 text-success" />;
}

function resultSummary(job: Job) {
  if (job.result_summary) {
    return job.result_summary;
  }
  if (job.error) {
    return job.error;
  }
  if (job.progress?.message) {
    return job.progress.message;
  }

  const result = job.result || {};
  const parts = ["scanned", "added", "missing", "processed", "succeeded", "organized", "updated", "failed"]
    .map((key) => {
      const value = result[key];
      return typeof value === "number" ? `${key} ${value}` : null;
    })
    .filter(Boolean);

  if (parts.length > 0) {
    return parts.slice(0, 3).join(", ");
  }

  return job.status;
}

function progressPercent(job: Job) {
  const current = job.progress?.current;
  const total = job.progress?.total;
  if (typeof current !== "number" || typeof total !== "number" || total <= 0) {
    return null;
  }
  return Math.max(0, Math.min(100, Math.round((current / total) * 100)));
}

export default function JobRuntimeStatus() {
  const router = useRouter();
  const { data: jobs = [] } = useJobs();
  const { upsertJob, refreshJobs } = useJobCache();
  const { trigger: cancelJob, isMutating: isCancelling } = useCancelJob();
  const { trigger: retryJob, isMutating: isRetrying } = useRetryJob();
  const refreshTimer = useRef<number | null>(null);

  const activeJobs = useMemo(
    () => jobs.filter((job) => job.status === "queued" || job.status === "running" || job.status === "cancelling"),
    [jobs],
  );
  const latestJob = activeJobs[0] || jobs[0];
  const hasRecentFailure = jobs.some((job) => job.status === "failed");

  useEffect(() => {
    const eventSource = new EventSource("/api/library/events");

    const scheduleRefresh = () => {
      if (refreshTimer.current) {
        window.clearTimeout(refreshTimer.current);
      }

      refreshTimer.current = window.setTimeout(() => {
        refreshJobs();
        router.refresh();
      }, 750);
    };

    const handleJobEvent = (event: Event) => {
      const message = event as MessageEvent<string>;
      try {
        const payload = JSON.parse(message.data) as { job?: Job };
        if (payload.job) {
          upsertJob(payload.job);
          if (TERMINAL_STATUSES.has(payload.job.status)) {
            scheduleRefresh();
          }
        }
      } catch {
        refreshJobs();
      }
    };

    eventSource.addEventListener("library_changed", scheduleRefresh);
    eventSource.addEventListener("job_queued", handleJobEvent);
    eventSource.addEventListener("job_started", handleJobEvent);
    eventSource.addEventListener("job_succeeded", handleJobEvent);
    eventSource.addEventListener("job_failed", handleJobEvent);
    eventSource.addEventListener("job_progress", handleJobEvent);
    eventSource.addEventListener("job_cancelled", handleJobEvent);
    eventSource.addEventListener("job_retried", handleJobEvent);

    return () => {
      if (refreshTimer.current) {
        window.clearTimeout(refreshTimer.current);
      }
      eventSource.removeEventListener("library_changed", scheduleRefresh);
      eventSource.removeEventListener("job_queued", handleJobEvent);
      eventSource.removeEventListener("job_started", handleJobEvent);
      eventSource.removeEventListener("job_succeeded", handleJobEvent);
      eventSource.removeEventListener("job_failed", handleJobEvent);
      eventSource.removeEventListener("job_progress", handleJobEvent);
      eventSource.removeEventListener("job_cancelled", handleJobEvent);
      eventSource.removeEventListener("job_retried", handleJobEvent);
      eventSource.close();
    };
  }, [refreshJobs, router, upsertJob]);

  return (
    <div className="group/jobs relative text-ink">
      <button
        type="button"
        className="focus-ring duration-standard relative flex h-10 w-10 items-center justify-center text-ink drop-shadow-lg transition-opacity hover:opacity-70"
        aria-label="Background jobs"
        title="Background jobs"
      >
        {activeJobs.length > 0 ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : hasRecentFailure ? (
          <AlertTriangle className="h-4 w-4 text-danger" />
        ) : (
          <ListTodo className="h-4 w-4" />
        )}
        {activeJobs.length > 0 && (
          <span className="absolute -top-1.5 -right-1.5 flex min-h-4 min-w-4 items-center justify-center border border-canvas bg-inverse px-1 text-[10px] leading-none font-bold text-inverse-ink">
            {activeJobs.length > 9 ? "9+" : activeJobs.length}
          </span>
        )}
      </button>

      <div className="z-popover pointer-events-none absolute top-full right-0 w-[min(24rem,calc(100vw-2rem))] pt-3 opacity-0 transition-opacity duration-standard group-hover/jobs:pointer-events-auto group-hover/jobs:opacity-100 group-focus-within/jobs:pointer-events-auto group-focus-within/jobs:opacity-100">
        <div className="liquid-glass-popover scrollbar-minimal relative max-h-80 overflow-y-auto border border-line/80 p-2">
          <div className="border-b border-line px-3 py-2">
            <p className="text-xs font-bold tracking-widest text-ink-muted uppercase">Background Jobs</p>
            <p className="mt-1 truncate text-xs text-ink-disabled">
              {latestJob ? `${jobLabel(latestJob.type)} - ${resultSummary(latestJob)}` : "No recent jobs"}
            </p>
          </div>
          {jobs.length === 0 ? (
            <div className="px-3 py-6 text-center text-xs font-bold tracking-widest text-ink-disabled uppercase">
              No Jobs
            </div>
          ) : (
            <ul className="mt-2 space-y-1">
              {jobs.map((job) => (
                <li key={job.id} className="grid grid-cols-[auto_1fr_auto] gap-3 border border-line bg-surface/70 p-3">
                  <span className="mt-0.5">{statusIcon(job)}</span>
                  <span className="min-w-0">
                    <span className="flex min-w-0 items-center justify-between gap-3">
                      <span className="truncate text-xs font-bold uppercase tracking-widest">{jobLabel(job.type)}</span>
                      <span className="shrink-0 text-[10px] font-bold tracking-widest text-ink-subtle uppercase">
                        {job.status}
                      </span>
                    </span>
                    <span className={`mt-1 block truncate text-xs ${job.status === "failed" ? "text-danger" : "text-ink-subtle"}`}>
                      {resultSummary(job)}
                    </span>
                    {progressPercent(job) !== null && (
                      <span className="mt-2 block h-1 overflow-hidden bg-surface-raised">
                        <span
                          className="duration-standard block h-full bg-ink transition-[width]"
                          style={{ width: `${progressPercent(job)}%` }}
                        />
                      </span>
                    )}
                  </span>
                  <span className="flex items-start gap-1">
                    {(job.status === "queued" || job.status === "running") && (
                      <button
                        type="button"
                        onClick={() => void cancelJob(job.id)}
                        disabled={isCancelling}
                        className="focus-ring duration-standard flex h-6 w-6 items-center justify-center text-ink-subtle transition-colors hover:text-ink disabled:opacity-50"
                        aria-label="Cancel job"
                        title="Cancel"
                      >
                        <X className="h-3.5 w-3.5" />
                      </button>
                    )}
                    {(job.status === "failed" || job.status === "cancelled") && (
                      <button
                        type="button"
                        onClick={() => void retryJob(job.id)}
                        disabled={isRetrying}
                        className="focus-ring duration-standard flex h-6 w-6 items-center justify-center text-ink-subtle transition-colors hover:text-ink disabled:opacity-50"
                        aria-label="Retry job"
                        title="Retry"
                      >
                        <ListRestart className="h-3.5 w-3.5" />
                      </button>
                    )}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
