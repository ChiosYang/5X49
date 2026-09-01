"use client";

import { AlertTriangle, CheckCircle2, Search, Trash2 } from "lucide-react";
import { useReducedMotion } from "framer-motion";
import { useLocale, useTranslations } from "next-intl";
import { useMemo, useState } from "react";
import useSWR from "swr";

import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { InlineFeedback, StateMessage } from "@/components/ui/Feedback";
import { useLibrary } from "@/hooks/useLibrary";
import { useCleanupMissingMovies, useScanLibrary } from "@/hooks/useSettings";
import { useWorkflowCache } from "@/hooks/useWorkflows";
import { Link, useRouter } from "@/i18n/routing";
import { API } from "@/lib/api";
import type { MissingLibraryItemsResponse, WorkflowAccepted } from "@/types/movie";

export default function LibraryOfflineCare({ initialData }: { initialData: MissingLibraryItemsResponse }) {
  const t = useTranslations("LibraryCare");
  const locale = useLocale();
  const router = useRouter();
  const reducedMotion = useReducedMotion();
  const library = useLibrary();
  const missing = useSWR<MissingLibraryItemsResponse>(API.libraryCleanupMissing(), { fallbackData: initialData });
  const cleanup = useCleanupMissingMovies();
  const scan = useScanLibrary();
  const { upsertWorkflow, refreshWorkflows } = useWorkflowCache();
  const [query, setQuery] = useState("");
  const [visibleCount, setVisibleCount] = useState(50);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [completed, setCompleted] = useState(false);
  const [feedback, setFeedback] = useState<{ message: string; tone: "success" | "error" } | null>(null);

  const items = useMemo(() => missing.data?.items ?? [], [missing.data?.items]);
  const filtered = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase(locale);
    if (!normalized) return items;
    return items.filter((item) => (
      `${item.title} ${item.display_name ?? ""} ${item.year ?? ""}`
        .toLocaleLowerCase(locale)
        .includes(normalized)
    ));
  }, [items, locale, query]);

  const startScan = async () => {
    setFeedback(null);
    try {
      const result = await scan.trigger() as Partial<WorkflowAccepted>;
      if (result.workflow?.id) upsertWorkflow(result.workflow);
      else refreshWorkflows();
      setFeedback({ message: t("scanStarted"), tone: "success" });
      router.refresh();
    } catch (error) {
      setFeedback({ message: error instanceof Error ? error.message : t("operationFailed"), tone: "error" });
    }
  };

  const confirmCleanup = async () => {
    setFeedback(null);
    try {
      await cleanup.trigger();
      setConfirmOpen(false);
      setCompleted(true);
      await Promise.all([missing.mutate(), library.mutate()]);
      setFeedback({ message: t("offlineCleaned"), tone: "success" });
      router.refresh();
    } catch (error) {
      setFeedback({ message: error instanceof Error ? error.message : t("offlineCleanupFailed"), tone: "error" });
    }
  };

  if (missing.isLoading && !missing.data) {
    return <StateMessage state="loading">{t("offlineLoading")}</StateMessage>;
  }

  if (missing.error && !missing.data) {
    return <StateMessage state="error">{t("offlineLoadFailed")}</StateMessage>;
  }

  if (items.length === 0) {
    return (
      <div className="border-y border-line py-16 text-center">
        <CheckCircle2 className="mx-auto h-8 w-8 text-success" />
        <h2 className="mt-5 type-section-title text-ink">{completed ? t("offlineComplete") : t("offlineEmpty")}</h2>
        <p className="mx-auto mt-3 max-w-xl text-sm leading-6 text-ink-subtle">{t("offlineEmptyDesc")}</p>
        <Link href="/library" className="focus-ring mt-7 inline-flex min-h-10 items-center border border-line-strong px-4 type-label text-ink-muted hover:border-ink-disabled hover:text-ink">
          {t("backToFilms")}
        </Link>
      </div>
    );
  }

  return (
    <section className="min-w-0">
      <div className="flex flex-col gap-5 border-b border-line pb-6 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h2 className="type-section-title text-ink">{t("offlineTitle")}</h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-ink-subtle">{t("offlineDesc")}</p>
        </div>
        <div className="flex flex-col gap-3 sm:flex-row">
          <Button busy={scan.isMutating} onClick={() => void startScan()}>{t("scanAgain")}</Button>
          <Button variant="danger" icon={<Trash2 className="h-4 w-4" />} onClick={() => setConfirmOpen(true)}>
            {t("cleanAllOffline", { count: items.length })}
          </Button>
        </div>
      </div>

      <div className="mt-5 min-h-5" aria-live="polite">
        {missing.error ? <InlineFeedback tone="error">{t("offlineRefreshFailed")}</InlineFeedback> : null}
        {feedback ? <InlineFeedback tone={feedback.tone}>{feedback.message}</InlineFeedback> : null}
      </div>

      <label className="mt-5 flex min-h-11 max-w-lg items-center gap-3 border border-line-strong bg-surface/50 px-3">
        <Search className="h-4 w-4 text-ink-disabled" />
        <span className="sr-only">{t("searchOffline")}</span>
        <input
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setVisibleCount(50);
          }}
          placeholder={t("searchOffline")}
          className="min-w-0 flex-1 bg-transparent text-sm text-ink outline-none placeholder:text-ink-disabled"
        />
      </label>

      {filtered.length === 0 ? <StateMessage className="mt-8">{t("noOfflineMatches")}</StateMessage> : (
        <ul className="mt-8 divide-y divide-line border-y border-line">
          {filtered.slice(0, visibleCount).map((item) => (
            <li key={item.library_item_id} className="grid gap-2 py-5 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center sm:gap-6">
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-ink">{item.title}{item.year ? ` (${item.year})` : ""}</p>
                <p className="mt-1 truncate text-xs text-ink-subtle">{item.display_name || t("unknownEdition")}</p>
              </div>
              <p className="text-xs text-ink-disabled">
                {item.missing_since ? new Date(item.missing_since).toLocaleString(locale) : t("unknownTime")}
              </p>
            </li>
          ))}
        </ul>
      )}
      {visibleCount < filtered.length ? (
        <Button className="mt-5" variant="ghost" onClick={() => setVisibleCount((value) => value + 50)}>
          {t("showMore", { count: Math.min(50, filtered.length - visibleCount) })}
        </Button>
      ) : null}

      <Dialog
        animated={!reducedMotion}
        open={confirmOpen}
        onClose={() => { if (!cleanup.isMutating) setConfirmOpen(false); }}
        closeLabel={t("closeDialog")}
        ariaLabelledBy="offline-cleanup-title"
        size="sm"
        placement="bottom"
      >
        <div className="p-6 sm:p-8">
          <span className="flex h-11 w-11 items-center justify-center rounded-full border border-danger/30 bg-danger/10 text-danger"><AlertTriangle className="h-4 w-4" /></span>
          <h3 id="offline-cleanup-title" className="mt-5 type-section-title text-ink">{t("offlineConfirmTitle")}</h3>
          <p className="mt-3 text-sm leading-6 text-ink-subtle">{t("offlineConfirmImpact", { count: items.length })}</p>
          <div className="mt-7 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
            <Button disabled={cleanup.isMutating} onClick={() => setConfirmOpen(false)}>{t("cancel")}</Button>
            <Button variant="danger" busy={cleanup.isMutating} onClick={() => void confirmCleanup()}>{t("confirmOfflineCleanup")}</Button>
          </div>
        </div>
      </Dialog>
    </section>
  );
}
