"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Award, Clapperboard, EyeOff, Loader2, RefreshCw, Search } from "lucide-react";
import {
  useConfirmScrapeMovie,
  useIgnoreMovie,
  useRefreshMovie,
  useRefreshMovieExternalScores,
  useScrapeMovie,
} from "@/hooks/useMovie";
import { useJobs } from "@/hooks/useJobs";
import { API } from "@/lib/api";
import type { MetadataSearchResult } from "@/types/movie";
import MovieArtworkPicker from "./MovieArtworkPicker";

const DEFAULT_VISIBLE_CANDIDATES = 5;

const parseTmdbId = (value: string) => {
  const trimmed = value.trim();
  const match = trimmed.match(/(?:movie\/)?(\d+)/);
  return match ? Number(match[1]) : null;
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

export default function MovieRefreshButton({ movieId }: { movieId: string }) {
  const router = useRouter();
  const { data: jobs = [] } = useJobs();
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
  const [searchQuery, setSearchQuery] = useState("");
  const [searchYear, setSearchYear] = useState("");
  const [tmdbInput, setTmdbInput] = useState("");
  const [isSearching, setIsSearching] = useState(false);
  const [externalScoreJobId, setExternalScoreJobId] = useState<string | null>(null);
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
    setTmdbInput("");
    setMessage(result.message);
    router.refresh();
  };

  const handleSearch = async () => {
    if (!searchQuery.trim()) return;
    clearQueuedMessageTimer();
    setIsSearching(true);
    setShowAllCandidates(false);
    try {
      const params = new URLSearchParams({ query: searchQuery.trim() });
      const year = Number(searchYear);
      if (Number.isInteger(year) && year > 0) {
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
      setMessage("Metadata search failed");
    } finally {
      setIsSearching(false);
    }
  };

  const handleDirectConfirm = async () => {
    clearQueuedMessageTimer();
    const tmdbId = parseTmdbId(tmdbInput);
    if (!tmdbId) {
      setMessage("Enter a TMDB ID or movie link");
      return;
    }
    setIsSearching(true);
    setShowAllCandidates(false);
    try {
      const res = await fetch(API.metadataMovie(tmdbId));
      if (!res.ok) {
        throw new Error("TMDB movie lookup failed");
      }
      const candidate = await res.json() as MetadataSearchResult;
      setCandidates((current) => prependCandidate(current, candidate));
      setReviewOpen(true);
      setMessage("Review the TMDB match, then click it to confirm");
    } catch {
      setMessage("TMDB movie lookup failed");
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
        {reviewOpen && (
          <div className="mt-3 space-y-2">
            <div className="flex flex-col gap-2 md:flex-row">
              <input
                type="text"
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
                placeholder="Search title"
                className="min-w-0 flex-1 border border-neutral-800 bg-neutral-950 px-3 py-2 text-xs text-white placeholder:text-neutral-600 focus:border-neutral-500 focus:outline-none"
              />
              <input
                type="number"
                value={searchYear}
                onChange={(event) => setSearchYear(event.target.value)}
                placeholder="Year"
                className="w-24 border border-neutral-800 bg-neutral-950 px-3 py-2 text-xs text-white placeholder:text-neutral-600 focus:border-neutral-500 focus:outline-none"
              />
              <button
                type="button"
                onClick={handleSearch}
                disabled={busy || !searchQuery.trim()}
                className="flex h-9 items-center justify-center gap-2 border border-neutral-800 bg-neutral-950 px-3 text-[11px] font-bold uppercase tracking-widest text-white hover:border-neutral-500 disabled:opacity-50"
              >
                {isSearching ? <Loader2 className="h-3 w-3 animate-spin" /> : <Search className="h-3 w-3" />}
                Search
              </button>
            </div>
            <div className="flex flex-col gap-2 md:flex-row">
              <input
                type="text"
                value={tmdbInput}
                onChange={(event) => setTmdbInput(event.target.value)}
                placeholder="TMDB ID or movie link"
                className="min-w-0 flex-1 border border-neutral-800 bg-neutral-950 px-3 py-2 text-xs text-white placeholder:text-neutral-600 focus:border-neutral-500 focus:outline-none"
              />
              <button
                type="button"
                onClick={handleDirectConfirm}
                disabled={busy || !tmdbInput.trim()}
                className="h-9 border border-neutral-800 bg-neutral-950 px-3 text-[11px] font-bold uppercase tracking-widest text-white hover:border-neutral-500 disabled:opacity-50"
              >
                Lookup ID
              </button>
            </div>
            {visibleCandidates.map((candidate) => (
              <button
                key={candidate.tmdb_id}
                type="button"
                onClick={() => handleConfirm(candidate.tmdb_id)}
                disabled={busy}
                className="block w-full border border-neutral-800 bg-neutral-950 px-3 py-2 text-left text-xs text-neutral-300 hover:border-neutral-500 hover:text-white disabled:opacity-50"
              >
                <span className="block font-bold uppercase tracking-widest">
                  {candidate.title} {candidate.year ? `(${candidate.year})` : ""}
                </span>
                <span className="block text-neutral-500">
                  TMDB {candidate.tmdb_id} · {Math.round(candidate.score)}%
                </span>
              </button>
            ))}
            {candidates.length > DEFAULT_VISIBLE_CANDIDATES && (
              <button
                type="button"
                onClick={() => setShowAllCandidates((value) => !value)}
                className="text-xs font-bold uppercase tracking-widest text-neutral-500 hover:text-white"
              >
                {showAllCandidates ? "Show fewer" : `Show ${candidates.length - DEFAULT_VISIBLE_CANDIDATES} more`}
              </button>
            )}
          </div>
        )}
      </div>
      <div className="flex shrink-0 items-center gap-2">
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
        <button
          type="button"
          onClick={handleScrape}
          disabled={busy}
          className="flex h-11 w-11 items-center justify-center border border-neutral-800 bg-neutral-950 text-white hover:border-neutral-500 hover:bg-neutral-900 disabled:cursor-not-allowed disabled:opacity-50"
          aria-label="Scrape metadata"
          title="Scrape metadata"
        >
          {isScraping || isConfirming ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Clapperboard className="h-4 w-4" />
          )}
        </button>
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
    </div>
  );
}
