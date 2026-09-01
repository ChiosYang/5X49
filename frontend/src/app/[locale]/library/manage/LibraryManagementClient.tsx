"use client";

import { X } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";
import useSWR from "swr";

import { InlineFeedback } from "@/components/ui/Feedback";
import { useLibrary } from "@/hooks/useLibrary";
import {
  useLibraryExternalScoresStatus,
  useLibraryOrganizeStatus,
  useLibraryScrapeStatus,
  useLibrarySyncStatus,
  useMediaDir,
  useRefreshLibraryExternalScores,
  useScanLibrary,
  useScrapeLibrary,
  useTmdbSettings,
} from "@/hooks/useSettings";
import { useWorkflowCache, useWorkflows } from "@/hooks/useWorkflows";
import { useRouter } from "@/i18n/routing";
import { API } from "@/lib/api";
import {
  buildManagementConstellation,
  type ManagementActionId,
  type ManagementNodeId,
} from "@/lib/management-constellation";
import type {
  MissingLibraryItemsResponse,
  OrganizationCandidate,
  WorkflowAccepted,
} from "@/types/movie";
import ManagementCommandLayer from "./ManagementCommandLayer";
import ManagementConstellation from "./ManagementConstellation";
import ManagementInspector, { type InspectorServiceDetails } from "./ManagementInspector";

type Feedback = { message: string; tone: "success" | "error" | "warning" };

function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
}

function useMediaQuery(query: string) {
  const [matches, setMatches] = useState(false);
  useEffect(() => {
    const media = window.matchMedia(query);
    const update = () => setMatches(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, [query]);
  return matches;
}

export default function LibraryManagementClient() {
  const t = useTranslations("LibraryManagement.constellation");
  const locale = useLocale();
  const router = useRouter();
  const isDesktop = useMediaQuery("(min-width: 1280px)");
  const isMobile = useMediaQuery("(max-width: 639px)");
  const [selectedId, setSelectedId] = useState<ManagementNodeId>("library");
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const [feedback, setFeedback] = useState<Feedback | null>(null);

  const library = useLibrary();
  const tmdb = useTmdbSettings();
  const mediaDir = useMediaDir();
  const sync = useLibrarySyncStatus();
  const metadata = useLibraryScrapeStatus();
  const scores = useLibraryExternalScoresStatus();
  const organizer = useLibraryOrganizeStatus();
  const organization = useSWR<OrganizationCandidate[]>(API.libraryOrganizationCandidates());
  const missing = useSWR<MissingLibraryItemsResponse>(API.libraryCleanupMissing());
  const workflowQuery = useWorkflows();
  const { upsertWorkflow, refreshWorkflows } = useWorkflowCache();

  const scanMutation = useScanLibrary();
  const metadataMutation = useScrapeLibrary();
  const scoresMutation = useRefreshLibraryExternalScores();

  const films = useMemo(() => library.data ?? [], [library.data]);
  const workflows = useMemo(() => workflowQuery.data ?? [], [workflowQuery.data]);
  const formatDate = useCallback((value?: string | null) => {
    if (!value) return t("never");
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? value : date.toLocaleString(locale);
  }, [locale, t]);

  const model = useMemo(() => buildManagementConstellation({
    films,
    libraryAvailable: !library.error && !workflowQuery.error,
    organizationCandidates: organization.data ?? [],
    missingItems: missing.data?.items ?? [],
    workflows,
    tmdbConfigured: Boolean(tmdb.data?.configured),
    watcher: {
      state: sync.data ? (sync.data.watcher.running ? "running" : "idle") : undefined,
      running: sync.data?.watcher.running,
      configured: Boolean(mediaDir.data?.media_dir),
      error: sync.error || mediaDir.error
        ? errorMessage(sync.error || mediaDir.error, t("loadFailed"))
        : sync.data?.watcher.last_error,
      detail: mediaDir.data?.media_dir,
    },
    sync: {
      state: sync.data?.sync.state,
      error: sync.error || missing.error
        ? errorMessage(sync.error || missing.error, t("loadFailed"))
        : sync.data?.sync.last_error,
      detail: sync.data?.sync.last_finished_at,
    },
    metadata: {
      state: metadata.data?.state,
      error: metadata.error || tmdb.error
        ? errorMessage(metadata.error || tmdb.error, t("loadFailed"))
        : metadata.data?.last_error,
      detail: metadata.data?.last_finished_at,
    },
    scores: {
      state: scores.data?.state,
      error: scores.error ? errorMessage(scores.error, t("loadFailed")) : scores.data?.last_error,
      detail: scores.data?.last_finished_at,
    },
    organizer: {
      state: organizer.data?.state,
      error: organizer.error || organization.error
        ? errorMessage(organizer.error || organization.error, t("loadFailed"))
        : organizer.data?.last_error,
      detail: organizer.data?.last_finished_at,
    },
    childLimit: isMobile ? 6 : 8,
  }), [
    films,
    isMobile,
    library.error,
    mediaDir.data?.media_dir,
    mediaDir.error,
    metadata.data,
    metadata.error,
    missing.data,
    missing.error,
    organization.data,
    organization.error,
    organizer.data,
    organizer.error,
    scores.data,
    scores.error,
    sync.data,
    sync.error,
    t,
    tmdb.data?.configured,
    tmdb.error,
    workflowQuery.error,
    workflows,
  ]);

  const effectiveSelectedId = model.nodes.some((node) => node.id === selectedId)
    ? selectedId
    : "library";
  const selectedNode = model.nodes.find((node) => node.id === effectiveSelectedId)
    ?? model.nodes[0];
  const runningWorkflow = useCallback((nodeId: ManagementNodeId) => workflows.some((workflow) => {
    if (workflow.status !== "running" && workflow.status !== "queued") return false;
    if (nodeId === "sync") return workflow.type.startsWith("library.");
    if (nodeId === "metadata") return workflow.type.startsWith("metadata.");
    if (nodeId === "scores") return workflow.type.startsWith("external_scores.");
    if (nodeId === "organizer") return workflow.type.startsWith("organizer.");
    return false;
  }), [workflows]);
  const busyActions = useMemo<Partial<Record<ManagementActionId, boolean>>>(() => ({
    scan: scanMutation.isMutating || sync.data?.sync.state === "running" || runningWorkflow("sync"),
    "scrape-metadata": metadataMutation.isMutating || metadata.data?.state === "running" || runningWorkflow("metadata"),
    "refresh-scores": scoresMutation.isMutating || scores.data?.state === "running" || runningWorkflow("scores"),
  }), [
    metadata.data?.state,
    metadataMutation.isMutating,
    scores.data?.state,
    scoresMutation.isMutating,
    scanMutation.isMutating,
    sync.data?.sync.state,
    runningWorkflow,
  ]);

  const serviceDetails = useMemo<Partial<Record<ManagementNodeId, InspectorServiceDetails>>>(() => ({
    library: {
      description: t("details.library"),
      detail: sync.data?.sync.last_result
        ? t("lastScanSummary", {
            scanned: sync.data.sync.last_result.scanned ?? 0,
            added: sync.data.sync.last_result.added ?? 0,
            missing: sync.data.sync.last_result.missing ?? 0,
          })
        : t("lastRunAt", { value: formatDate(sync.data?.sync.last_finished_at) }),
      error: library.error || workflowQuery.error
        ? errorMessage(library.error || workflowQuery.error, t("libraryLoadFailed"))
        : null,
    },
    watcher: {
      description: t("details.watcher"),
      detail: mediaDir.data?.media_dir || t("mediaDirectoryMissing"),
      error: sync.data?.watcher.last_error || (mediaDir.error ? errorMessage(mediaDir.error, t("loadFailed")) : null),
    },
    sync: {
      description: t("details.sync"),
      detail: t("lastRunAt", { value: formatDate(sync.data?.sync.last_finished_at) }),
      error: sync.data?.sync.last_error || (sync.error || missing.error ? errorMessage(sync.error || missing.error, t("loadFailed")) : null),
    },
    metadata: {
      description: t("details.metadata"),
      detail: tmdb.data?.configured
        ? t("lastRunAt", { value: formatDate(metadata.data?.last_finished_at) })
        : t("tmdbNotConfigured"),
      error: metadata.data?.last_error || (metadata.error || tmdb.error ? errorMessage(metadata.error || tmdb.error, t("loadFailed")) : null),
    },
    scores: {
      description: t("details.scores"),
      detail: t("lastRunAt", { value: formatDate(scores.data?.last_finished_at) }),
      error: scores.data?.last_error || (scores.error ? errorMessage(scores.error, t("loadFailed")) : null),
    },
    organizer: {
      description: t("details.organizer"),
      detail: t("organizationSummary", {
        count: organization.data?.length ?? 0,
        value: formatDate(organizer.data?.last_finished_at),
      }),
      error: organizer.data?.last_error || (organizer.error || organization.error ? errorMessage(organizer.error || organization.error, t("loadFailed")) : null),
    },
  }), [
    formatDate,
    library.error,
    mediaDir.data?.media_dir,
    mediaDir.error,
    metadata.data,
    metadata.error,
    missing.error,
    organization.data?.length,
    organization.error,
    organizer.data,
    organizer.error,
    scores.data,
    scores.error,
    sync.data,
    sync.error,
    t,
    tmdb.data?.configured,
    tmdb.error,
    workflowQuery.error,
  ]);

  const selectNode = useCallback((id: ManagementNodeId) => {
    setSelectedId(id);
    if (!isDesktop) setInspectorOpen(true);
  }, [isDesktop]);

  useEffect(() => {
    if (window.location.hash === "#metadata-reviews") {
      router.replace("/library?view=metadata");
    } else if (window.location.hash === "#root-video-reviews") {
      router.replace("/library?view=inbox");
    }
  }, [router]);

  const registerWorkflow = useCallback((result: unknown) => {
    const accepted = result as Partial<WorkflowAccepted> | undefined;
    if (accepted?.workflow?.id) upsertWorkflow(accepted.workflow);
    else refreshWorkflows();
  }, [refreshWorkflows, upsertWorkflow]);

  const runAction = useCallback(async (
    operation: () => Promise<unknown>,
    successKey: string,
  ) => {
    setFeedback(null);
    try {
      const result = await operation();
      registerWorkflow(result);
      setFeedback({ message: t(successKey), tone: "success" });
      return result;
    } catch (error) {
      setFeedback({ message: errorMessage(error, t("operationFailed")), tone: "error" });
      return null;
    }
  }, [registerWorkflow, t]);

  const executeAction = useCallback((id: ManagementActionId) => {
    const action = model.actions.find((item) => item.id === id);
    if (!action || action.disabledReason || busyActions[id]) return;
    if (action.destination) {
      router.push(action.destination);
    } else if (id === "scan") {
      void runAction(() => scanMutation.trigger(), "feedback.scan");
    } else if (id === "scrape-metadata") {
      void runAction(() => metadataMutation.trigger(), "feedback.scrape");
    } else if (id === "refresh-scores") {
      void runAction(() => scoresMutation.trigger(), "feedback.scores");
    }
  }, [
    busyActions,
    metadataMutation,
    model.actions,
    router,
    runAction,
    scanMutation,
    scoresMutation,
  ]);

  return (
    <main className="min-h-screen overflow-x-hidden bg-[#020405] pb-8 text-white selection:bg-cyan-200 selection:text-black">
      <header className="page-x flex flex-col gap-5 border-b border-white/10 pt-24 pb-6 sm:pt-28 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-[9px] font-black tracking-[0.22em] text-cyan-300 uppercase">{t("eyebrow")}</p>
          <h1 className="mt-3 text-3xl font-semibold tracking-[-0.04em] sm:text-5xl">{t("title")}</h1>
          <p className="mt-3 max-w-2xl text-xs leading-5 tracking-wide text-neutral-500 sm:text-sm">{t("subtitle")}</p>
        </div>
        <div className="flex flex-wrap items-center gap-3 text-[9px] font-bold tracking-[0.14em] uppercase">
          <span className="inline-flex min-h-9 items-center gap-2 border border-white/10 px-3 text-neutral-500">
            <span className={`h-1.5 w-1.5 rounded-full ${model.nodes.some((node) => node.state === "failed") ? "bg-red-400" : model.attentionCount ? "bg-amber-300" : "bg-emerald-300"}`} />
            {model.nodes.some((node) => node.state === "failed") ? t("systemFailed") : model.attentionCount ? t("systemAttention", { count: model.attentionCount }) : t("systemHealthy")}
          </span>
          <span className="hidden min-h-9 items-center border border-white/10 px-3 text-neutral-700 sm:inline-flex">{t("keyboardHint")}</span>
          <ManagementCommandLayer actions={model.actions} attentionCount={model.attentionCount} busyActions={busyActions} onExecute={executeAction} t={t} />
        </div>
      </header>

      <section className="page-x py-5 sm:py-7">
        <div className="overflow-hidden border border-white/10 bg-black shadow-[0_35px_100px_rgba(0,0,0,.35)] xl:grid xl:grid-cols-[minmax(0,1fr)_24rem]">
          <ManagementConstellation
            model={model}
            selectedId={effectiveSelectedId}
            onSelect={selectNode}
            onReset={() => {
              setSelectedId("library");
              if (!isDesktop) setInspectorOpen(false);
            }}
            t={t}
          />
          {isDesktop ? (
            <aside aria-label={t("inspector")} className="scrollbar-minimal max-h-[calc(100vh-12.5rem)] min-h-[38rem] overflow-y-auto border-l border-white/10 bg-[#050708]">
              <ManagementInspector
                key={selectedNode.id}
                node={selectedNode}
                model={model}
                serviceDetails={serviceDetails}
                workflows={workflows}
                busyActions={busyActions}
                onExecute={executeAction}
                onSelect={selectNode}
                t={t}
              />
            </aside>
          ) : null}
        </div>
      </section>

      {!isDesktop && inspectorOpen ? (
        <div className="z-overlay fixed inset-0 bg-black/45 md:bg-black/25" onMouseDown={(event) => { if (event.target === event.currentTarget) setInspectorOpen(false); }}>
          <aside aria-label={t("inspector")} className="scrollbar-minimal absolute right-0 bottom-0 left-0 max-h-[76vh] overflow-y-auto border-t border-white/15 bg-[#050708] shadow-2xl md:top-20 md:bottom-0 md:left-auto md:w-[25rem] md:max-h-none md:border-t-0 md:border-l">
            <div className="sticky top-0 z-20 flex items-center justify-between border-b border-white/10 bg-[#050708]/95 px-5 py-3 backdrop-blur-md">
              <span className="h-1 w-10 rounded-full bg-white/15 md:hidden" />
              <span className="hidden text-[9px] font-black tracking-[0.16em] text-neutral-600 uppercase md:block">{t("inspector")}</span>
              <button type="button" aria-label={t("closeInspector")} onClick={() => setInspectorOpen(false)} className="focus-ring ml-auto p-2 text-neutral-600 hover:text-white"><X className="h-4 w-4" /></button>
            </div>
            <ManagementInspector
              key={selectedNode.id}
              node={selectedNode}
              model={model}
              serviceDetails={serviceDetails}
              workflows={workflows}
              busyActions={busyActions}
              onExecute={executeAction}
              onSelect={selectNode}
              t={t}
            />
          </aside>
        </div>
      ) : null}

      <div aria-live="polite" aria-atomic="true" className="pointer-events-none fixed right-4 bottom-24 z-50 max-w-sm">
        {feedback ? (
          <div className={`pointer-events-auto border bg-neutral-950 px-4 py-3 shadow-2xl ${feedback.tone === "error" ? "border-red-400/40" : feedback.tone === "warning" ? "border-amber-300/40" : "border-emerald-300/35"}`}>
            <InlineFeedback tone={feedback.tone}>{feedback.message}</InlineFeedback>
          </div>
        ) : null}
      </div>

    </main>
  );
}
