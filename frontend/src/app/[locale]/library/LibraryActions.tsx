"use client";

import { Activity, Ellipsis, Fingerprint, RefreshCw, ScanSearch, Settings, Sparkles, Star } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useCallback, useEffect, useId, useRef, useState } from "react";
import useSWR from "swr";

import { IconButton } from "@/components/ui/Button";
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
import { API } from "@/lib/api";
import type { WorkflowAccepted } from "@/types/movie";
import type { IdentityReviewPage } from "@/types/identity-review";

type Feedback = { message: string; tone: "success" | "error" };

function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
}

export default function LibraryActions({ showScan = true }: { showScan?: boolean }) {
  const locale = useLocale();
  const t = useTranslations("LibraryCare");
  const reviewT = useTranslations("IdentityReview");
  const router = useRouter();
  const menuRef = useRef<HTMLDivElement>(null);
  const moreTrigger = useRef<HTMLButtonElement>(null);
  const menuId = useId();
  const reviewCountId = useId();
  const focusOnOpen = useRef<"first" | "last" | null>(null);
  const [open, setOpen] = useState(false);
  const reviews = useSWR<IdentityReviewPage>(open ? API.identityReviews(0) : null);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const sync = useLibrarySyncStatus();
  const tmdb = useTmdbSettings();
  const scan = useScanLibrary();
  const scrape = useScrapeLibrary();
  const scores = useRefreshLibraryExternalScores();
  const { upsertWorkflow, refreshWorkflows } = useWorkflowCache();
  const scanBusy = scan.isMutating || sync.data?.sync.state === "running";

  const focusItem = useCallback((position: "first" | "last") => {
    const items = menuRef.current?.querySelectorAll<HTMLElement>('[role="menu"] button:not(:disabled), [role="menu"] a[href]');
    (position === "last" ? items?.[items.length - 1] : items?.[0])?.focus();
  }, []);

  useEffect(() => {
    if (open && focusOnOpen.current) {
      focusItem(focusOnOpen.current);
      focusOnOpen.current = null;
    }
  }, [open, focusItem]);

  useEffect(() => {
    const close = (event: MouseEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape" && open) { setOpen(false); moreTrigger.current?.focus(); }
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", escape);
    };
  }, [open]);

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
    <div className="relative ml-auto flex flex-wrap items-center justify-end gap-1 sm:gap-3" ref={menuRef} onBlur={(event) => {
      if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false);
    }}>
      {showScan ? <IconButton
        variant="ghost"
        aria-label={scanBusy ? t("scanning") : t("scanNow")}
        busy={scanBusy}
        icon={<ScanSearch className="h-4 w-4" />}
        onClick={() => void run(() => scan.trigger(), t("scanStarted"))}
      /> : null}
      <IconButton
        ref={moreTrigger}
        variant="ghost"
        aria-label={t("more")}
        aria-expanded={open}
        aria-haspopup="menu"
        aria-controls={menuId}
        icon={<Ellipsis className="h-4 w-4" />}
        onClick={(event) => {
          if (!open && event.detail === 0) focusOnOpen.current = "first";
          setOpen((value) => !value);
        }}
        onKeyDown={(event) => {
          if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
          event.preventDefault();
          const position = event.key === "ArrowUp" ? "last" : "first";
          if (open) focusItem(position);
          else { focusOnOpen.current = position; setOpen(true); }
        }}
      />

      {open ? (
        <div
          id={menuId}
          role="menu"
          aria-label={t("more")}
          onKeyDown={(event) => {
            if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
            event.preventDefault();
            const items = Array.from(event.currentTarget.querySelectorAll<HTMLElement>('button:not(:disabled), a[href]'));
            const index = items.indexOf(document.activeElement as HTMLElement);
            const next = event.key === "Home" ? 0 : event.key === "End" ? items.length - 1
              : (index + (event.key === "ArrowUp" ? -1 : 1) + items.length) % items.length;
            items[next]?.focus();
          }}
          className="liquid-glass-popover z-popover absolute top-full right-0 mt-3 w-[min(20rem,calc(100vw-2rem))] border border-line/80 p-1 shadow-2xl"
        >
          {/* Keep this static destination out of the Film detail interception route. */}
          <a role="menuitem" href={`/${locale}/library/identity-review`} aria-label={t("identityReview")}
            aria-describedby={reviews.data ? reviewCountId : undefined} onClick={() => setOpen(false)}
            className="focus-ring flex min-h-11 items-center gap-3 px-3 text-xs text-ink-muted hover:bg-surface-raised hover:text-ink">
            <Fingerprint className="h-4 w-4" aria-hidden />
            <span className="flex-1">{t("identityReview")}</span>
            {reviews.data ? <><span aria-hidden="true" className="text-ink-subtle">{reviews.data.total}</span>
              <span id={reviewCountId} className="sr-only">{reviewT("count", { count: reviews.data.total })}</span></> : null}
          </a>
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
