"use client";

import { useEffect, useMemo, useRef } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle, CheckCircle2, Clock3, Loader2, ListTodo } from "lucide-react";
import { useJobCache, useJobs } from "@/hooks/useJobs";
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
  if (job.status === "running") {
    return <Loader2 className="h-3.5 w-3.5 animate-spin text-white" />;
  }
  if (job.status === "queued") {
    return <Clock3 className="h-3.5 w-3.5 text-neutral-400" />;
  }
  if (job.status === "failed") {
    return <AlertTriangle className="h-3.5 w-3.5 text-red-400" />;
  }
  return <CheckCircle2 className="h-3.5 w-3.5 text-green-400" />;
}

function resultSummary(job: Job) {
  if (job.error) {
    return job.error;
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

export default function JobRuntimeStatus() {
  const router = useRouter();
  const { data: jobs = [] } = useJobs();
  const { upsertJob, refreshJobs } = useJobCache();
  const refreshTimer = useRef<number | null>(null);

  const activeJobs = useMemo(
    () => jobs.filter((job) => job.status === "queued" || job.status === "running"),
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

    return () => {
      if (refreshTimer.current) {
        window.clearTimeout(refreshTimer.current);
      }
      eventSource.removeEventListener("library_changed", scheduleRefresh);
      eventSource.removeEventListener("job_queued", handleJobEvent);
      eventSource.removeEventListener("job_started", handleJobEvent);
      eventSource.removeEventListener("job_succeeded", handleJobEvent);
      eventSource.removeEventListener("job_failed", handleJobEvent);
      eventSource.close();
    };
  }, [refreshJobs, router, upsertJob]);

  return (
    <div className="group/jobs relative text-white">
      <button
        type="button"
        className="relative flex h-10 w-10 items-center justify-center text-white drop-shadow-lg transition-opacity hover:opacity-70"
        aria-label="Background jobs"
        title="Background jobs"
      >
        {activeJobs.length > 0 ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : hasRecentFailure ? (
          <AlertTriangle className="h-4 w-4 text-red-300" />
        ) : (
          <ListTodo className="h-4 w-4" />
        )}
        {activeJobs.length > 0 && (
          <span className="absolute -right-1.5 -top-1.5 flex min-h-4 min-w-4 items-center justify-center border border-black bg-white px-1 text-[10px] font-bold leading-none text-black">
            {activeJobs.length > 9 ? "9+" : activeJobs.length}
          </span>
        )}
      </button>

      <div className="pointer-events-none absolute right-0 top-full z-[80] w-[min(24rem,calc(100vw-2rem))] pt-3 opacity-0 transition-opacity duration-150 group-hover/jobs:pointer-events-auto group-hover/jobs:opacity-100 group-focus-within/jobs:pointer-events-auto group-focus-within/jobs:opacity-100">
        <div className="max-h-80 overflow-y-auto border border-neutral-800 bg-black/95 p-2 shadow-2xl shadow-black/60 backdrop-blur scrollbar-minimal">
          <div className="border-b border-neutral-900 px-3 py-2">
            <p className="text-xs font-bold uppercase tracking-widest text-neutral-300">Background Jobs</p>
            <p className="mt-1 truncate text-xs text-neutral-600">
              {latestJob ? `${jobLabel(latestJob.type)} - ${latestJob.status}` : "No recent jobs"}
            </p>
          </div>
          {jobs.length === 0 ? (
            <div className="px-3 py-6 text-center text-xs font-bold uppercase tracking-widest text-neutral-600">
              No Jobs
            </div>
          ) : (
            <ul className="mt-2 space-y-1">
              {jobs.map((job) => (
                <li key={job.id} className="grid grid-cols-[auto_1fr] gap-3 border border-neutral-900 bg-neutral-950/70 p-3">
                  <span className="mt-0.5">{statusIcon(job)}</span>
                  <span className="min-w-0">
                    <span className="flex min-w-0 items-center justify-between gap-3">
                      <span className="truncate text-xs font-bold uppercase tracking-widest">{jobLabel(job.type)}</span>
                      <span className="shrink-0 text-[10px] font-bold uppercase tracking-widest text-neutral-500">
                        {job.status}
                      </span>
                    </span>
                    <span className={`mt-1 block truncate text-xs ${job.status === "failed" ? "text-red-400" : "text-neutral-500"}`}>
                      {resultSummary(job)}
                    </span>
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
