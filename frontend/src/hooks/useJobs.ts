"use client";

import { useCallback } from "react";
import useSWR, { useSWRConfig } from "swr";
import useSWRMutation from "swr/mutation";
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

export function useCancelJob() {
  const { mutate } = useSWRConfig();
  return useSWRMutation(
    "job.cancel",
    async (_key: string, { arg: jobId }: { arg: string }) => {
      const res = await fetch(API.jobCancel(jobId), { method: "POST" });
      if (!res.ok) throw new Error("Failed to cancel job");
      const job = await res.json() as Job;
      await mutate(JOBS_KEY);
      return job;
    },
  );
}

export function useRetryJob() {
  const { mutate } = useSWRConfig();
  return useSWRMutation(
    "job.retry",
    async (_key: string, { arg: jobId }: { arg: string }) => {
      const res = await fetch(API.jobRetry(jobId), { method: "POST" });
      if (!res.ok) throw new Error("Failed to retry job");
      const data = await res.json();
      await mutate(JOBS_KEY);
      return data;
    },
  );
}

export { JOBS_KEY };
