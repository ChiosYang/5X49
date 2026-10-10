"use client";

import { Award, Check, Clapperboard, EyeOff, Network, RefreshCw, Star } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";

import {
  MetadataCandidatePicker,
  parseMetadataSearchInput,
  parseTmdbId,
  prependMetadataCandidate,
} from "@/components/metadata/MetadataCandidatePicker";
import { Button } from "@/components/ui/Button";
import { InlineFeedback } from "@/components/ui/Feedback";
import {
  useConfirmScrapeFilm,
  useIgnoreLibraryItem,
  useRefreshFilmExternalScores,
  useRefreshLibraryItem,
  useScrapeFilm,
  useUpdateFilmProfileState,
} from "@/hooks/useFilm";
import { useFilmAction } from "@/hooks/useFilmAction";
import { todayLocalDate } from "@/lib/diary";
import { API } from "@/lib/api";
import { metadataActionError } from "@/lib/metadata-review";
import { useRouter } from "@/i18n/routing";
import type { LibraryFilmDetail, MetadataSearchResult } from "@/types/movie";
import MovieArtworkPicker from "./MovieArtworkPicker";
import FilmMoreActions from "./FilmMoreActions";



export default function MovieRefreshButton({ film }: { film: LibraryFilmDetail }) {
  const t = useTranslations("FilmDetail");
  const router = useRouter();
  const filmId = film.id;
  const itemId = film.primary_item.id;
  const [state, setState] = useState(film.profile_state);
  const [profileVersion, setProfileVersion] = useState(film.profile_state.updated_at);
  const [candidates, setCandidates] = useState<MetadataSearchResult[]>([]);
  const [message, setMessage] = useState("");
  const [messageError, setMessageError] = useState(false);
  const [reviewOpen, setReviewOpen] = useState(false);
  const [reviewSearchDraft, setReviewSearchDraft] = useState("");
  const [isSearching, setIsSearching] = useState(false);
  const [artworkOpen, setArtworkOpen] = useState(false);

  // Refresh profile labels without remounting an open disclosure or artwork dialog.
  if (profileVersion !== film.profile_state.updated_at) {
    setProfileVersion(film.profile_state.updated_at);
    setState(film.profile_state);
  }

  const profile = useUpdateFilmProfileState(filmId);
  const refresh = useRefreshLibraryItem(itemId);
  const scores = useRefreshFilmExternalScores(filmId);
  const scrape = useScrapeFilm(filmId);
  const confirmScrape = useConfirmScrapeFilm(filmId);
  const ignore = useIgnoreLibraryItem(itemId);
  const action = useFilmAction(filmId);
  const busy = action.pending || profile.isMutating || refresh.isMutating || scores.isMutating || scrape.isMutating || confirmScrape.isMutating || ignore.isMutating || isSearching;
  const needsMetadataMatch = !film.identities.tmdb || film.primary_item.metadata.scrape_status !== "matched";
  const matchLabel = t(film.primary_item.metadata.scrape_status === "needs_review" ? "reviewMatch" : "matchFilm");

  const updateProfile = async (updates: { watched?: boolean; favorite?: boolean; watched_at?: string | null }) => {
    setMessage("");
    await action.run(() => profile.trigger(updates), t("profileSaveFailed"), setState);
  };

  const handleWatched = async () => {
    if (state.watched && !state.manual_watched) {
      router.push(`/diary?film=${filmId}`);
      return;
    }
    await updateProfile({
      watched: !state.manual_watched,
      watched_at: !state.manual_watched ? state.watched_at || todayLocalDate() : null,
    });
  };

  const handleScrape = async () => {
    setMessage("");
    setMessageError(false);
    action.clear();
    try {
      const result = await scrape.trigger();
      if (result.status === "needs_review") {
        setCandidates(result.candidates);
        setReviewOpen(true);
      } else {
        setReviewOpen(false);
        if (await action.retryRefresh()) action.clear();
      }
      setMessage(result.message);
    } catch (error) {
      setMessageError(true);
      setCandidates([]);
      setReviewOpen(false);
      setMessage(metadataActionError(error, t("actionFailed"), t("metadataNoMatches")));
    }
  };

  const handleConfirm = async (tmdbId: number) => {
    action.clear();
    setMessageError(false);
    try {
      const result = await confirmScrape.trigger(tmdbId);
      setCandidates([]);
      setReviewOpen(false);
      setMessage(result.message);
      if (await action.retryRefresh()) action.clear();
      if (result.film && result.film.id !== filmId) router.replace(`/library/${result.film.id}`);
    } catch (error) {
      setMessageError(true);
      setMessage(metadataActionError(error, t("actionFailed"), t("metadataNoMatches")));
    }
  };

  const handleReviewLookup = async () => {
    const input = reviewSearchDraft.trim();
    if (!input) return;
    setIsSearching(true);
    action.clear();
    setMessageError(false);
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
      setMessageError(true);
      setMessage(error instanceof Error ? error.message : t("metadataLookupFailed"));
    } finally {
      setIsSearching(false);
    }
  };

  const metadataControl = (
    <div className={needsMetadataMatch ? "relative w-full sm:w-auto" : "relative"}>
      {needsMetadataMatch ? <Button
        variant="primary"
        responsiveWidth
        onClick={() => reviewOpen ? setReviewOpen(false) : void handleScrape()}
        disabled={busy}
        busy={scrape.isMutating || confirmScrape.isMutating}
        aria-expanded={reviewOpen}
        icon={<Clapperboard className="h-4 w-4" />}
      >{matchLabel}</Button> : <Button
        onClick={() => reviewOpen ? setReviewOpen(false) : void handleScrape()}
        disabled={busy}
        busy={scrape.isMutating || confirmScrape.isMutating}
        aria-expanded={reviewOpen}
        aria-label={t("scrapeMetadata")}
        title={t("scrapeMetadata")}
        variant="ghost"
        className="w-full justify-start px-3"
        icon={<Clapperboard className="h-4 w-4" />}
      >{t("scrapeMetadata")}</Button>}
      {reviewOpen && (
        <div className={needsMetadataMatch ? "z-popover absolute top-full right-0 w-[min(24rem,calc(100vw-4rem))] pt-3" : "mt-2"}>
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
  );

  return (
    <div data-profile-version={film.profile_state.updated_at || "initial"} className="relative flex min-w-0 flex-col items-start justify-between gap-4 p-8 md:px-8 lg:px-16">
      <div className="space-y-2">
        <span className="type-label block text-ink-subtle">{t("filmControls")}</span>
        <div role="status" aria-live="polite">
          {action.feedback ? <InlineFeedback tone={action.feedback.kind === "failed" ? "error" : action.feedback.kind === "refreshFailed" ? "warning" : "success"}>{action.feedback.message}</InlineFeedback>
            : message && <InlineFeedback tone={messageError ? "error" : "neutral"}>{message}</InlineFeedback>}
          {action.feedback?.kind === "refreshFailed" && <button type="button" disabled={busy} onClick={() => void action.retryRefresh()} className="focus-ring min-h-11 text-sm underline">{t("retryRefresh")}</button>}
        </div>
      </div>
      <div className="w-full min-w-0 space-y-2">
        {needsMetadataMatch && metadataControl}
        <div className="grid min-w-0 grid-cols-2 gap-2 md:grid-cols-1 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]">
        <Button
          onClick={handleWatched}
          disabled={busy}
          busy={profile.isMutating}
          variant={state.watched ? "primary" : "secondary"}
          aria-label={state.watched && !state.manual_watched ? t("viewDiary") : state.manual_watched ? t("markUnwatched") : t("markWatched")}
          title={state.watched && !state.manual_watched ? t("viewDiary") : state.manual_watched ? t("markUnwatched") : t("markWatched")}
          aria-pressed={state.watched}
          size="sm"
          className="min-w-0 px-2"
          icon={<Check className="h-4 w-4" />}
        >{state.watched && !state.manual_watched ? t("viewDiary") : t("watchedAction")}</Button>
        <Button
          onClick={() => updateProfile({ favorite: !state.favorite })}
          disabled={busy}
          busy={profile.isMutating}
          variant={state.favorite ? "primary" : "secondary"}
          aria-label={state.favorite ? t("removeFavorite") : t("favorite")}
          title={state.favorite ? t("removeFavorite") : t("favorite")}
          aria-pressed={state.favorite}
          size="sm"
          className="min-w-0 px-2"
          icon={<Star className={`h-4 w-4 ${state.favorite ? "fill-current" : ""}`} />}
        >{t("favoriteAction")}</Button>
        <FilmMoreActions label={t("moreFilmActions")} modalOpen={artworkOpen}>
        <MovieArtworkPicker movieId={filmId} menuItem disabled={busy} onOpenChange={setArtworkOpen} />
        <Button
          onClick={() => { setMessage(""); void action.run(() => scores.trigger(), t("scoresRefreshFailed"), () => {}, t("scoresQueued")); }}
          disabled={busy}
          busy={scores.isMutating}
          aria-label={t("refreshExternalScores")}
          title={t("refreshExternalScores")}
          variant="ghost"
          className="w-full justify-start px-3"
          icon={<Award className="h-4 w-4" />}
        >{t("refreshExternalScores")}</Button>
        {!needsMetadataMatch && metadataControl}
        <Button
          onClick={() => { setMessage(""); void action.run(() => ignore.trigger(), t("ignoreFailed"), () => {}, t("editionIgnored")); }}
          disabled={busy}
          busy={ignore.isMutating}
          aria-label={t("ignorePrimaryEdition")}
          title={t("ignorePrimaryEdition")}
          variant="ghost"
          className="w-full justify-start px-3"
          icon={<EyeOff className="h-4 w-4" />}
        >{t("ignorePrimaryEdition")}</Button>
        <Button
          onClick={() => { setMessage(""); void action.run(() => refresh.trigger(), t("editionRefreshFailed"), () => {}, t("editionRefreshQueued")); }}
          disabled={busy}
          busy={refresh.isMutating}
          aria-label={t("refreshPrimaryEdition")}
          title={t("refreshPrimaryEdition")}
          variant="ghost"
          className="w-full justify-start px-3"
          icon={<RefreshCw className="h-4 w-4" />}
        >{t("refreshPrimaryEdition")}</Button>
        <Button variant="ghost" className="w-full justify-start px-3" data-film-more-close=""
          onClick={() => {
            const section = document.getElementById("film-analysis");
            section?.scrollIntoView({ behavior: "instant", block: "start" });
            section?.focus({ preventScroll: true });
          }}>
          <Network className="h-4 w-4" />{t("analysisControls")}
        </Button>
        </FilmMoreActions>
        </div>
      </div>
    </div>
  );
}
