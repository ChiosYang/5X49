"use client";

import { useState } from "react";
import { ArrowUpRight } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { Link } from "@/i18n/routing";
import LibrarianTerminal from "@/components/LibrarianTerminal";
import {
  ActionButton,
  ActionCard,
  StatusTile,
} from "@/components/settings/SettingsPrimitives";
import {
  useCleanupMissingMovies,
  useClearLibraryData,
  useLibraryExternalScoresStatus,
  useLibraryOrganizeStatus,
  useLibraryScrapeStatus,
  useLibrarySyncStatus,
  useOrganizeRootVideos,
  useReconcileLibrary,
  useRefreshLibraryExternalScores,
  useScanLibrary,
  useScrapeLibrary,
  useTmdbSettings,
} from "@/hooks/useSettings";

function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
}

export default function LibraryManagementClient() {
  const t = useTranslations("LibraryManagement");
  const settingsT = useTranslations("Settings");
  const locale = useLocale();
  const [terminalOpen, setTerminalOpen] = useState(false);

  const { data: tmdbData } = useTmdbSettings();
  const { data: syncStatus } = useLibrarySyncStatus();
  const { data: scrapeStatus } = useLibraryScrapeStatus();
  const { data: externalScoresStatus } = useLibraryExternalScoresStatus();
  const { data: organizeStatus } = useLibraryOrganizeStatus();

  const {
    trigger: scanLibrary,
    isMutating: isScanning,
    data: scanResult,
    error: scanError,
  } = useScanLibrary();
  const {
    trigger: reconcileLibrary,
    isMutating: isReconciling,
    data: reconcileResult,
    error: reconcileError,
  } = useReconcileLibrary();
  const {
    trigger: scrapeLibrary,
    isMutating: isScraping,
    data: scrapeResult,
    error: scrapeError,
  } = useScrapeLibrary();
  const {
    trigger: refreshExternalScores,
    isMutating: isRefreshingScores,
    data: externalScoresResult,
    error: externalScoresError,
  } = useRefreshLibraryExternalScores();
  const {
    trigger: organizeRootVideos,
    isMutating: isOrganizing,
    data: organizeResult,
    error: organizeError,
  } = useOrganizeRootVideos();
  const {
    trigger: cleanupMissing,
    isMutating: isCleaning,
    data: cleanupResult,
    error: cleanupError,
  } = useCleanupMissingMovies();
  const {
    trigger: clearLibraryData,
    isMutating: isClearing,
    data: clearResult,
    error: clearError,
  } = useClearLibraryData();

  const formatDate = (value: string | null | undefined) =>
    value ? new Date(value).toLocaleString(locale) : t("never");
  const statusLabel = (state: string | undefined) => {
    if (state === "running") return t("running");
    if (state === "failed" || state === "error") return t("failed");
    return t("idle");
  };
  const run = async (operation: () => Promise<unknown>) => {
    try {
      await operation();
    } catch {
      // Each mutation exposes its localized error in the relevant card.
    }
  };

  const scanMessage = scanError
    ? errorMessage(scanError, t("scanFailed"))
    : scanResult
      ? t("scanStarted")
      : undefined;
  const reconcileMessage = reconcileError
    ? errorMessage(reconcileError, t("reconcileFailed"))
    : reconcileResult
      ? t("reconcileSummary", {
          scanned: reconcileResult.scanned ?? 0,
          missing: reconcileResult.missing ?? 0,
        })
      : undefined;
  const scrapeMessage = scrapeError
    ? errorMessage(scrapeError, t("scrapeFailed"))
    : scrapeResult
      ? t("scrapeStarted")
      : scrapeStatus?.last_result
        ? t("scrapeSummary", {
            succeeded: scrapeStatus.last_result.succeeded ?? 0,
            review: scrapeStatus.last_result.needs_review ?? 0,
          })
        : undefined;
  const scoresMessage = externalScoresError
    ? errorMessage(externalScoresError, settingsT("externalScoresFailed"))
    : externalScoresResult
      ? settingsT("externalScoresStarted")
      : externalScoresStatus?.last_result
        ? settingsT("externalScoresSummary", {
            updated: externalScoresStatus.last_result.updated ?? 0,
            skipped: externalScoresStatus.last_result.skipped ?? 0,
          })
        : undefined;
  const organizeMessage = organizeError
    ? errorMessage(organizeError, t("organizeFailed"))
    : organizeResult
      ? t("organizeStarted")
      : organizeStatus?.last_result
        ? t("organizeSummary", {
            organized: organizeStatus.last_result.organized ?? 0,
            review: organizeStatus.last_result.needs_review ?? 0,
          })
        : undefined;
  const cleanupMessage = cleanupError
    ? errorMessage(cleanupError, t("cleanupFailed"))
    : cleanupResult
      ? t("cleanupSummary", { deleted: cleanupResult.deleted ?? 0 })
      : undefined;
  const clearMessage = clearError
    ? errorMessage(clearError, settingsT("clearAllDataFailed"))
    : clearResult
      ? settingsT("clearAllDataSummary", {
          movies: clearResult.deleted.movies,
          userStates: clearResult.deleted.user_states,
          jobs: clearResult.deleted.jobs,
          events: clearResult.deleted.events,
        })
      : undefined;

  const handleClearLibraryData = () => {
    if (!window.confirm(settingsT("clearAllDataConfirm"))) return;
    void run(() => clearLibraryData());
  };

  return (
    <div className="min-h-screen bg-black text-white selection:bg-white selection:text-black">
      <div className="w-full">
        <header className="border-b border-neutral-900 px-6 py-16 pt-28 sm:px-8 md:px-16 md:py-24 md:pt-32">
          <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <h1 className="break-words text-4xl font-bold uppercase leading-none tracking-tight sm:text-5xl md:text-7xl">
                {t("title")}
              </h1>
              <p className="mt-4 max-w-2xl text-sm uppercase leading-6 tracking-widest text-neutral-500">
                {t("subtitle")}
              </p>
            </div>
            <div className="flex flex-wrap gap-3">
              <Link
                href="/settings?section=library"
                className="inline-flex min-h-11 items-center gap-2 border border-neutral-800 px-4 text-xs font-medium uppercase tracking-widest text-neutral-300 transition-colors hover:border-neutral-600 hover:text-white"
              >
                {t("openSettings")}
                <ArrowUpRight className="h-3.5 w-3.5" />
              </Link>
              <Link
                href="/library/activity"
                className="inline-flex min-h-11 items-center gap-2 bg-white px-4 text-xs font-medium uppercase tracking-widest text-black transition-colors hover:bg-neutral-200"
              >
                {t("viewActivity")}
                <ArrowUpRight className="h-3.5 w-3.5" />
              </Link>
            </div>
          </div>
        </header>

        <section className="space-y-16 px-6 py-12 sm:px-8 md:px-16 md:py-16">
        <section className="space-y-6">
          <div>
            <h2 className="text-2xl font-bold uppercase tracking-tight text-white">{t("statusOverview")}</h2>
            <p className="mt-1 text-xs leading-5 text-neutral-600">{t("statusOverviewDesc")}</p>
          </div>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            <StatusTile
              label={t("watcher")}
              value={syncStatus?.watcher.running ? t("running") : t("idle")}
              detail={syncStatus?.watcher.media_dir ?? t("notConfigured")}
              active={syncStatus?.watcher.running}
              error={Boolean(syncStatus?.watcher.last_error)}
            />
            <StatusTile
              label={t("reconcile")}
              value={statusLabel(syncStatus?.sync.state)}
              detail={formatDate(syncStatus?.sync.last_finished_at)}
              active={syncStatus?.sync.state === "running"}
              error={Boolean(syncStatus?.sync.last_error)}
            />
            <StatusTile
              label={t("metadata")}
              value={statusLabel(scrapeStatus?.state)}
              detail={formatDate(scrapeStatus?.last_finished_at)}
              active={scrapeStatus?.state === "running"}
              error={Boolean(scrapeStatus?.last_error)}
            />
            <StatusTile
              label={t("scores")}
              value={statusLabel(externalScoresStatus?.state)}
              detail={formatDate(externalScoresStatus?.last_finished_at)}
              active={externalScoresStatus?.state === "running"}
              error={Boolean(externalScoresStatus?.last_error)}
            />
            <StatusTile
              label={t("organizer")}
              value={statusLabel(organizeStatus?.state)}
              detail={formatDate(organizeStatus?.last_finished_at)}
              active={organizeStatus?.state === "running"}
              error={Boolean(organizeStatus?.last_error)}
            />
          </div>
        </section>

        <section className="space-y-6">
          <div>
            <h2 className="text-2xl font-bold uppercase tracking-tight text-white">{t("scanGroup")}</h2>
            <p className="mt-1 text-xs leading-5 text-neutral-600">{t("scanGroupDesc")}</p>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <ActionCard
              title={settingsT("manualScan")}
              description={settingsT("manualScanDesc")}
              status={scanMessage}
              statusTone={scanError ? "error" : scanResult ? "success" : "neutral"}
            >
              <ActionButton busy={isScanning} onClick={() => void run(() => scanLibrary())}>
                {isScanning ? settingsT("scanning") : settingsT("scanNow")}
              </ActionButton>
            </ActionCard>
            <ActionCard
              title={settingsT("reconcileLibrary")}
              description={settingsT("reconcileLibraryDesc")}
              meta={
                syncStatus?.sync.last_finished_at
                  ? `${t("lastRun")}: ${formatDate(syncStatus.sync.last_finished_at)}`
                  : undefined
              }
              status={reconcileMessage}
              statusTone={reconcileError ? "error" : reconcileResult ? "success" : "neutral"}
            >
              <ActionButton busy={isReconciling} onClick={() => void run(() => reconcileLibrary())}>
                {isReconciling ? settingsT("scanning") : settingsT("reconcileNow")}
              </ActionButton>
            </ActionCard>
          </div>
        </section>

        <section className="space-y-6">
          <div>
            <h2 className="text-2xl font-bold uppercase tracking-tight text-white">{t("metadataGroup")}</h2>
            <p className="mt-1 text-xs leading-5 text-neutral-600">{t("metadataGroupDesc")}</p>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <ActionCard
              title={settingsT("scrapeMetadata")}
              description={settingsT("scrapeMetadataDesc")}
              meta={scrapeStatus?.last_error}
              status={!tmdbData?.configured ? settingsT("tmdbRequiredForScrape") : scrapeMessage}
              statusTone={scrapeError || !tmdbData?.configured ? "error" : scrapeResult ? "success" : "neutral"}
            >
              <ActionButton
                busy={isScraping || scrapeStatus?.state === "running"}
                disabled={!tmdbData?.configured}
                onClick={() => void run(() => scrapeLibrary())}
              >
                {isScraping || scrapeStatus?.state === "running"
                  ? settingsT("scraping")
                  : settingsT("scrapeNow")}
              </ActionButton>
            </ActionCard>
            <ActionCard
              title={settingsT("externalScores")}
              description={settingsT("externalScoresDesc")}
              meta={externalScoresStatus?.last_error}
              status={scoresMessage}
              statusTone={externalScoresError ? "error" : externalScoresResult ? "success" : "neutral"}
            >
              <ActionButton
                busy={isRefreshingScores || externalScoresStatus?.state === "running"}
                onClick={() => void run(() => refreshExternalScores())}
              >
                {isRefreshingScores || externalScoresStatus?.state === "running"
                  ? settingsT("externalScoresRefreshing")
                  : settingsT("externalScoresNow")}
              </ActionButton>
            </ActionCard>
          </div>
        </section>

        <section className="space-y-6">
          <div>
            <h2 className="text-2xl font-bold uppercase tracking-tight text-white">{t("organizationGroup")}</h2>
            <p className="mt-1 text-xs leading-5 text-neutral-600">{t("organizationGroupDesc")}</p>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <ActionCard
              title={settingsT("organizeRoot")}
              description={settingsT("organizeRootDesc")}
              meta={organizeStatus?.last_error}
              status={organizeMessage}
              statusTone={organizeError ? "error" : organizeResult ? "success" : "neutral"}
            >
              <ActionButton
                busy={isOrganizing || organizeStatus?.state === "running"}
                onClick={() => void run(() => organizeRootVideos())}
              >
                {isOrganizing || organizeStatus?.state === "running"
                  ? settingsT("organizing")
                  : settingsT("organizeNow")}
              </ActionButton>
            </ActionCard>
            <ActionCard title={t("librarianAgent")} description={t("librarianAgentDesc")}>
              <ActionButton onClick={() => setTerminalOpen(true)}>{t("openConsole")}</ActionButton>
            </ActionCard>
          </div>
        </section>

        <section className="space-y-6">
          <div>
            <h2 className="text-2xl font-bold uppercase tracking-tight text-red-300">{t("maintenanceGroup")}</h2>
            <p className="mt-1 text-xs leading-5 text-neutral-600">{t("maintenanceGroupDesc")}</p>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <ActionCard
              title={settingsT("cleanupMissing")}
              description={settingsT("cleanupMissingDesc")}
              status={cleanupMessage}
              statusTone={cleanupError ? "error" : cleanupResult ? "success" : "warning"}
              danger
            >
              <ActionButton danger busy={isCleaning} onClick={() => void run(() => cleanupMissing())}>
                {isCleaning ? settingsT("cleaning") : settingsT("cleanupNow")}
              </ActionButton>
            </ActionCard>
            <ActionCard
              title={settingsT("clearAllData")}
              description={settingsT("clearAllDataDesc")}
              status={clearMessage}
              statusTone={clearError ? "error" : clearResult ? "success" : "warning"}
              danger
            >
              <ActionButton danger busy={isClearing} onClick={handleClearLibraryData}>
                {isClearing ? settingsT("clearing") : settingsT("clearAllDataNow")}
              </ActionButton>
            </ActionCard>
          </div>
        </section>
        </section>
      </div>

      <LibrarianTerminal isOpen={terminalOpen} onClose={() => setTerminalOpen(false)} />
    </div>
  );
}
