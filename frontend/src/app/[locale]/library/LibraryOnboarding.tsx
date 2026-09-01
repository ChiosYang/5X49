"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
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
  useLibrarySyncStatus,
  useMediaDir,
  useScanLibrary,
  useTmdbSettings,
} from "@/hooks/useSettings";
import { getFirstScanState, isMediaDirectoryReady } from "@/lib/library-onboarding";
import FirstRunIntro from "./FirstRunIntro";

export default function LibraryOnboarding({ rootVideoCount }: { rootVideoCount: number }) {
  const t = useTranslations("Onboarding");
  const router = useRouter();
  const { data: mediaDirectory } = useMediaDir();
  const { data: tmdb } = useTmdbSettings();
  const [scanRequested, setScanRequested] = useState(false);
  const [baselineFinishedAt, setBaselineFinishedAt] = useState<string | null>();
  const { data: syncStatus } = useLibrarySyncStatus((latestData) => {
    if (!scanRequested) return 5000;
    const lastFinishedAt = latestData?.sync.last_finished_at;
    const finished = Boolean(lastFinishedAt && lastFinishedAt !== baselineFinishedAt);
    return finished ? 5000 : 1000;
  });
  const {
    trigger: scanLibrary,
    isMutating: queueing,
    error: queueError,
    reset: resetScan,
  } = useScanLibrary();
  const refreshedScan = useRef<string | null>(null);

  const directoryReady = isMediaDirectoryReady(mediaDirectory);
  const sync = syncStatus?.sync;
  const derivedScanState = getFirstScanState({
    requested: scanRequested,
    queueing,
    syncState: sync?.state,
    lastFinishedAt: sync?.last_finished_at,
    baselineFinishedAt,
    lastError: sync?.last_error,
    scanned: sync?.last_result?.scanned,
  });
  const scanState = queueError ? "error" : derivedScanState;
  const scanActive = scanState === "queueing" || scanState === "queued" || scanState === "running";
  const scanned = sync?.last_result?.scanned ?? 0;
  const added = sync?.last_result?.added ?? 0;

  useEffect(() => {
    if (scanState !== "success" || !sync?.last_finished_at) return;
    if (refreshedScan.current === sync.last_finished_at) return;
    refreshedScan.current = sync.last_finished_at;
    router.refresh();
  }, [router, scanState, sync?.last_finished_at]);

  const handleScan = async () => {
    resetScan();
    setBaselineFinishedAt(sync?.last_finished_at ?? null);
    setScanRequested(true);
    try {
      await scanLibrary();
    } catch {
      // Mutation state renders the backend validation detail.
    }
  };

  const scanFeedback = (() => {
    if (scanState === "queueing") return <InlineFeedback>{t("scanQueueing")}</InlineFeedback>;
    if (scanState === "queued") return <InlineFeedback>{t("scanQueued")}</InlineFeedback>;
    if (scanState === "running") return <InlineFeedback>{t("scanRunning")}</InlineFeedback>;
    if (scanState === "success") {
      return <InlineFeedback tone="success">{t("scanSuccess", { scanned, added })}</InlineFeedback>;
    }
    if (scanState === "empty") return <InlineFeedback tone="warning">{t("scanEmpty")}</InlineFeedback>;
    if (scanState === "error") {
      const message = queueError instanceof Error ? queueError.message : sync?.last_error || t("scanFailed");
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
          <div className="space-y-10">
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
              <MediaDirectoryControl autoSave inlineStatus />
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
                    disabled={!directoryReady || scanActive}
                    onClick={handleScan}
                  >
                    {scanActive ? t("scanning") : scanState === "error" || scanState === "empty" ? t("scanAgain") : t("scanNow")}
                  </Button>
                  <div className="min-h-5 flex-1" aria-live="polite">{scanFeedback}</div>
                </div>

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
          </div>

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
