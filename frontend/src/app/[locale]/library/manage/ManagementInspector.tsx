"use client";

import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  ChevronRight,
  Clock3,
  Layers3,
  ListRestart,
  RefreshCw,
  Search,
  X,
} from "lucide-react";
import { useMemo, useState } from "react";

import { Button } from "@/components/ui/Button";
import { InlineFeedback, StateMessage } from "@/components/ui/Feedback";
import { useCancelWorkflow, useRetryWorkflow } from "@/hooks/useWorkflows";
import type {
  ManagementActionDefinition,
  ManagementActionId,
  ManagementConstellationModel,
  ManagementNode,
  ManagementNodeId,
} from "@/lib/management-constellation";
import type { WorkflowRunView } from "@/types/movie";

type Translate = (key: string, values?: Record<string, string | number>) => string;

export interface InspectorServiceDetails {
  description: string;
  detail?: string | null;
  error?: string | null;
}

const WORKFLOW_SERVICE: Record<string, ManagementNodeId> = {
  "library.reconcile": "sync",
  "library.scan_folder": "sync",
  "library.mark_path_missing": "sync",
  "metadata.scrape_library": "metadata",
  "organizer.organize_root": "organizer",
  "organizer.confirm_root_video": "organizer",
  "external_scores.refresh_library": "scores",
  "external_scores.refresh_film": "scores",
};

function childCluster(node: ManagementNode): ManagementNodeId | null {
  if (node.kind === "film") return "metadata-review";
  if (node.kind === "file") return "organization-review";
  if (node.kind === "missing") return "missing-items";
  return null;
}

function clusterAction(clusterId: ManagementNodeId | null): ManagementActionId | null {
  if (clusterId === "metadata-review") return "review-metadata";
  if (clusterId === "organization-review") return "organize-files";
  if (clusterId === "missing-items") return "cleanup-missing";
  return null;
}

function formatTime(value?: string | null) {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function InspectorActionList({ actions, busyActions, onExecute, t }: {
  actions: ManagementActionDefinition[];
  busyActions: Partial<Record<ManagementActionId, boolean>>;
  onExecute: (id: ManagementActionId) => void;
  t: Translate;
}) {
  if (actions.length === 0) return null;
  return (
    <div className="mt-7 space-y-2 border-t border-white/10 pt-5">
      {actions.map((action) => (
        <button key={action.id} type="button" disabled={Boolean(action.disabledReason) || busyActions[action.id]} onClick={() => onExecute(action.id)} className={`focus-ring flex min-h-11 w-full items-center justify-between gap-4 border px-4 text-left text-[10px] font-black tracking-[0.12em] uppercase transition disabled:cursor-not-allowed disabled:opacity-35 ${action.danger ? "border-red-400/30 bg-red-400/[0.06] text-red-300 hover:bg-red-400/[0.12]" : "border-white/12 text-neutral-300 hover:bg-white/[0.05] hover:text-white"}`}>
          <span>{t(`actions.${action.id}.label`)}</span>
          {busyActions[action.id] ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <ChevronRight className="h-3.5 w-3.5" />}
        </button>
      ))}
    </div>
  );
}
function WorkflowList({ workflows, t }: { workflows: WorkflowRunView[]; t: Translate }) {
  const cancel = useCancelWorkflow();
  const retry = useRetryWorkflow();
  if (workflows.length === 0) return null;
  return (
    <div className="mt-7 border-t border-white/10 pt-5">
      <p className="text-[9px] font-black tracking-[0.18em] text-neutral-600 uppercase">{t("workflows")}</p>
      <ul className="mt-3 space-y-2">
        {workflows.slice(0, 5).map((workflow) => (
          <li key={workflow.id} className="border border-white/10 bg-white/[0.025] p-3">
            <div className="flex items-start gap-3">
              {workflow.status === "running" ? <RefreshCw className="mt-0.5 h-3.5 w-3.5 shrink-0 animate-spin text-cyan-300" /> : workflow.status === "failed" ? <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-red-300" /> : <Clock3 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-neutral-500" />}
              <div className="min-w-0 flex-1">
                <p className="truncate text-[10px] font-bold text-neutral-300">{workflow.type}</p>
                <p className={`mt-1 line-clamp-2 text-[9px] leading-4 ${workflow.status === "failed" ? "text-red-300" : "text-neutral-600"}`}>{workflow.error_message || workflow.result_summary || workflow.current_step || workflow.status}</p>
              </div>
              {(workflow.status === "running" || workflow.status === "queued") ? <button type="button" disabled={cancel.isMutating} onClick={() => void cancel.trigger(workflow.id)} aria-label={t("cancelWorkflow")} className="focus-ring p-1.5 text-neutral-600 hover:text-white"><X className="h-3.5 w-3.5" /></button> : null}
              {(workflow.status === "failed" || workflow.status === "cancelled") ? <button type="button" disabled={retry.isMutating} onClick={() => void retry.trigger(workflow.id)} aria-label={t("retryWorkflow")} className="focus-ring p-1.5 text-neutral-600 hover:text-white"><ListRestart className="h-3.5 w-3.5" /></button> : null}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

function QueueSearch({ value, onChange, placeholder }: { value: string; onChange: (value: string) => void; placeholder: string }) {
  return (
    <label className="mt-5 flex min-h-10 items-center gap-3 border border-white/10 bg-black px-3">
      <Search className="h-3.5 w-3.5 text-neutral-600" /><span className="sr-only">{placeholder}</span>
      <input value={value} onChange={(event) => onChange(event.target.value)} placeholder={placeholder} className="min-w-0 flex-1 bg-transparent text-xs text-white outline-none placeholder:text-neutral-700" />
    </label>
  );
}

export default function ManagementInspector({
  node,
  model,
  serviceDetails,
  workflows,
  busyActions,
  onExecute,
  onSelect,
  t,
}: {
  node: ManagementNode;
  model: ManagementConstellationModel;
  serviceDetails: Partial<Record<ManagementNodeId, InspectorServiceDetails>>;
  workflows: WorkflowRunView[];
  busyActions: Partial<Record<ManagementActionId, boolean>>;
  onExecute: (id: ManagementActionId) => void;
  onSelect: (id: ManagementNodeId) => void;
  t: Translate;
}) {
  const [query, setQuery] = useState("");
  const [visibleCount, setVisibleCount] = useState(50);
  const [detailEntityId, setDetailEntityId] = useState<string | null>(node.entityId ?? null);
  const clusterId = node.kind === "cluster" ? node.id : childCluster(node);
  const actionId = clusterAction(clusterId);
  const selectedFilm = detailEntityId ? model.reviewFilms.find((film) => film.id === detailEntityId) : null;
  const selectedOrganization = detailEntityId ? model.organizationCandidates.find((item) => item.source_path === detailEntityId) : null;
  const selectedMissing = detailEntityId ? model.missingItems.find((item) => item.library_item_id === detailEntityId) : null;
  const details = serviceDetails[node.id];
  const nodeActions = model.actions.filter((action) => action.id !== "clear-data" && action.nodeIds.includes(node.id));
  const relatedWorkflows = node.kind === "service"
    ? workflows.filter((workflow) => WORKFLOW_SERVICE[workflow.type] === node.id)
    : node.id === "library" ? workflows : [];
  const normalizedQuery = query.trim().toLocaleLowerCase();
  const reviewResults = useMemo(() => model.reviewFilms.filter((film) => !normalizedQuery || `${film.title} ${film.original_title ?? ""} ${film.year ?? ""}`.toLocaleLowerCase().includes(normalizedQuery)), [model.reviewFilms, normalizedQuery]);
  const organizationResults = useMemo(() => model.organizationCandidates.filter((item) => !normalizedQuery || `${item.parsed_title} ${item.filename} ${item.parsed_year ?? ""}`.toLocaleLowerCase().includes(normalizedQuery)), [model.organizationCandidates, normalizedQuery]);
  const missingResults = useMemo(() => model.missingItems.filter((item) => !normalizedQuery || `${item.title} ${item.display_name ?? ""} ${item.year ?? ""}`.toLocaleLowerCase().includes(normalizedQuery)), [model.missingItems, normalizedQuery]);

  if (selectedFilm || selectedOrganization || selectedMissing) {
    const title = selectedFilm?.title || selectedOrganization?.parsed_title || selectedOrganization?.filename || selectedMissing?.title || t("unknownEdition");
    const detail = selectedFilm?.year
      || selectedOrganization?.filename
      || selectedMissing?.display_name
      || t("unknownEdition");
    return (
      <div className="flex min-h-full flex-col p-5 sm:p-6">
        <button type="button" onClick={() => { setDetailEntityId(null); if (clusterId) onSelect(clusterId); }} className="focus-ring inline-flex w-fit items-center gap-2 text-[9px] font-black tracking-[0.16em] text-neutral-600 uppercase hover:text-white"><ArrowLeft className="h-3.5 w-3.5" />{t("backToQueue")}</button>
        <span className="mt-8 flex h-11 w-11 items-center justify-center rounded-full border border-amber-300/30 bg-amber-300/[0.08] text-amber-200"><AlertTriangle className="h-4 w-4" /></span>
        <h3 className="mt-5 text-xl font-semibold text-white">{title}</h3>
        <p className="mt-2 break-words text-xs text-neutral-500">{detail}</p>
        {selectedMissing ? <p className="mt-5 text-xs text-neutral-600">{t("missingSince")}: {formatTime(selectedMissing.missing_since) || t("unknownTime")}</p> : null}
        <p className="mt-6 border-l border-white/15 pl-3 text-xs leading-5 text-neutral-500">{t("diagnosticOnly")}</p>
        {actionId ? <Button className="mt-auto" responsiveWidth onClick={() => onExecute(actionId)}>{t(`actions.${actionId}.label`)}</Button> : null}
      </div>
    );
  }

  if (clusterId) {
    const isMetadata = clusterId === "metadata-review";
    const isOrganization = clusterId === "organization-review";
    const results = isMetadata ? reviewResults : isOrganization ? organizationResults : missingResults;
    const searchPlaceholder = isMetadata ? t("searchReviews") : isOrganization ? t("searchFiles") : t("searchMissing");
    return (
      <div className="p-5 sm:p-6">
        <p className="text-[9px] font-black tracking-[0.18em] text-amber-200 uppercase">{t(`nodes.${isMetadata ? "metadataReview" : isOrganization ? "organizationReview" : "missingItems"}`)}</p>
        <h3 className="mt-3 text-2xl font-semibold tracking-tight text-white">{t("queueCount", { count: results.length })}</h3>
        <p className="mt-2 text-xs leading-5 text-neutral-500">{t(isMetadata ? "metadataQueueDescription" : isOrganization ? "organizationQueueDescription" : "missingQueueDescription")}</p>
        {actionId ? <Button className="mt-5" responsiveWidth onClick={() => onExecute(actionId)}>{t(`actions.${actionId}.label`)}</Button> : null}
        <QueueSearch value={query} onChange={setQuery} placeholder={searchPlaceholder} />
        {results.length === 0 ? <StateMessage className="mt-4">{t("noQueueMatches")}</StateMessage> : (
          <ul className="mt-4 divide-y divide-white/10 border-y border-white/10">
            {results.slice(0, visibleCount).map((item) => {
              const id = "id" in item ? item.id : "source_path" in item ? item.source_path : item.library_item_id;
              const title = "title" in item ? item.title : item.parsed_title || item.filename;
              const meta = "source_path" in item ? `${item.stable ? t("fileReady") : t("fileWaiting")} · ${item.filename}` : "display_name" in item ? item.display_name || item.year || t("unknownEdition") : item.year || t("unknownYear");
              return (
                <li key={id}>
                  <button type="button" onClick={() => setDetailEntityId(id)} className="focus-ring group flex w-full items-center justify-between gap-4 py-4 text-left">
                    <span className="min-w-0"><span className="block truncate text-xs font-semibold text-neutral-300 group-hover:text-white">{title}</span><span className="mt-1 block truncate text-[10px] text-neutral-600">{meta}</span></span>
                    <ChevronRight className="h-3.5 w-3.5 shrink-0 text-neutral-700" />
                  </button>
                </li>
              );
            })}
          </ul>
        )}
        {visibleCount < results.length ? <Button className="mt-4" responsiveWidth variant="ghost" onClick={() => setVisibleCount((value) => value + 50)}>{t("showMore", { count: Math.min(50, results.length - visibleCount) })}</Button> : null}
      </div>
    );
  }

  return (
    <div className="flex min-h-full flex-col p-5 sm:p-6">
      <div className="flex items-center justify-between gap-4"><p className="text-[9px] font-black tracking-[0.18em] text-cyan-300 uppercase">{t("inspector")}</p><span className={`text-[9px] font-bold tracking-wider uppercase ${node.state === "failed" ? "text-red-300" : node.state === "attention" ? "text-amber-200" : node.state === "running" ? "text-cyan-300" : "text-neutral-600"}`}>{t(`states.${node.state}`)}</span></div>
      <span className="mt-8 flex h-11 w-11 items-center justify-center rounded-full border border-white/10 text-cyan-300">{node.id === "library" ? <Layers3 className="h-4 w-4" /> : node.state === "failed" ? <AlertTriangle className="h-4 w-4" /> : node.state === "running" ? <RefreshCw className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}</span>
      <h3 className="mt-5 text-2xl font-semibold tracking-tight text-white">{t(`nodes.${node.id}`)}</h3>
      <p className="mt-3 text-xs leading-5 text-neutral-500">{details?.description || t("defaultNodeDescription")}</p>
      {details?.detail ? <p className="mt-4 break-words border-l border-white/15 pl-3 text-[10px] leading-5 text-neutral-400">{details.detail}</p> : null}
      {details?.error ? <InlineFeedback tone="error" className="mt-4">{details.error}</InlineFeedback> : null}
      {node.id === "library" ? <div className="mt-7 grid grid-cols-2 gap-px border border-white/10 bg-white/10"><div className="bg-[#030506] p-4"><p className="text-2xl font-semibold text-white">{node.count ?? 0}</p><p className="mt-1 text-[9px] text-neutral-600">{t("films")}</p></div><div className="bg-[#030506] p-4"><p className="text-2xl font-semibold text-amber-200">{model.attentionCount}</p><p className="mt-1 text-[9px] text-neutral-600">{t("attentionItems")}</p></div></div> : null}
      <InspectorActionList actions={nodeActions} busyActions={busyActions} onExecute={onExecute} t={t} />
      <WorkflowList workflows={relatedWorkflows} t={t} />
    </div>
  );
}
