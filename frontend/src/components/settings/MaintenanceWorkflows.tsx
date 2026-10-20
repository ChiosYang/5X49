"use client";

import { useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/Button";
import { InlineFeedback, StateMessage } from "@/components/ui/Feedback";
import { useCancelWorkflow, useRetryWorkflow, useWorkflows } from "@/hooks/useWorkflows";
import { Link } from "@/i18n/routing";
import { workflowLabel } from "@/components/WorkflowRuntimeStatus";

export default function MaintenanceWorkflows() {
  const area = useTranslations("SettingsArea");
  const t = useTranslations("LibraryManagement.constellation");
  const workflowText = useTranslations("WorkflowStatus");
  const query = useWorkflows(), cancel = useCancelWorkflow(), retry = useRetryWorkflow();
  const [error, setError] = useState<string | null>(null);
  const lock = useRef(false);
  const workflows = (query.data ?? []).filter(workflow => /^(library|metadata|organizer|external_scores)\./.test(workflow.type));
  async function act(id: string, operation: "cancel" | "retry") {
    if (lock.current) return;
    lock.current = true; setError(null);
    try { if (operation === "cancel") await cancel.trigger(id); else await retry.trigger(id); }
    catch (failure) { setError(failure instanceof Error ? failure.message : t("operationFailed")); }
    finally { lock.current = false; }
  }
  return <section className="space-y-4">
    <div className="flex flex-wrap items-center justify-between gap-3"><h3 className="type-label text-ink-muted">{area("recentWorkflows")}</h3><Link href="/library/activity" className="focus-ring inline-flex min-h-11 items-center text-sm underline underline-offset-4">{t("actions.open-activity.label")}</Link></div>
    {query.error ? <StateMessage state="error">{t("loadFailed")}</StateMessage> : !query.data ? <StateMessage state="loading">{area("loading")}</StateMessage> : !workflows.length ? <StateMessage>{area("noWorkflows")}</StateMessage> : <ul className="divide-y divide-line border-y border-line">{workflows.map(workflow => <li key={workflow.id} className="flex min-w-0 flex-wrap items-start justify-between gap-3 py-4">
      <div className="min-w-0 flex-1"><p className="break-words text-sm">{workflowLabel(workflow.type, workflowText)}</p><p className="mt-1 break-words text-xs text-ink-muted">{workflow.error_message || workflow.result_summary || workflow.current_step || workflow.status}</p></div>
      {["queued", "running"].includes(workflow.status) ? <Button size="sm" disabled={cancel.isMutating || workflow.cancel_requested} onClick={() => void act(workflow.id, "cancel")}>{t("cancelWorkflow")}</Button> : ["failed", "cancelled"].includes(workflow.status) ? <Button size="sm" disabled={retry.isMutating} onClick={() => void act(workflow.id, "retry")}>{t("retryWorkflow")}</Button> : null}
    </li>)}</ul>}
    {error ? <InlineFeedback tone="error">{error}</InlineFeedback> : null}
  </section>;
}
