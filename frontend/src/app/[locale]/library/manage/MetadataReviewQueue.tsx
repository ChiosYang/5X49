"use client";

import { CheckCircle2, ChevronRight, RotateCcw } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useEffect, useMemo, useState } from "react";

import {
  MetadataCandidatePicker,
  parseMetadataSearchInput,
  parseTmdbId,
  prependMetadataCandidate,
} from "@/components/metadata/MetadataCandidatePicker";
import { Button } from "@/components/ui/Button";
import { InlineFeedback, StateMessage } from "@/components/ui/Feedback";
import {
  useConfirmScrapeFilm,
  useFilmScrapeCandidates,
} from "@/hooks/useFilm";
import { useLibrary } from "@/hooks/useLibrary";
import { API } from "@/lib/api";
import type { LibraryFilmSummary, MetadataSearchResult } from "@/types/movie";

function filmsNeedingReview(films: LibraryFilmSummary[], locale: string) {
  return films
    .filter((film) => film.primary_item.metadata.scrape_status === "needs_review")
    .sort((left, right) => (
      left.title.localeCompare(right.title, locale)
      || (left.year ?? 0) - (right.year ?? 0)
      || left.id.localeCompare(right.id)
    ));
}

export function MetadataReviewInspector({
  film,
  onConfirmed,
}: {
  film: LibraryFilmSummary;
  onConfirmed: (filmId: string) => Promise<void>;
}) {
  const t = useTranslations("LibraryManagement");
  const filmT = useTranslations("FilmDetail");
  const candidateQuery = useFilmScrapeCandidates(film.id);
  const confirmScrape = useConfirmScrapeFilm(film.id);
  const [candidateOverride, setCandidateOverride] = useState<MetadataSearchResult[] | null>(null);
  const [reviewSearchDraft, setReviewSearchDraft] = useState(
    `${film.title}${film.year ? ` ${film.year}` : ""}`,
  );
  const [lookupBusy, setLookupBusy] = useState(false);
  const [busyCandidateId, setBusyCandidateId] = useState<number | null>(null);
  const [feedback, setFeedback] = useState<{ message: string; tone: "error" | "success" } | null>(null);
  const candidates = candidateOverride ?? candidateQuery.data ?? [];
  const busy = lookupBusy || confirmScrape.isMutating;
  const automaticCandidatesLoading = candidateOverride === null && candidateQuery.isLoading;
  const automaticCandidatesError = candidateOverride === null && candidateQuery.error;

  const handleLookup = async () => {
    const input = reviewSearchDraft.trim();
    if (!input) return;
    setLookupBusy(true);
    setFeedback(null);
    try {
      const tmdbId = parseTmdbId(input);
      if (tmdbId) {
        const response = await fetch(API.metadataMovie(tmdbId));
        if (!response.ok) throw new Error(filmT("metadataLookupFailed"));
        const candidate = await response.json() as MetadataSearchResult;
        setCandidateOverride((current) => prependMetadataCandidate(current ?? candidates, candidate));
      } else {
        const parsed = parseMetadataSearchInput(input);
        const query = new URLSearchParams({ query: parsed.query });
        if (parsed.year) query.set("year", String(parsed.year));
        const response = await fetch(`${API.metadataSearch()}?${query}`);
        if (!response.ok) throw new Error(filmT("metadataLookupFailed"));
        setCandidateOverride(await response.json() as MetadataSearchResult[]);
      }
    } catch (error) {
      setFeedback({
        message: error instanceof Error ? error.message : filmT("metadataLookupFailed"),
        tone: "error",
      });
    } finally {
      setLookupBusy(false);
    }
  };

  const handleConfirm = async (candidate: MetadataSearchResult) => {
    setBusyCandidateId(candidate.tmdb_id);
    setFeedback(null);
    try {
      await confirmScrape.trigger(candidate.tmdb_id);
      await onConfirmed(film.id);
    } catch (error) {
      setFeedback({
        message: error instanceof Error ? error.message : t("reviewConfirmFailed"),
        tone: "error",
      });
    } finally {
      setBusyCandidateId(null);
    }
  };

  return (
    <div className="border-t border-line pt-5">
      <div className="mb-5 flex min-w-0 flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <p className="break-words text-base font-semibold text-ink">
            {film.title}{film.year ? ` (${film.year})` : ""}
          </p>
          {film.original_title && film.original_title !== film.title ? (
            <p className="mt-1 break-words text-xs text-ink-subtle">{film.original_title}</p>
          ) : null}
        </div>
        <span className="type-badge shrink-0 text-warning">{t("needsReview")}</span>
      </div>

      {automaticCandidatesLoading ? (
        <StateMessage state="loading">{t("candidateLoading")}</StateMessage>
      ) : null}
      {automaticCandidatesError ? (
        <StateMessage state="error" className="flex-col">
          <span>{t("candidateLoadFailed")}</span>
          <Button
            size="sm"
            icon={<RotateCcw className="h-3.5 w-3.5" />}
            onClick={() => void candidateQuery.mutate()}
          >
            {t("retryCandidates")}
          </Button>
        </StateMessage>
      ) : null}
      {!automaticCandidatesLoading && !automaticCandidatesError && candidates.length === 0 ? (
        <StateMessage>{t("noCandidates")}</StateMessage>
      ) : null}

      <div className="mt-4">
        <MetadataCandidatePicker
          busyCandidateId={busyCandidateId}
          candidates={candidates}
          disabled={busy}
          inputValue={reviewSearchDraft}
          lookupBusy={lookupBusy}
          lookupLabel={filmT("lookup")}
          onInputChange={setReviewSearchDraft}
          onLookup={handleLookup}
          onSelect={(candidate) => void handleConfirm(candidate)}
          placeholder={filmT("metadataSearchPlaceholder")}
          selectionBusy={confirmScrape.isMutating}
          showCandidates={!automaticCandidatesLoading && candidates.length > 0}
          showFewerLabel={filmT("showFewer")}
          showMoreLabel={(count) => filmT("showMore", { count })}
        />
      </div>
      <div className="mt-3 min-h-5" aria-live="polite">
        {feedback ? <InlineFeedback tone={feedback.tone}>{feedback.message}</InlineFeedback> : null}
      </div>
    </div>
  );
}

export default function MetadataReviewQueue({ refreshSignal }: { refreshSignal?: string | null }) {
  const t = useTranslations("LibraryManagement");
  const locale = useLocale();
  const { data, error, isLoading, mutate } = useLibrary();
  const [activeFilmId, setActiveFilmId] = useState<string | null>(null);
  const [completed, setCompleted] = useState(false);
  const [confirmedSinceStart, setConfirmedSinceStart] = useState(false);
  const [sessionTotal, setSessionTotal] = useState(0);
  const [sessionConfirmedCount, setSessionConfirmedCount] = useState(0);

  const allReviewFilms = useMemo(
    () => filmsNeedingReview(data ?? [], locale),
    [data, locale],
  );
  const activeFilm = allReviewFilms.find((film) => film.id === activeFilmId) ?? null;

  useEffect(() => {
    if (refreshSignal) void mutate();
  }, [refreshSignal, mutate]);

  const startReview = () => {
    setCompleted(false);
    setConfirmedSinceStart(false);
    setSessionTotal(allReviewFilms.length);
    setSessionConfirmedCount(0);
    setActiveFilmId(allReviewFilms[0]?.id ?? null);
  };

  const handleConfirmed = async (filmId: string) => {
    const currentRemaining = allReviewFilms.filter((film) => film.id !== filmId);
    const refreshed = await mutate().catch(() => undefined);
    const remaining = refreshed
      ? filmsNeedingReview(refreshed, locale).filter((film) => film.id !== filmId)
      : currentRemaining;
    setConfirmedSinceStart(true);
    setSessionConfirmedCount((current) => current + 1);
    setActiveFilmId(remaining[0]?.id ?? null);
    setCompleted(remaining.length === 0);
  };

  return (
    <article
      id="metadata-reviews"
      className="scroll-mt-32 border-y border-line py-6 md:col-span-2"
    >
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-3">
            <h3 className="text-sm font-medium tracking-widest text-ink uppercase">
              {t("reviewQueueTitle")}
            </h3>
            <span className="type-badge border border-line-strong px-2 py-1 text-ink-muted">
              {t("reviewQueueCount", { count: allReviewFilms.length })}
            </span>
          </div>
          <p className="mt-2 max-w-2xl text-xs leading-5 text-ink-disabled">
            {t("reviewQueueDesc")}
          </p>
        </div>
        {!activeFilm && allReviewFilms.length > 0 ? (
          <Button
            responsiveWidth
            icon={<ChevronRight className="h-3.5 w-3.5" />}
            onClick={startReview}
          >
            {t("startReview")}
          </Button>
        ) : null}
      </div>

      <div className="mt-5 min-h-5" aria-live="polite">
        {error ? <InlineFeedback tone="error">{t("reviewQueueLoadFailed")}</InlineFeedback> : null}
        {completed && allReviewFilms.length === 0 ? (
          <InlineFeedback tone="success">
            <span className="inline-flex items-center gap-2">
              <CheckCircle2 className="h-3.5 w-3.5" />
              {t("allReviewsComplete")}
            </span>
          </InlineFeedback>
        ) : null}
        {!isLoading && !error && !completed && allReviewFilms.length === 0 ? (
          <InlineFeedback>{t("noPendingReviews")}</InlineFeedback>
        ) : null}
        {activeFilm ? (
          <InlineFeedback tone={confirmedSinceStart ? "success" : "neutral"}>
            {confirmedSinceStart ? `${t("reviewConfirmed")} ` : ""}
            {t("reviewProgress", {
              current: Math.min(sessionConfirmedCount + 1, sessionTotal),
              total: sessionTotal,
            })}
          </InlineFeedback>
        ) : null}
      </div>

      {activeFilm ? (
        <MetadataReviewInspector
          key={activeFilm.id}
          film={activeFilm}
          onConfirmed={handleConfirmed}
        />
      ) : null}
    </article>
  );
}
