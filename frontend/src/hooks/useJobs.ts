"use client";

import { useCallback } from "react";
import useSWR, { useSWRConfig } from "swr";
import { API } from "@/lib/api";
import type { Job } from "@/types/movie";

const JOBS_KEY = `${API.jobs()}?limit=8`;

export function useJobs() {
  return useSWR<Job[]>(JOBS_KEY, {
    refreshInterval: (jobs?: Job[]) =>
      jobs?.some((job) => job.status === "queued" || job.status === "running") ? 3000 : 0,
  });
}

export function useJobCache() {
  const { mutate } = useSWRConfig();

  const upsertJob = useCallback((job: Job) => {
    void mutate(
      JOBS_KEY,
      (current?: Job[]) => {
        const jobs = current || [];
        const next = [job, ...jobs.filter((item) => item.id !== job.id)];
        return next
          .sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at))
          .slice(0, 8);
      },
      false,
    );
  }, [mutate]);

  const refreshJobs = useCallback(() => {
    void mutate(JOBS_KEY);
  }, [mutate]);

  return { upsertJob, refreshJobs };
}

export { JOBS_KEY };
