"use client";

import { useRef, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { Button } from "@/components/ui/Button";
import { InlineFeedback } from "@/components/ui/Feedback";
import MediaScanResults from "@/components/settings/MediaScanResults";
import MaintenanceWorkflows from "@/components/settings/MaintenanceWorkflows";
import { useSettingsSession } from "@/components/settings/SettingsSession";
import { useLibraryExternalScoresStatus, useLibraryOrganizeStatus, useLibraryScrapeStatus, useRefreshLibraryExternalScores, useScrapeLibrary, useTmdbSettings } from "@/hooks/useSettings";
import { useWorkflowCache, useWorkflows } from "@/hooks/useWorkflows";
import { Link } from "@/i18n/routing";
import { settingsHref } from "@/lib/settings-navigation";
import type { WorkflowAccepted } from "@/types/movie";
import LibraryOfflineCare from "../library/LibraryOfflineCare";

export default function LibraryMaintenanceSettings() {
  const area = useTranslations("SettingsArea"), t = useTranslations("LibraryManagement.constellation");
  const locale = useLocale();
  const metadata = useLibraryScrapeStatus(), scores = useLibraryExternalScoresStatus(), organizer = useLibraryOrganizeStatus(), tmdb = useTmdbSettings();
  const scrape = useScrapeLibrary(), refreshScores = useRefreshLibraryExternalScores();
  const workflows = useWorkflows();
  const { upsertWorkflow, refreshWorkflows } = useWorkflowCache();
  const { rootsDraft, rootsSaving } = useSettingsSession();
  const [notice, setNotice] = useState<{ text: string; failed: boolean } | null>(null);
  const locks = useRef(new Set<string>());
  const scanBlocked = rootsDraft !== null || rootsSaving;
  const running = (prefix: string) => workflows.data?.some(workflow => workflow.type.startsWith(prefix) && ["queued", "running"].includes(workflow.status));
  async function run(kind: "metadata" | "scores") {
    if (locks.current.has(kind)) return;
    locks.current.add(kind); setNotice(null);
    try {
      const result = await (kind === "metadata" ? scrape.trigger() : refreshScores.trigger()) as Partial<WorkflowAccepted>;
      if (result.workflow?.id) upsertWorkflow(result.workflow); else refreshWorkflows();
      setNotice({ text: t(kind === "metadata" ? "feedback.scrape" : "feedback.scores"), failed: false });
    } catch (failure) { setNotice({ text: failure instanceof Error ? failure.message : t("operationFailed"), failed: true }); }
    finally { locks.current.delete(kind); }
  }
  const lastRun = (value?: string | null) => t("lastRunAt", { value: value ? new Date(value).toLocaleString(locale) : t("never") });
  return <div className="space-y-8">
    <section id="scan" className="scroll-mt-28 space-y-3">
      {scanBlocked ? <InlineFeedback tone="warning">{area("pendingDirectories")} <Link href={settingsHref("library", "media-directories")} className="focus-ring underline underline-offset-4">{area("openDirectories")}</Link></InlineFeedback> : null}
      <MediaScanResults disabled={scanBlocked} />
    </section>
    <section id="metadata" className="scroll-mt-28 space-y-4 border-b border-line pb-6">
      <h3 className="type-label text-ink-muted">{area("metadata")}</h3>
      <div className="flex flex-wrap gap-3"><Button className="max-w-full" busy={scrape.isMutating} disabled={!metadata.data || Boolean(metadata.error) || !tmdb.data?.configured || metadata.data.state === "running" || Boolean(running("metadata."))} onClick={() => void run("metadata")}>{t("actions.scrape-metadata.label")}</Button><Link href="/library?view=metadata" className="focus-ring inline-flex min-h-11 items-center text-sm underline underline-offset-4">{t("actions.review-metadata.label")}</Link></div>
      {!tmdb.data?.configured ? <InlineFeedback tone="warning">{t("tmdbNotConfigured")} <Link href={settingsHref("connections")} className="focus-ring underline">{area("connections")}</Link></InlineFeedback> : null}
      <p className="text-xs text-ink-subtle">{metadata.data ? lastRun(metadata.data.last_finished_at) : area("loading")}</p>
      {metadata.error || metadata.data?.last_error ? <InlineFeedback tone="error">{metadata.data?.last_error || t("loadFailed")}</InlineFeedback> : null}
    </section>
    <section id="scores" className="scroll-mt-28 space-y-4 border-b border-line pb-6">
      <h3 className="type-label text-ink-muted">{area("externalScores")}</h3>
      <Button className="max-w-full" busy={refreshScores.isMutating} disabled={!scores.data || Boolean(scores.error) || scores.data.state === "running" || Boolean(running("external_scores."))} onClick={() => void run("scores")}>{t("actions.refresh-scores.label")}</Button>
      <p className="text-xs text-ink-subtle">{scores.data ? lastRun(scores.data.last_finished_at) : area("loading")}</p>
      {scores.error || scores.data?.last_error ? <InlineFeedback tone="error">{scores.data?.last_error || t("loadFailed")}</InlineFeedback> : null}
    </section>
    <section id="root-files" className="scroll-mt-28 space-y-3 border-b border-line pb-6"><h3 className="type-label text-ink-muted">{area("rootFiles")}</h3><Link href="/library?view=inbox" className="focus-ring inline-flex min-h-11 items-center text-sm underline underline-offset-4">{t("actions.organize-files.label")}</Link>{organizer.error || organizer.data?.last_error ? <InlineFeedback tone="error">{organizer.data?.last_error || t("loadFailed")}</InlineFeedback> : null}</section>
    <section id="missing-files" className="scroll-mt-28"><LibraryOfflineCare embedded scanDisabled={scanBlocked} filmsHref="/library" /></section>
    <div role={notice?.failed ? "alert" : "status"} aria-live="polite">{notice ? <InlineFeedback tone={notice.failed ? "error" : "success"}>{notice.text}</InlineFeedback> : null}</div>
    <MaintenanceWorkflows />
  </div>;
}
