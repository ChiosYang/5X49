"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Award, Check, Clapperboard, EyeOff, Heart, History, Loader2, RefreshCw, Search } from "lucide-react";
import { mutate } from "swr";
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

const DEFAULT_VISIBLE_CANDIDATES = 5;

const parseTmdbId = (value: string) => {
  const trimmed = value.trim();
  const match = trimmed.match(/(?:movie\/)?(\d+)/);
  return match ? Number(match[1]) : null;
};

const parseSearchInput = (value: string) => {
  const yearMatch = value.match(/\b(19\d{2}|20\d{2})\b/);
  return {
    query: value.replace(/\b(19\d{2}|20\d{2})\b/, "").trim() || value.trim(),
    year: yearMatch ? Number(yearMatch[1]) : null,
  };
};

const prependCandidate = (
  candidates: MetadataSearchResult[],
  candidate: MetadataSearchResult,
) => [candidate, ...candidates.filter((item) => item.tmdb_id !== candidate.tmdb_id)];

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
  const [showAllCandidates, setShowAllCandidates] = useState(false);
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
    setShowAllCandidates(false);
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
    setShowAllCandidates(false);
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
    setShowAllCandidates(false);
    try {
      const tmdbId = parseTmdbId(input);
      if (tmdbId) {
        const res = await fetch(API.metadataMovie(tmdbId));
        if (!res.ok) {
          throw new Error("TMDB movie lookup failed");
        }
        const candidate = await res.json() as MetadataSearchResult;
        setCandidates((current) => prependCandidate(current, candidate));
        setReviewOpen(true);
        setMessage("Review the TMDB match, then click it to confirm");
        return;
      }

      const { query, year } = parseSearchInput(input);
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
  const visibleCandidates = showAllCandidates
    ? candidates
    : candidates.slice(0, DEFAULT_VISIBLE_CANDIDATES);
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
    <div className="p-8 md:px-16 flex items-center justify-between gap-4">
      <div className="space-y-2">
        <span className="block text-xs font-bold uppercase tracking-widest text-neutral-500">
          Metadata
        </span>
        {message && (
          <span className="block text-xs uppercase tracking-widest text-neutral-400">
            {message}
          </span>
        )}
        {anyError && (
          <span className="block text-xs uppercase tracking-widest text-red-500">
            Metadata action failed
          </span>
        )}
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <button
          type="button"
          onClick={handleToggleWatched}
          disabled={isUpdatingUserState}
          className={`flex h-11 w-11 items-center justify-center border transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
            watched
              ? "border-white bg-white text-black"
              : "border-neutral-800 bg-neutral-950 text-white hover:border-neutral-500 hover:bg-neutral-900"
          }`}
          aria-label={watched ? "Mark unwatched" : "Mark watched"}
          title={watched ? "Mark unwatched" : "Mark watched"}
        >
          {userStateAction === "watched" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
        </button>
        <button
          type="button"
          onClick={handleToggleFavorite}
          disabled={isUpdatingUserState}
          className={`flex h-11 w-11 items-center justify-center border transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
            favorite
              ? "border-white bg-white text-black"
              : "border-neutral-800 bg-neutral-950 text-white hover:border-neutral-500 hover:bg-neutral-900"
          }`}
          aria-label={favorite ? "Remove favorite" : "Favorite"}
          title={favorite ? "Remove favorite" : "Favorite"}
        >
          {userStateAction === "favorite" ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Heart className={`h-4 w-4 ${favorite ? "fill-current" : ""}`} />
          )}
        </button>
        <button
          type="button"
          onClick={() => {
            setReviewOpen(false);
            setActivityOpen(true);
          }}
          className="flex h-11 w-11 items-center justify-center border border-neutral-800 bg-neutral-950 text-white hover:border-neutral-500 hover:bg-neutral-900"
          aria-label="Show library history"
          title="Show library history"
        >
          <History className="h-4 w-4" />
        </button>
        <MovieArtworkPicker movieId={movieId} />
        <button
          type="button"
          onClick={handleRefreshExternalScores}
          disabled={busy}
          className="flex h-11 w-11 items-center justify-center border border-neutral-800 bg-neutral-950 text-white hover:border-neutral-500 hover:bg-neutral-900 disabled:cursor-not-allowed disabled:opacity-50"
          aria-label="Refresh external scores"
          title="Refresh external scores"
        >
          {isRefreshingExternalScores ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Award className="h-4 w-4" />
          )}
        </button>
        <div className="relative">
          <button
            type="button"
            onClick={() => reviewOpen ? setReviewOpen(false) : handleScrape()}
            disabled={busy}
            className="flex h-11 w-11 items-center justify-center border border-neutral-800 bg-neutral-950 text-white hover:border-neutral-500 hover:bg-neutral-900 disabled:cursor-not-allowed disabled:opacity-50"
            aria-label="Scrape metadata"
            aria-expanded={reviewOpen}
            title="Scrape metadata"
          >
            {isScraping || isConfirming ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Clapperboard className="h-4 w-4" />
            )}
          </button>

          {reviewOpen && (
            <div className="absolute right-0 top-full z-50 w-[min(24rem,calc(100vw-4rem))] pt-3">
              <div className="border border-neutral-800 bg-black/95 p-4 shadow-2xl shadow-black/60 backdrop-blur">
                <div className="mb-3 flex items-center justify-between gap-4 border-b border-neutral-900 pb-3">
                  <p className="text-xs font-bold uppercase tracking-widest text-neutral-400">
                    Choose TMDB Match
                  </p>
                </div>
                <div className="scrollbar-minimal max-h-72 overflow-y-auto pr-1">
                  <div className="space-y-2">
                    <div className="flex gap-2">
                      <input
                        type="text"
                        value={reviewSearchDraft}
                        onChange={(event) => setReviewSearchDraft(event.target.value)}
                        placeholder="Title, year, TMDB ID, or movie link"
                        className="min-w-0 flex-1 border border-neutral-800 bg-neutral-950 px-3 py-2 text-xs text-white placeholder:text-neutral-600 focus:border-neutral-500 focus:outline-none"
                      />
                      <button
                        type="button"
                        onClick={handleReviewLookup}
                        disabled={busy || !reviewSearchDraft.trim()}
                        className="flex h-9 w-24 items-center justify-center gap-1.5 border border-neutral-800 bg-neutral-950 px-2 text-[10px] font-bold uppercase tracking-widest text-white transition-colors hover:border-neutral-500 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {isSearching ? (
                          <Loader2 className="h-3 w-3 animate-spin" />
                        ) : (
                          <Search className="h-3 w-3" />
                        )}
                        Lookup
                      </button>
                    </div>
                    <div className="space-y-2 pt-1">
                      {visibleCandidates.map((candidate) => (
                        <button
                          key={candidate.tmdb_id}
                          type="button"
                          onClick={() => handleConfirm(candidate.tmdb_id)}
                          disabled={busy}
                          className="block w-full border border-neutral-800 bg-neutral-950 px-3 py-2 text-left text-xs text-neutral-300 transition-colors hover:border-neutral-500 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          <span className="flex items-start justify-between gap-3">
                            <span className="min-w-0">
                              <span className="block truncate font-bold uppercase tracking-widest">
                                {candidate.title} {candidate.year ? `(${candidate.year})` : ""}
                              </span>
                              <span className="block text-neutral-500">
                                TMDB {candidate.tmdb_id} · {Math.round(candidate.score)}%
                              </span>
                            </span>
                            {isConfirming && <Loader2 className="mt-0.5 h-3 w-3 shrink-0 animate-spin" />}
                          </span>
                        </button>
                      ))}
                      {candidates.length > DEFAULT_VISIBLE_CANDIDATES && (
                        <button
                          type="button"
                          onClick={() => setShowAllCandidates((value) => !value)}
                          className="text-[10px] font-bold uppercase tracking-widest text-neutral-500 hover:text-white"
                        >
                          {showAllCandidates ? "Show fewer" : `Show ${candidates.length - DEFAULT_VISIBLE_CANDIDATES} more`}
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
        <button
          type="button"
          onClick={handleIgnore}
          disabled={busy}
          className="flex h-11 w-11 items-center justify-center border border-neutral-800 bg-neutral-950 text-white hover:border-neutral-500 hover:bg-neutral-900 disabled:cursor-not-allowed disabled:opacity-50"
          aria-label="Ignore movie"
          title="Ignore movie"
        >
          {isIgnoring ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <EyeOff className="h-4 w-4" />
          )}
        </button>
        <button
          type="button"
          onClick={handleRefresh}
          disabled={busy}
          className="flex h-11 w-11 items-center justify-center border border-neutral-800 bg-neutral-950 text-white hover:border-neutral-500 hover:bg-neutral-900 disabled:cursor-not-allowed disabled:opacity-50"
          aria-label="Refresh metadata"
          title="Refresh metadata"
        >
          {isMutating ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <RefreshCw className="h-4 w-4" />
          )}
        </button>
      </div>
      <MovieActivityTimeline
        movieId={movieId}
        open={activityOpen}
        onClose={() => setActivityOpen(false)}
      />
    </div>
  );
}
