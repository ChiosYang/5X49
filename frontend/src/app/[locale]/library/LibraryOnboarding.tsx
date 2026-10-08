"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import useSWR from "swr";
import { API } from "@/lib/api";
import type { WorkflowRunView } from "@/types/movie";
import { useTranslations } from "next-intl";
import {
  ArrowUpRight,
  CheckCircle2,
  Circle,
  FolderOpen,
  ScanSearch,
  Sparkles,
  TriangleAlert,
} from "lucide-react";
import MediaDirectoryControl from "@/components/settings/MediaDirectoryControl";
import { Button } from "@/components/ui/Button";
import { InlineFeedback } from "@/components/ui/Feedback";
import { Link } from "@/i18n/routing";
import {
  useMediaDir,
  useScanLibrary,
  useUpdateMediaDir,
  useTmdbSettings,
} from "@/hooks/useSettings";
import { getWorkflowScanState, isMediaDirectoryReady, saveDirectoryAndScan } from "@/lib/library-onboarding";
import FirstRunIntro from "./FirstRunIntro";

export default function LibraryOnboarding({ rootVideoCount }: { rootVideoCount: number }) {
  const t = useTranslations("Onboarding");
  const router = useRouter();
  const { data: mediaDirectory } = useMediaDir();
  const { data: tmdb } = useTmdbSettings();
  const [directoryDraft, setDirectoryDraft] = useState<string>();
  const { data: scanWorkflowId, mutate: rememberScanWorkflow } = useSWR<string | null>(
    "5x49:first-scan-workflow",
    () => { try { return sessionStorage.getItem("5x49:first-scan-workflow"); } catch { return null; } },
    { revalidateOnFocus: false },
  );
  const [preparing, setPreparing] = useState(false);
  const [scanError, setScanError] = useState<string | null>(null);
  const submitting = useRef(false);
  const { trigger: updateMediaDir } = useUpdateMediaDir();
  const { trigger: scanLibrary } = useScanLibrary();
  const { data: scanWorkflow, error: workflowError } = useSWR<WorkflowRunView | null>(
    scanWorkflowId ? API.workflow(scanWorkflowId) : null,
    async (url: string) => {
      const response = await fetch(url);
      if (response.status === 404) return null;
      if (!response.ok) throw new Error(t("scanStatusUnavailable"));
      return response.json();
    },
    { refreshInterval: (workflow) => workflow === undefined || (workflow !== null && ["queued", "running"].includes(workflow.status)) ? 1000 : 0 },
  );
  const refreshedScan = useRef<string | null>(null);

  const directoryReady = isMediaDirectoryReady(mediaDirectory) && (directoryDraft === undefined || directoryDraft.trim() === mediaDirectory?.media_dir);
  const scanState = preparing ? "queueing" : scanError || scanWorkflow === null ? "error" : getWorkflowScanState(scanWorkflow, preparing, Boolean(scanWorkflowId));
  const scanActive = scanState === "queueing" || scanState === "queued" || scanState === "running" || scanState === "cancelling";
  const directoryValue = directoryDraft ?? mediaDirectory?.media_dir ?? "";

  useEffect(() => {
    if ((scanState !== "success" && scanState !== "empty") || !scanWorkflow?.finished_at) return;
    if (refreshedScan.current === scanWorkflow.finished_at) return;
    refreshedScan.current = scanWorkflow.finished_at;
    router.refresh();
  }, [router, scanState, scanWorkflow?.finished_at]);

  const handleScan = async () => {
    if (submitting.current || scanActive || scanWorkflowId === undefined) return;
    submitting.current = true;
    setPreparing(true);
    setScanError(null);
    try {
      const result = await saveDirectoryAndScan(directoryValue, updateMediaDir, scanLibrary);
      void rememberScanWorkflow(result.workflow_id, false);
      try { sessionStorage.setItem("5x49:first-scan-workflow", result.workflow_id); } catch { /* Storage is optional. */ }
    } catch (error) {
      setScanError(error instanceof Error ? error.message : t("scanFailed"));
    } finally {
      submitting.current = false;
      setPreparing(false);
    }
  };

  const scanFeedback = (() => {
    if (workflowError && !scanError) return <InlineFeedback tone="error">{t("scanStatusUnavailable")}</InlineFeedback>;
    if (scanState === "cancelled" || scanState === "cancelling") return <InlineFeedback tone="warning">{t(scanState === "cancelled" ? "scanCancelled" : "scanCancelling")}</InlineFeedback>;
    if (scanState === "queueing") return <InlineFeedback>{t("scanQueueing")}</InlineFeedback>;
    if (scanState === "queued") return <InlineFeedback>{t("scanQueued")}</InlineFeedback>;
    if (scanState === "running") return <InlineFeedback>{t("scanRunning")}</InlineFeedback>;
    if (scanState === "success") {
      return <InlineFeedback tone="success">{scanWorkflow?.progress?.counts ? t("scanSuccess", { scanned: scanWorkflow.progress.counts.scanned ?? 0, added: scanWorkflow.progress.counts.added ?? 0 }) : t("scanCompleted")}</InlineFeedback>;
    }
    if (scanState === "empty") return <InlineFeedback tone="warning">{t("scanEmpty")}</InlineFeedback>;
    if (scanState === "error") {
      const message = scanError || scanWorkflow?.error_message || t(scanWorkflow === null ? "scanNoLongerAvailable" : "scanFailed");
      return <InlineFeedback tone="error">{message}</InlineFeedback>;
    }
    return null;
  })();

  return (
    <>
      <FirstRunIntro />
      <section className="pt-10" aria-labelledby="onboarding-title">
        <header className="max-w-[57rem]">
          <h2 id="onboarding-title" className="max-w-3xl pt-3 font-serif text-3xl tracking-tight text-ink md:text-5xl">
            {t("title")}
          </h2>
          <p className="mt-4 text-sm leading-6 text-ink-subtle">{t("description")}</p>
        </header>

        <div className="mt-10 grid gap-10 lg:min-h-[27.0625rem] lg:grid-cols-[minmax(0,1.35fr)_minmax(18rem,0.65fr)] lg:gap-12">
          <form className="space-y-10" onSubmit={(event) => { event.preventDefault(); void handleScan(); }}>
            <article className="border-b border-line pb-10">
              <div className="mb-6 flex items-start gap-4">
                <span className="flex h-10 w-10 shrink-0 items-center justify-center border border-line-strong bg-surface-raised">
                  {directoryReady ? (
                    <CheckCircle2 className="h-4 w-4 text-success" />
                  ) : (
                    <FolderOpen className="h-4 w-4 text-ink-muted" />
                  )}
                </span>
                <div>
                  <p className="type-label text-ink-disabled">{t("step", { number: 1 })}</p>
                  <h3 className="mt-1 text-lg font-medium text-ink">{t("directoryTitle")}</h3>
                </div>
              </div>
              <MediaDirectoryControl inlineStatus managedValue={directoryValue} onValueChange={setDirectoryDraft} disabled={scanActive} />
            </article>

            <article className="flex items-start gap-4">
              <span className="flex h-10 w-10 shrink-0 items-center justify-center border border-line-strong bg-surface-raised">
                {scanState === "success" ? (
                  <CheckCircle2 className="h-4 w-4 text-success" />
                ) : scanState === "error" || scanState === "empty" ? (
                  <TriangleAlert className="h-4 w-4 text-warning" />
                ) : (
                  <ScanSearch className="h-4 w-4 text-ink-muted" />
                )}
              </span>
              <div className="min-w-0 flex-1">
                <p className="type-label text-ink-disabled">{t("step", { number: 2 })}</p>
                <h3 className="mt-1 text-lg font-medium text-ink">{t("scanTitle")}</h3>
                <p className="mt-2 text-xs leading-5 text-ink-subtle">{t("scanDescription")}</p>

                <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:items-center">
                  <Button
                    variant="primary"
                    responsiveWidth
                    busy={scanActive}
                    disabled={!directoryValue.trim() || scanActive || scanWorkflowId === undefined}
                    type="submit"
                  >
                    {scanActive ? t("scanning") : scanState === "error" || scanState === "empty" ? t("scanAgain") : t("scanNow")}
                  </Button>
                  <div className="min-h-5 flex-1" aria-live="polite">{scanFeedback}</div>
                </div>

                <p className="mt-3 break-all text-xs text-ink-subtle">{t("scanDirectory", { path: directoryValue })}</p>
                {!directoryReady ? (
                  <p className="mt-3 text-xs leading-5 text-warning">{t("scanNeedsDirectory")}</p>
                ) : null}

                {scanState === "empty" ? (
                  <div className="mt-6 border-l border-warning/50 bg-warning/5 p-5">
                    <h4 className="text-sm font-medium text-ink">{t("emptyHelpTitle")}</h4>
                    <p className="mt-2 text-xs leading-5 text-ink-subtle">{t("emptyHelpDescription")}</p>
                    <pre className="mt-4 overflow-x-auto bg-canvas/70 p-4 text-xs leading-6 text-ink-muted">
{`Movies/
└── Film Title (2024)/
    ├── Film Title (2024).mkv
    └── movie.nfo  # optional`}
                    </pre>
                    <p className="mt-3 text-xs leading-5 text-ink-disabled">{t("supportedFiles")}</p>
                  </div>
                ) : null}
              </div>
            </article>
          </form>

          <aside className="space-y-8 border-t border-line pt-8 lg:border-t-0 lg:border-l lg:pt-0 lg:pl-8">
            <div>
              <div className="flex items-center gap-2">
                <Sparkles className="h-4 w-4 text-ink-muted" />
                <h3 className="type-label text-ink-muted">{t("optionalTitle")}</h3>
              </div>
              <ul className="mt-5 space-y-4 text-xs leading-5">
                <li className="flex items-start gap-3">
                  {tmdb?.configured ? (
                    <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-success" />
                  ) : (
                    <Circle className="mt-0.5 h-4 w-4 shrink-0 text-ink-disabled" />
                  )}
                  <span>
                    <strong className="block font-medium text-ink">TMDB</strong>
                    <span className="text-ink-disabled">
                      {tmdb?.configured ? t("tmdbConfigured") : t("tmdbOptional")}
                    </span>
                  </span>
                </li>
                <li className="flex items-start gap-3">
                  <Circle className="mt-0.5 h-4 w-4 shrink-0 text-ink-disabled" />
                  <span>
                    <strong className="block font-medium text-ink">OpenRouter</strong>
                    <span className="text-ink-disabled">{t("aiOptional")}</span>
                  </span>
                </li>
              </ul>
              <Link
                href="/settings?section=integrations"
                className="focus-ring mt-5 inline-flex items-center gap-2 text-xs font-medium tracking-widest text-ink-muted uppercase hover:text-ink"
              >
                {t("configureIntegrations")}
                <ArrowUpRight className="h-3.5 w-3.5" />
              </Link>
            </div>

            <div className="border-t border-line pt-6">
              <h3 className="type-label text-ink-muted">{t("helpTitle")}</h3>
              <div className="mt-4 flex flex-col items-start gap-3">
                <Link className="focus-ring text-xs text-ink-subtle hover:text-ink" href="/library/activity">
                  {t("viewActivity")}
                </Link>
                <Link
                  className="focus-ring text-xs text-ink-subtle hover:text-ink"
                  href={rootVideoCount > 0 ? "/library?view=inbox" : "/settings?section=library"}
                >
                  {rootVideoCount > 0 ? t("organizeRootCount", { count: rootVideoCount }) : t("openManagement")}
                </Link>
              </div>
            </div>
          </aside>
        </div>
      </section>
    </>
  );
}
