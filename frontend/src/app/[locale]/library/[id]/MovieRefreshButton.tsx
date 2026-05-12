"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Clapperboard, EyeOff, Loader2, RefreshCw } from "lucide-react";
import { useConfirmScrapeMovie, useIgnoreMovie, useRefreshMovie, useScrapeMovie } from "@/hooks/useMovie";
import type { MetadataSearchResult } from "@/types/movie";

export default function MovieRefreshButton({ movieId }: { movieId: string }) {
  const router = useRouter();
  const { trigger, isMutating, error } = useRefreshMovie(movieId);
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

  const handleRefresh = async () => {
    await trigger();
    router.refresh();
  };

  const handleScrape = async () => {
    setMessage("");
    setCandidates([]);
    const result = await scrape();
    if (result.status === "needs_review") {
      setCandidates(result.candidates);
      setMessage(result.message);
      return;
    }
    setMessage(result.message);
    router.refresh();
  };

  const handleConfirm = async (tmdbId: number) => {
    const result = await confirmScrape(tmdbId);
    setCandidates([]);
    setMessage(result.message);
    router.refresh();
  };

  const handleIgnore = async () => {
    await ignoreMovie();
    setMessage("Movie ignored");
    router.refresh();
  };

  const anyError = error || scrapeError || confirmError || ignoreError;
  const busy = isMutating || isScraping || isConfirming || isIgnoring;

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
        {candidates.length > 0 && (
          <div className="mt-3 space-y-2">
            {candidates.map((candidate) => (
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
          </div>
        )}
      </div>
      <div className="flex shrink-0 items-center gap-2">
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
