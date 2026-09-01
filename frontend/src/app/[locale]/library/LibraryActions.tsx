"use client";

import { Activity, Ellipsis, RefreshCw, ScanSearch, Settings, Sparkles, Star } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/Button";
import { InlineFeedback } from "@/components/ui/Feedback";
import {
  useLibrarySyncStatus,
  useRefreshLibraryExternalScores,
  useScanLibrary,
  useScrapeLibrary,
  useTmdbSettings,
} from "@/hooks/useSettings";
import { useWorkflowCache } from "@/hooks/useWorkflows";
import { Link, useRouter } from "@/i18n/routing";
import type { WorkflowAccepted } from "@/types/movie";

type Feedback = { message: string; tone: "success" | "error" };

function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
}

export default function LibraryActions() {
  const t = useTranslations("LibraryCare");
  const router = useRouter();
  const menuRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const sync = useLibrarySyncStatus();
  const tmdb = useTmdbSettings();
  const scan = useScanLibrary();
  const scrape = useScrapeLibrary();
  const scores = useRefreshLibraryExternalScores();
  const { upsertWorkflow, refreshWorkflows } = useWorkflowCache();
  const scanBusy = scan.isMutating || sync.data?.sync.state === "running";

  useEffect(() => {
    const close = (event: MouseEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", escape);
    };
  }, []);

  const run = async (
    operation: () => Promise<unknown>,
    successMessage: string,
  ) => {
    setFeedback(null);
    setOpen(false);
    try {
      const result = await operation() as Partial<WorkflowAccepted> | undefined;
      if (result?.workflow?.id) upsertWorkflow(result.workflow);
      else refreshWorkflows();
      setFeedback({ message: successMessage, tone: "success" });
      router.refresh();
    } catch (error) {
      setFeedback({ message: errorMessage(error, t("operationFailed")), tone: "error" });
    }
  };

  return (
    <div className="relative flex flex-wrap items-center justify-end gap-3" ref={menuRef}>
      <Button
        variant="primary"
        busy={scanBusy}
        icon={<ScanSearch className="h-4 w-4" />}
        onClick={() => void run(() => scan.trigger(), t("scanStarted"))}
      >
        {scanBusy ? t("scanning") : t("scanNow")}
      </Button>
      <Button
        aria-expanded={open}
        aria-haspopup="menu"
        icon={<Ellipsis className="h-4 w-4" />}
        onClick={() => setOpen((value) => !value)}
      >
        {t("more")}
      </Button>

      {open ? (
        <div
          role="menu"
          className="liquid-glass-popover z-popover absolute top-full right-0 mt-3 w-[min(20rem,calc(100vw-2rem))] border border-line/80 p-1 shadow-2xl"
        >
          <button
            role="menuitem"
            type="button"
            disabled={!tmdb.data?.configured || scrape.isMutating}
            onClick={() => void run(() => scrape.trigger(), t("scrapeStarted"))}
            className="focus-ring flex min-h-11 w-full items-center gap-3 px-3 text-left text-xs text-ink-muted hover:bg-surface-raised hover:text-ink disabled:cursor-not-allowed disabled:opacity-45"
          >
            {scrape.isMutating ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
            {t("scrapeMetadata")}
          </button>
          {!tmdb.isLoading && !tmdb.data?.configured ? (
            <Link
              href="/settings?section=integrations"
              onClick={() => setOpen(false)}
              className="focus-ring mx-3 mb-2 block border-l border-warning/50 pl-3 text-[11px] leading-5 text-warning hover:text-ink"
            >
              {t("configureTmdb")}
            </Link>
          ) : null}
          <button
            role="menuitem"
            type="button"
            disabled={scores.isMutating}
            onClick={() => void run(() => scores.trigger(), t("scoresStarted"))}
            className="focus-ring flex min-h-11 w-full items-center gap-3 px-3 text-left text-xs text-ink-muted hover:bg-surface-raised hover:text-ink disabled:cursor-not-allowed disabled:opacity-45"
          >
            {scores.isMutating ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Star className="h-4 w-4" />}
            {t("refreshScores")}
          </button>
          <Link role="menuitem" href="/library/activity" onClick={() => setOpen(false)} className="focus-ring flex min-h-11 items-center gap-3 px-3 text-xs text-ink-muted hover:bg-surface-raised hover:text-ink">
            <Activity className="h-4 w-4" />{t("activity")}
          </Link>
          <Link role="menuitem" href="/settings?section=library" onClick={() => setOpen(false)} className="focus-ring flex min-h-11 items-center gap-3 px-3 text-xs text-ink-muted hover:bg-surface-raised hover:text-ink">
            <Settings className="h-4 w-4" />{t("librarySettings")}
          </Link>
        </div>
      ) : null}

      <div aria-live="polite" aria-atomic="true" className="absolute top-full right-0 mt-3 min-h-5 w-[min(22rem,calc(100vw-2rem))] text-right">
        {feedback ? <InlineFeedback tone={feedback.tone}>{feedback.message}</InlineFeedback> : null}
      </div>
    </div>
  );
}
