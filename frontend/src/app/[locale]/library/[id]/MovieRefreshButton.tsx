"use client";

import { Award, Check, Clapperboard, EyeOff, RefreshCw, Star } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { mutate } from "swr";

import {
  MetadataCandidatePicker,
  parseMetadataSearchInput,
  parseTmdbId,
  prependMetadataCandidate,
} from "@/components/metadata/MetadataCandidatePicker";
import { IconButton } from "@/components/ui/Button";
import { InlineFeedback } from "@/components/ui/Feedback";
import {
  useConfirmScrapeFilm,
  invalidateViewingCaches,
  useIgnoreLibraryItem,
  useRefreshFilmExternalScores,
  useRefreshLibraryItem,
  useScrapeFilm,
  useUpdateFilmProfileState,
} from "@/hooks/useFilm";
import { API } from "@/lib/api";
import { useRouter } from "@/i18n/routing";
import type { LibraryFilmDetail, MetadataSearchResult } from "@/types/movie";
import MovieArtworkPicker from "./MovieArtworkPicker";

function todayDateValue() {
  return new Date().toISOString().slice(0, 10);
}

export default function MovieRefreshButton({ film }: { film: LibraryFilmDetail }) {
  const t = useTranslations("FilmDetail");
  const router = useRouter();
  const filmId = film.id;
  const itemId = film.primary_item.id;
  const [state, setState] = useState(film.profile_state);
  const [candidates, setCandidates] = useState<MetadataSearchResult[]>([]);
  const [message, setMessage] = useState("");
  const [reviewOpen, setReviewOpen] = useState(false);
  const [reviewSearchDraft, setReviewSearchDraft] = useState("");
  const [isSearching, setIsSearching] = useState(false);

  const profile = useUpdateFilmProfileState(filmId);
  const refresh = useRefreshLibraryItem(itemId);
  const scores = useRefreshFilmExternalScores(filmId);
  const scrape = useScrapeFilm(filmId);
  const confirmScrape = useConfirmScrapeFilm(filmId);
  const ignore = useIgnoreLibraryItem(itemId);
  const busy = profile.isMutating || refresh.isMutating || scores.isMutating || scrape.isMutating || confirmScrape.isMutating || ignore.isMutating || isSearching;
  const anyError = profile.error || refresh.error || scores.error || scrape.error || confirmScrape.error || ignore.error;

  const refreshViews = async () => {
    await Promise.all([
      invalidateViewingCaches(filmId),
      mutate(API.libraryFilm(filmId)),
      mutate(API.libraryFilms()),
      mutate(API.filmProfileState(filmId)),
      mutate(API.watchHistory()),
    ]);
    router.refresh();
  };

  const updateProfile = async (updates: { watched?: boolean; favorite?: boolean; watched_at?: string | null }) => {
    const saved = await profile.trigger(updates);
    setState(saved);
    setMessage(t("saved"));
    await refreshViews();
  };

  const handleWatched = async () => {
    if (state.watched && !state.manual_watched) {
      router.push(`/diary?film=${filmId}`);
      return;
    }
    await updateProfile({
      watched: !state.manual_watched,
      watched_at: !state.manual_watched ? state.watched_at || todayDateValue() : null,
    });
  };

  const handleScrape = async () => {
    setMessage("");
    const result = await scrape.trigger();
    if (result.status === "needs_review") {
      setCandidates(result.candidates);
      setReviewOpen(true);
    } else {
      setReviewOpen(false);
      await refreshViews();
    }
    setMessage(result.message);
  };

  const handleConfirm = async (tmdbId: number) => {
    const result = await confirmScrape.trigger(tmdbId);
    setCandidates([]);
    setReviewOpen(false);
    setMessage(result.message);
    await refreshViews();
  };

  const handleReviewLookup = async () => {
    const input = reviewSearchDraft.trim();
    if (!input) return;
    setIsSearching(true);
    try {
      const tmdbId = parseTmdbId(input);
      if (tmdbId) {
        const response = await fetch(API.metadataMovie(tmdbId));
        if (!response.ok) throw new Error(t("metadataLookupFailed"));
        const candidate = await response.json() as MetadataSearchResult;
        setCandidates((current) => prependMetadataCandidate(current, candidate));
      } else {
        const parsed = parseMetadataSearchInput(input);
        const query = new URLSearchParams({ query: parsed.query });
        if (parsed.year) query.set("year", String(parsed.year));
        const response = await fetch(`${API.metadataSearch()}?${query}`);
        if (!response.ok) throw new Error(t("metadataLookupFailed"));
        setCandidates(await response.json());
      }
      setReviewOpen(true);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : t("metadataLookupFailed"));
    } finally {
      setIsSearching(false);
    }
  };

  return (
    <div className="relative flex min-w-0 flex-col items-start justify-between gap-4 p-8 md:px-16 2xl:flex-row 2xl:items-center">
      <div className="space-y-2">
        <span className="type-label block text-ink-subtle">{t("filmControls")}</span>
        {message && <InlineFeedback>{message}</InlineFeedback>}
        {anyError && <InlineFeedback tone="error">{t("actionFailed")}</InlineFeedback>}
      </div>
      <div className="flex max-w-full flex-wrap items-center gap-2 sm:shrink-0">
        <IconButton
          onClick={handleWatched}
          disabled={busy}
          busy={profile.isMutating}
          variant={state.watched ? "primary" : "secondary"}
          aria-label={state.watched && !state.manual_watched ? t("viewDiary") : state.manual_watched ? t("markUnwatched") : t("markWatched")}
          title={state.watched && !state.manual_watched ? t("viewDiary") : state.manual_watched ? t("markUnwatched") : t("markWatched")}
          icon={<Check className="h-4 w-4" />}
        />
        <IconButton
          onClick={() => updateProfile({ favorite: !state.favorite })}
          disabled={busy}
          busy={profile.isMutating}
          variant={state.favorite ? "primary" : "secondary"}
          aria-label={state.favorite ? t("removeFavorite") : t("favorite")}
          title={state.favorite ? t("removeFavorite") : t("favorite")}
          icon={<Star className={`h-4 w-4 ${state.favorite ? "fill-current" : ""}`} />}
        />
        <MovieArtworkPicker movieId={filmId} />
        <IconButton
          onClick={async () => { const result = await scores.trigger(); setMessage(result.message); }}
          disabled={busy}
          busy={scores.isMutating}
          aria-label={t("refreshExternalScores")}
          title={t("refreshExternalScores")}
          icon={<Award className="h-4 w-4" />}
        />
        <div className="relative">
          <IconButton
            onClick={() => reviewOpen ? setReviewOpen(false) : void handleScrape()}
            disabled={busy}
            busy={scrape.isMutating || confirmScrape.isMutating}
            aria-label={t("scrapeMetadata")}
            title={t("scrapeMetadata")}
            icon={<Clapperboard className="h-4 w-4" />}
          />
          {reviewOpen && (
            <div className="z-popover absolute top-full right-0 w-[min(24rem,calc(100vw-4rem))] pt-3">
              <div className="liquid-glass-popover border border-line/80 p-4">
                <MetadataCandidatePicker
                  candidates={candidates}
                  inputValue={reviewSearchDraft}
                  onInputChange={setReviewSearchDraft}
                  onLookup={handleReviewLookup}
                  onSelect={(candidate) => handleConfirm(candidate.tmdb_id)}
                  lookupBusy={isSearching}
                  selectionBusy={confirmScrape.isMutating}
                  disabled={busy}
                  lookupLabel={t("lookup")}
                  placeholder={t("metadataSearchPlaceholder")}
                  showFewerLabel={t("showFewer")}
                  showMoreLabel={(count) => t("showMore", { count })}
                />
              </div>
            </div>
          )}
        </div>
        <IconButton
          onClick={async () => { await ignore.trigger(); setMessage(t("editionIgnored")); await refreshViews(); }}
          disabled={busy}
          busy={ignore.isMutating}
          aria-label={t("ignorePrimaryEdition")}
          title={t("ignorePrimaryEdition")}
          icon={<EyeOff className="h-4 w-4" />}
        />
        <IconButton
          onClick={async () => { const result = await refresh.trigger(); setMessage(result.message); }}
          disabled={busy}
          busy={refresh.isMutating}
          aria-label={t("refreshPrimaryEdition")}
          title={t("refreshPrimaryEdition")}
          icon={<RefreshCw className="h-4 w-4" />}
        />
      </div>
    </div>
  );
}
