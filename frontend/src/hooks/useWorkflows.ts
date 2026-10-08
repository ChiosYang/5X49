"use client";

import { useCallback } from "react";
import useSWR, { useSWRConfig } from "swr";
import useSWRMutation from "swr/mutation";
import { retainRecentWorkflows } from "@/lib/workflow-status";
import { responseError } from "@/lib/fetcher";
import { API } from "@/lib/api";
import type { WorkflowRunView } from "@/types/movie";

const WORKFLOWS_KEY = `${API.workflows()}?limit=8&include_active=true`;

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
        return retainRecentWorkflows([workflow, ...workflows.filter((item) => item.id !== workflow.id)]);
      },
      false,
    );
  }, [mutate]);

  const refreshWorkflows = useCallback(() => {
    void mutate(WORKFLOWS_KEY).catch(() => undefined);
  }, [mutate]);

  return { upsertWorkflow, refreshWorkflows };
}

export function useCancelWorkflow() {
  const { mutate } = useSWRConfig();
  return useSWRMutation(
    "workflow.cancel",
    async (_key: string, { arg: workflowId }: { arg: string }) => {
      const response = await fetch(API.workflowCancel(workflowId), { method: "POST" });
      if (!response.ok) throw await responseError(response, "Failed to cancel workflow");
      const workflow = await response.json() as WorkflowRunView;
      void mutate(WORKFLOWS_KEY).catch(() => undefined);
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
      if (!response.ok) throw await responseError(response, "Failed to retry workflow");
      const data = await response.json();
      void mutate(WORKFLOWS_KEY).catch(() => undefined);
      return data;
    },
  );
}

export { WORKFLOWS_KEY };
