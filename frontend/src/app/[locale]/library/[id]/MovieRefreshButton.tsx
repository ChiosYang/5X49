"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Award, Check, Clapperboard, EyeOff, History, RefreshCw, Star } from "lucide-react";
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
  useConfirmScrapeMovie,
  useIgnoreMovie,
  useMovieUserState,
  useRefreshMovie,
  useRefreshMovieExternalScores,
  useScrapeMovie,
  useUpdateMovieUserState,
} from "@/hooks/useMovie";
import { useJobs } from "@/hooks/useJobs";
import { API } from "@/lib/api";
import type { MetadataSearchResult } from "@/types/movie";
import MovieActivityTimeline from "./MovieActivityTimeline";
import MovieArtworkPicker from "./MovieArtworkPicker";

const externalScoreResultMessage = (result?: Record<string, unknown> | null) => {
  const updatedSources = result?.updated_sources;
  if (Array.isArray(updatedSources) && updatedSources.length > 0) {
    return "External scores refreshed";
  }
  return "No external score match found";
};

function todayDateValue() {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export default function MovieRefreshButton({ movieId }: { movieId: string }) {
  const router = useRouter();
  const { data: jobs = [] } = useJobs();
  const { data: userState } = useMovieUserState(movieId);
  const { trigger: updateUserState, isMutating: isUpdatingUserState } = useUpdateMovieUserState(movieId);
  const { trigger, isMutating, error } = useRefreshMovie(movieId);
  const {
    trigger: refreshExternalScores,
    isMutating: isRefreshingExternalScores,
    error: externalScoresError,
  } = useRefreshMovieExternalScores(movieId);
  const {
    trigger: scrape,
    isMutating: isScraping,
    error: scrapeError,
  } = useScrapeMovie(movieId);
  const {
    trigger: confirmScrape,
    isMutating: isConfirming,
    error: confirmError,
  } = useConfirmScrapeMovie(movieId);
  const {
    trigger: ignoreMovie,
    isMutating: isIgnoring,
    error: ignoreError,
  } = useIgnoreMovie(movieId);
  const [candidates, setCandidates] = useState<MetadataSearchResult[]>([]);
  const [message, setMessage] = useState<string>("");
  const [reviewOpen, setReviewOpen] = useState(false);
  const [reviewSearchDraft, setReviewSearchDraft] = useState("");
  const [isSearching, setIsSearching] = useState(false);
  const [externalScoreJobId, setExternalScoreJobId] = useState<string | null>(null);
  const [activityOpen, setActivityOpen] = useState(false);
  const [userStateAction, setUserStateAction] = useState<"watched" | "favorite" | null>(null);
  const completedExternalScoreJob = useRef<string | null>(null);
  const queuedMessageTimer = useRef<number | null>(null);

  useEffect(() => {
    return () => {
      if (queuedMessageTimer.current) {
        window.clearTimeout(queuedMessageTimer.current);
      }
    };
  }, []);

  useEffect(() => {
    if (!externalScoreJobId) return;

    const job = jobs.find((item) => item.id === externalScoreJobId);
    if (!job) return;

    if (job.status === "queued" || job.status === "running") {
      return;
    }

    if (completedExternalScoreJob.current === job.id) return;
    completedExternalScoreJob.current = job.id;
    if (queuedMessageTimer.current) {
      window.clearTimeout(queuedMessageTimer.current);
      queuedMessageTimer.current = null;
    }

    setMessage(
      job.status === "failed"
        ? job.error || "External score refresh failed"
        : externalScoreResultMessage(job.result),
    );
    router.refresh();

    const timeout = window.setTimeout(() => {
      setMessage("");
      setExternalScoreJobId(null);
      completedExternalScoreJob.current = null;
    }, 3500);

    return () => window.clearTimeout(timeout);
  }, [externalScoreJobId, jobs, router]);

  const clearQueuedMessageTimer = () => {
    if (queuedMessageTimer.current) {
      window.clearTimeout(queuedMessageTimer.current);
      queuedMessageTimer.current = null;
    }
  };

  const handleRefresh = async () => {
    await trigger();
    router.refresh();
  };

  const handleRefreshExternalScores = async () => {
    const result = await refreshExternalScores();
    setMessage(result?.message || "External score refresh queued");
    setExternalScoreJobId(result?.job_id || null);
    completedExternalScoreJob.current = null;
    clearQueuedMessageTimer();
    queuedMessageTimer.current = window.setTimeout(() => {
      setMessage("");
      queuedMessageTimer.current = null;
    }, 2500);
    router.refresh();
  };

  const handleScrape = async () => {
    clearQueuedMessageTimer();
    setExternalScoreJobId(null);
    setMessage("");
    setCandidates([]);
    setReviewOpen(false);
    const result = await scrape();
    if (result.status === "needs_review") {
      setCandidates(result.candidates);
      setReviewOpen(true);
      setMessage(result.message);
      return;
    }
    setMessage(result.message);
    router.refresh();
  };

  const handleConfirm = async (tmdbId: number) => {
    clearQueuedMessageTimer();
    setExternalScoreJobId(null);
    const result = await confirmScrape(tmdbId);
    setCandidates([]);
    setReviewOpen(false);
    setMessage(result.message);
    router.refresh();
  };

  const handleReviewLookup = async () => {
    clearQueuedMessageTimer();
    const input = reviewSearchDraft.trim();
    if (!input) {
      setMessage("Enter a title, year, TMDB ID, or movie link");
      return;
    }
    setIsSearching(true);
    try {
      const tmdbId = parseTmdbId(input);
      if (tmdbId) {
        const res = await fetch(API.metadataMovie(tmdbId));
        if (!res.ok) {
          throw new Error("TMDB movie lookup failed");
        }
        const candidate = await res.json() as MetadataSearchResult;
        setCandidates((current) => prependMetadataCandidate(current, candidate));
        setReviewOpen(true);
        setMessage("Review the TMDB match, then click it to confirm");
        return;
      }

      const { query, year } = parseMetadataSearchInput(input);
      const params = new URLSearchParams({ query });
      if (year) {
        params.set("year", String(year));
      }
      const res = await fetch(`${API.metadataSearch()}?${params.toString()}`);
      if (!res.ok) {
        throw new Error("Metadata search failed");
      }
      const results = await res.json() as MetadataSearchResult[];
      setCandidates(results);
      setReviewOpen(true);
      setMessage(results.length ? "Choose a TMDB match to continue" : "No TMDB matches found");
    } catch {
      setMessage("Metadata lookup failed");
    } finally {
      setIsSearching(false);
    }
  };

  const handleIgnore = async () => {
    clearQueuedMessageTimer();
    await ignoreMovie();
    setMessage("Movie ignored");
    router.refresh();
  };

  const anyError = error || scrapeError || confirmError || ignoreError || externalScoresError;
  const busy = isMutating || isScraping || isConfirming || isIgnoring || isSearching || isRefreshingExternalScores;
  const watched = Boolean(userState?.watched);
  const favorite = Boolean(userState?.favorite);

  const handleToggleWatched = async () => {
    setUserStateAction("watched");
    try {
      const saved = await updateUserState({
        watched: !watched,
        watched_at: !watched ? userState?.watched_at || todayDateValue() : null,
      });
      setMessage("Watch state saved");
      await Promise.all([
        mutate(API.libraryMovieUserState(movieId), saved, false),
        mutate(API.libraryUserStates()),
        mutate(API.watchHistory()),
      ]);
      router.refresh();
    } finally {
      setUserStateAction(null);
    }
  };

  const handleToggleFavorite = async () => {
    setUserStateAction("favorite");
    try {
      const saved = await updateUserState({ favorite: !favorite });
      setMessage("Watch state saved");
      await Promise.all([
        mutate(API.libraryMovieUserState(movieId), saved, false),
        mutate(API.libraryUserStates()),
        mutate(API.watchHistory()),
      ]);
      router.refresh();
    } finally {
      setUserStateAction(null);
    }
  };

  return (
    <div className="flex flex-col items-start justify-between gap-4 p-8 sm:flex-row sm:items-center md:px-16">
      <div className="space-y-2">
        <span className="type-label block text-ink-subtle">
          Metadata
        </span>
        {message && (
          <InlineFeedback className="tracking-widest uppercase">
            {message}
          </InlineFeedback>
        )}
        {anyError && (
          <InlineFeedback tone="error" className="tracking-widest uppercase">
            Metadata action failed
          </InlineFeedback>
        )}
      </div>
      <div className="flex max-w-full flex-wrap items-center gap-2 sm:shrink-0">
        <IconButton
          onClick={handleToggleWatched}
          disabled={isUpdatingUserState}
          busy={userStateAction === "watched"}
          variant={watched ? "primary" : "secondary"}
          aria-label={watched ? "Mark unwatched" : "Mark watched"}
          title={watched ? "Mark unwatched" : "Mark watched"}
          icon={<Check className="h-4 w-4" />}
        />
        <IconButton
          onClick={handleToggleFavorite}
          disabled={isUpdatingUserState}
          busy={userStateAction === "favorite"}
          variant={favorite ? "primary" : "secondary"}
          aria-label={favorite ? "Remove favorite" : "Favorite"}
          title={favorite ? "Remove favorite" : "Favorite"}
          icon={<Star className={`h-4 w-4 ${favorite ? "fill-current" : ""}`} />}
        />
        <IconButton
          onClick={() => {
            setReviewOpen(false);
            setActivityOpen(true);
          }}
          aria-label="Show library history"
          title="Show library history"
          icon={<History className="h-4 w-4" />}
        />
        <MovieArtworkPicker movieId={movieId} />
        <IconButton
          onClick={handleRefreshExternalScores}
          disabled={busy}
          busy={isRefreshingExternalScores}
          aria-label="Refresh external scores"
          title="Refresh external scores"
          icon={<Award className="h-4 w-4" />}
        />
        <div className="relative">
          <IconButton
            onClick={() => reviewOpen ? setReviewOpen(false) : handleScrape()}
            disabled={busy}
            busy={isScraping || isConfirming}
            aria-label="Scrape metadata"
            aria-expanded={reviewOpen}
            title="Scrape metadata"
            icon={<Clapperboard className="h-4 w-4" />}
          />

          {reviewOpen && (
            <div className="z-popover absolute top-full right-0 w-[min(24rem,calc(100vw-4rem))] pt-3">
              <div className="liquid-glass-popover relative border border-line/80 p-4">
                <div className="mb-3 flex items-center justify-between gap-4 border-b border-line pb-3">
                  <p className="type-label text-ink-muted">
                    Choose TMDB Match
                  </p>
                </div>
                <div className="scrollbar-minimal max-h-72 overflow-y-auto pr-1">
                  <MetadataCandidatePicker
                    key={isSearching ? "searching" : candidates.map((candidate) => candidate.tmdb_id).join(",")}
                    candidates={candidates}
                    inputValue={reviewSearchDraft}
                    onInputChange={setReviewSearchDraft}
                    onLookup={handleReviewLookup}
                    onSelect={(candidate) => handleConfirm(candidate.tmdb_id)}
                    lookupBusy={isSearching}
                    selectionBusy={isConfirming}
                    disabled={busy}
                    lookupLabel="Lookup"
                    placeholder="Title, year, TMDB ID, or movie link"
                    showFewerLabel="Show fewer"
                    showMoreLabel={(count) => `Show ${count} more`}
                  />
                </div>
              </div>
            </div>
          )}
        </div>
        <IconButton
          onClick={handleIgnore}
          disabled={busy}
          busy={isIgnoring}
          aria-label="Ignore movie"
          title="Ignore movie"
          icon={<EyeOff className="h-4 w-4" />}
        />
        <IconButton
          onClick={handleRefresh}
          disabled={busy}
          busy={isMutating}
          aria-label="Refresh metadata"
          title="Refresh metadata"
          icon={<RefreshCw className="h-4 w-4" />}
        />
      </div>
      <MovieActivityTimeline
        movieId={movieId}
        open={activityOpen}
        onClose={() => setActivityOpen(false)}
      />
    </div>
  );
}
