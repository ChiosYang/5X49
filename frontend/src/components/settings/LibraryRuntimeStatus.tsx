"use client";

import { useLocale, useTranslations } from "next-intl";
import { Button } from "@/components/ui/Button";
import { InlineFeedback } from "@/components/ui/Feedback";
import { useLibraryExternalScoresStatus, useLibraryOrganizeStatus, useLibraryScrapeStatus, useLibrarySyncStatus } from "@/hooks/useSettings";

export default function LibraryRuntimeStatus() {
  const t = useTranslations("LibraryManagement.constellation");
  const area = useTranslations("SettingsArea");
  const locale = useLocale();
  const sync = useLibrarySyncStatus(), metadata = useLibraryScrapeStatus();
  const scores = useLibraryExternalScoresStatus(), organizer = useLibraryOrganizeStatus();
  const rows = [
    { id: "watcher", loaded: Boolean(sync.data), error: sync.error || sync.data?.watcher.last_error, state: sync.data?.watcher.running ? "running" : "idle", finished: null },
    { id: "sync", loaded: Boolean(sync.data), error: sync.error || sync.data?.sync.last_error, state: sync.data?.sync.state, finished: sync.data?.sync.last_finished_at },
    { id: "metadata", loaded: Boolean(metadata.data), error: metadata.error || metadata.data?.last_error, state: metadata.data?.state, finished: metadata.data?.last_finished_at },
    { id: "scores", loaded: Boolean(scores.data), error: scores.error || scores.data?.last_error, state: scores.data?.state, finished: scores.data?.last_finished_at },
    { id: "organizer", loaded: Boolean(organizer.data), error: organizer.error || organizer.data?.last_error, state: organizer.data?.state, finished: organizer.data?.last_finished_at },
  ];
  const label = (state?: string) => state === "running" ? t("states.running") : ["error", "failed", "interrupted"].includes(state ?? "") ? t("states.failed") : ["completed", "succeeded", "success"].includes(state ?? "") ? t("states.healthy") : state === "idle" ? t("states.idle") : state || area("loading");
  return <section id="runtime" className="scroll-mt-28 space-y-4">
    <div className="flex flex-wrap items-center justify-between gap-3"><h3 className="type-label text-ink-muted">{area("runtime")}</h3><Button size="sm" disabled={sync.isValidating || metadata.isValidating || scores.isValidating || organizer.isValidating} onClick={() => void Promise.allSettled([sync.mutate(), metadata.mutate(), scores.mutate(), organizer.mutate()])}>{area("refresh")}</Button></div>
    <dl className="divide-y divide-line border-y border-line">{rows.map(row => <div key={row.id} className="space-y-2 py-4">
      <div className="flex flex-wrap justify-between gap-3 text-sm"><dt>{t(`nodes.${row.id}`)}</dt><dd className={row.error ? "text-danger" : "text-ink-muted"}>{row.error ? t("states.failed") : row.loaded ? label(row.state) : area("loading")}</dd></div>
      {row.error ? <InlineFeedback tone="error">{typeof row.error === "string" ? row.error : t("loadFailed")}</InlineFeedback> : row.id !== "watcher" && row.loaded ? <p className="text-xs text-ink-subtle">{t("lastRunAt", { value: row.finished ? new Date(row.finished).toLocaleString(locale) : t("never") })}</p> : null}
    </div>)}</dl>
  </section>;
}
