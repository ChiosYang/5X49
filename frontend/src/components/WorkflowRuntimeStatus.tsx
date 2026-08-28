"use client";

import { useEffect, useMemo, useRef } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { AlertTriangle, CheckCircle2, Clock3, Layers3, ListRestart, Loader2, X } from "lucide-react";
import {
  useCancelWorkflow,
  useRetryWorkflow,
  useWorkflowCache,
  useWorkflows,
} from "@/hooks/useWorkflows";
import type { WorkflowRunView } from "@/types/movie";

const TERMINAL_STATUSES = new Set(["succeeded", "failed", "cancelled"]);
const WORKFLOW_EVENTS = [
  "workflow_queued",
  "workflow_running",
  "workflow_progress",
  "workflow_succeeded",
  "workflow_failed",
  "workflow_cancelled",
] as const;

function workflowLabel(type: string, translate: (key: string) => string) {
  const labels: Record<string, string> = {
    "library.reconcile": "types.libraryReconcile",
    "library.scan_folder": "types.folderScan",
    "library.mark_path_missing": "types.missingUpdate",
    "library.refresh_item": "types.editionRefresh",
    "metadata.scrape_library": "types.metadataScrape",
    "organizer.organize_root": "types.rootOrganization",
    "organizer.confirm_root_video": "types.rootConfirmation",
    "analysis.analyze_film": "types.filmAnalysis",
    "external_scores.refresh_film": "types.scoreRefresh",
    "external_scores.refresh_library": "types.scoreRefresh",
  };

  return labels[type] ? translate(labels[type]) : type;
}

function statusIcon(workflow: WorkflowRunView) {
  if (workflow.status === "running") {
    return <Loader2 className="h-3.5 w-3.5 animate-spin text-ink" />;
  }
  if (workflow.status === "queued") {
    return <Clock3 className="h-3.5 w-3.5 text-ink-muted" />;
  }
  if (workflow.status === "failed") {
    return <AlertTriangle className="h-3.5 w-3.5 text-danger" />;
  }
  return <CheckCircle2 className="h-3.5 w-3.5 text-success" />;
}

function resultSummary(workflow: WorkflowRunView) {
  if (workflow.result_summary) return workflow.result_summary;
  if (workflow.error_message) return workflow.error_message;
  const currentStep = workflow.steps.find((step) => step.step_key === workflow.current_step);
  return currentStep?.result_summary || workflow.current_step || workflow.status;
}

function progressPercent(workflow: WorkflowRunView) {
  const current = workflow.progress?.current;
  const total = workflow.progress?.total;
  if (typeof current === "number" && typeof total === "number" && total > 0) {
    return Math.max(0, Math.min(100, Math.round((current / total) * 100)));
  }
  if (workflow.steps.length === 0) return null;
  const completed = workflow.steps.filter((step) => step.status === "succeeded").length;
  return Math.round((completed / workflow.steps.length) * 100);
}

export default function WorkflowRuntimeStatus() {
  const router = useRouter();
  const t = useTranslations("WorkflowStatus");
  const { data: workflows = [] } = useWorkflows();
  const { upsertWorkflow, refreshWorkflows } = useWorkflowCache();
  const { trigger: cancelWorkflow, isMutating: isCancelling } = useCancelWorkflow();
  const { trigger: retryWorkflow, isMutating: isRetrying } = useRetryWorkflow();
  const refreshTimer = useRef<number | null>(null);

  const activeWorkflows = useMemo(
    () => workflows.filter((workflow) => workflow.status === "queued" || workflow.status === "running"),
    [workflows],
  );
  const latestWorkflow = activeWorkflows[0] || workflows[0];
  const hasRecentFailure = workflows.some((workflow) => workflow.status === "failed");

  useEffect(() => {
    const eventSource = new EventSource("/api/library/events");

    const scheduleRefresh = () => {
      if (refreshTimer.current) window.clearTimeout(refreshTimer.current);
      refreshTimer.current = window.setTimeout(() => {
        refreshWorkflows();
        router.refresh();
      }, 750);
    };

    const handleWorkflowEvent = (event: Event) => {
      const message = event as MessageEvent<string>;
      try {
        const payload = JSON.parse(message.data) as { workflow?: WorkflowRunView };
        if (payload.workflow) {
          upsertWorkflow(payload.workflow);
          if (TERMINAL_STATUSES.has(payload.workflow.status)) scheduleRefresh();
        }
      } catch {
        refreshWorkflows();
      }
    };

    eventSource.addEventListener("library_changed", scheduleRefresh);
    WORKFLOW_EVENTS.forEach((eventName) => eventSource.addEventListener(eventName, handleWorkflowEvent));

    return () => {
      if (refreshTimer.current) window.clearTimeout(refreshTimer.current);
      eventSource.removeEventListener("library_changed", scheduleRefresh);
      WORKFLOW_EVENTS.forEach((eventName) => eventSource.removeEventListener(eventName, handleWorkflowEvent));
      eventSource.close();
    };
  }, [refreshWorkflows, router, upsertWorkflow]);

  return (
    <div className="group/workflows relative text-ink">
      <button
        type="button"
        className="focus-ring duration-standard relative flex h-10 w-10 items-center justify-center text-ink drop-shadow-lg transition-opacity hover:opacity-70"
        aria-label={t("label")}
        title={t("label")}
      >
        {activeWorkflows.length > 0 ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : hasRecentFailure ? (
          <AlertTriangle className="h-4 w-4 text-danger" />
        ) : (
          <Layers3 className="h-4 w-4" />
        )}
        {activeWorkflows.length > 0 && (
          <span className="absolute -top-1.5 -right-1.5 flex min-h-4 min-w-4 items-center justify-center border border-canvas bg-inverse px-1 text-[10px] leading-none font-bold text-inverse-ink">
            {activeWorkflows.length > 9 ? "9+" : activeWorkflows.length}
          </span>
        )}
      </button>

      <div className="z-popover pointer-events-none absolute top-full right-0 w-[min(24rem,calc(100vw-2rem))] pt-3 opacity-0 transition-opacity duration-standard group-hover/workflows:pointer-events-auto group-hover/workflows:opacity-100 group-focus-within/workflows:pointer-events-auto group-focus-within/workflows:opacity-100">
        <div className="liquid-glass-popover scrollbar-minimal relative max-h-80 overflow-y-auto border border-line/80 p-2">
          <div className="border-b border-line px-3 py-2">
            <p className="text-xs font-bold tracking-widest text-ink-muted uppercase">{t("title")}</p>
            <p className="mt-1 truncate text-xs text-ink-disabled">
              {latestWorkflow
                ? `${workflowLabel(latestWorkflow.type, (key) => t(key as never))} - ${resultSummary(latestWorkflow)}`
                : t("noRecent")}
            </p>
          </div>
          {workflows.length === 0 ? (
            <div className="px-3 py-6 text-center text-xs font-bold tracking-widest text-ink-disabled uppercase">
              {t("empty")}
            </div>
          ) : (
            <ul className="mt-2 space-y-1">
              {workflows.map((workflow) => (
                <li key={workflow.id} className="grid grid-cols-[auto_1fr_auto] gap-3 border border-line bg-surface/70 p-3">
                  <span className="mt-0.5">{statusIcon(workflow)}</span>
                  <span className="min-w-0">
                    <span className="flex min-w-0 items-center justify-between gap-3">
                      <span className="truncate text-xs font-bold uppercase tracking-widest">{workflowLabel(workflow.type, (key) => t(key as never))}</span>
                      <span className="shrink-0 text-[10px] font-bold tracking-widest text-ink-subtle uppercase">
                        {workflow.status}
                      </span>
                    </span>
                    <span className={`mt-1 block truncate text-xs ${workflow.status === "failed" ? "text-danger" : "text-ink-subtle"}`}>
                      {resultSummary(workflow)}
                    </span>
                    {progressPercent(workflow) !== null && (
                      <span className="mt-2 block h-1 overflow-hidden bg-surface-raised">
                        <span
                          className="duration-standard block h-full bg-ink transition-[width]"
                          style={{ width: `${progressPercent(workflow)}%` }}
                        />
                      </span>
                    )}
                  </span>
                  <span className="flex items-start gap-1">
                    {(workflow.status === "queued" || workflow.status === "running") && (
                      <button
                        type="button"
                        onClick={() => void cancelWorkflow(workflow.id)}
                        disabled={isCancelling}
                        className="focus-ring duration-standard flex h-6 w-6 items-center justify-center text-ink-subtle transition-colors hover:text-ink disabled:opacity-50"
                        aria-label={t("cancel")}
                        title={t("cancel")}
                      >
                        <X className="h-3.5 w-3.5" />
                      </button>
                    )}
                    {(workflow.status === "failed" || workflow.status === "cancelled") && (
                      <button
                        type="button"
                        onClick={() => void retryWorkflow(workflow.id)}
                        disabled={isRetrying}
                        className="focus-ring duration-standard flex h-6 w-6 items-center justify-center text-ink-subtle transition-colors hover:text-ink disabled:opacity-50"
                        aria-label={t("retry")}
                        title={t("retry")}
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
