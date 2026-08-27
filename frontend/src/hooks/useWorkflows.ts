"use client";

import { useCallback } from "react";
import useSWR, { useSWRConfig } from "swr";
import useSWRMutation from "swr/mutation";
import { API } from "@/lib/api";
import type { WorkflowRunView } from "@/types/movie";

const WORKFLOWS_KEY = `${API.workflows()}?limit=8`;

export function useWorkflows() {
  return useSWR<WorkflowRunView[]>(WORKFLOWS_KEY, {
    refreshInterval: (workflows?: WorkflowRunView[]) =>
      workflows?.some((workflow) => workflow.status === "queued" || workflow.status === "running") ? 3000 : 0,
  });
}

export function useWorkflowCache() {
  const { mutate } = useSWRConfig();

  const upsertWorkflow = useCallback((workflow: WorkflowRunView) => {
    void mutate(
      WORKFLOWS_KEY,
      (current?: WorkflowRunView[]) => {
        const workflows = current || [];
        return [workflow, ...workflows.filter((item) => item.id !== workflow.id)]
          .sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at))
          .slice(0, 8);
      },
      false,
    );
  }, [mutate]);

  const refreshWorkflows = useCallback(() => {
    void mutate(WORKFLOWS_KEY);
  }, [mutate]);

  return { upsertWorkflow, refreshWorkflows };
}

export function useCancelWorkflow() {
  const { mutate } = useSWRConfig();
  return useSWRMutation(
    "workflow.cancel",
    async (_key: string, { arg: workflowId }: { arg: string }) => {
      const response = await fetch(API.workflowCancel(workflowId), { method: "POST" });
      if (!response.ok) throw new Error("Failed to cancel workflow");
      const workflow = await response.json() as WorkflowRunView;
      await mutate(WORKFLOWS_KEY);
      return workflow;
    },
  );
}

export function useRetryWorkflow() {
  const { mutate } = useSWRConfig();
  return useSWRMutation(
    "workflow.retry",
    async (_key: string, { arg: workflowId }: { arg: string }) => {
      const response = await fetch(API.workflowRetry(workflowId), { method: "POST" });
      if (!response.ok) throw new Error("Failed to retry workflow");
      const data = await response.json();
      await mutate(WORKFLOWS_KEY);
      return data;
    },
  );
}

export { WORKFLOWS_KEY };
