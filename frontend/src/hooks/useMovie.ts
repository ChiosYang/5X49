import useSWR from "swr";
import useSWRMutation from "swr/mutation";
import { API } from "@/lib/api";
import type { EventRecord, JobAccepted, MovieDetail, ScrapeResult } from "@/types/movie";

export function useMovie(id: string, fallbackData?: MovieDetail) {
  return useSWR<MovieDetail>(id ? API.libraryMovie(id) : null, {
    fallbackData,
    // Poll every 5s while analysis is processing, stop otherwise
    refreshInterval: (data?: MovieDetail) => {
      if (data?.analysis_status === "processing") return 5000;
      return 0;
    },
  });
}

export function useMovieAuditEvents(id: string) {
  return useSWR<EventRecord[]>(id ? API.libraryMovieAuditEvents(id) : null, {
    refreshInterval: 5000,
  });
}

export function useAnalyzeMovie(id: string) {
  return useSWRMutation(
    API.libraryMovie(id),
    async () => {
      const res = await fetch(API.libraryAnalyze(id), { method: "POST" });
      if (!res.ok) throw new Error("Failed to trigger analysis");
      return res.json() as Promise<JobAccepted>;
    }
  );
}

export function useRefreshMovie(id: string) {
  return useSWRMutation(
    API.libraryMovie(id),
    async () => {
      const res = await fetch(API.libraryRefresh(id), { method: "POST" });
      if (!res.ok) throw new Error("Failed to refresh movie");
      return res.json() as Promise<JobAccepted>;
    }
  );
}

export function useRefreshMovieExternalScores(id: string) {
  return useSWRMutation(
    API.libraryMovie(id),
    async () => {
      const res = await fetch(API.libraryExternalScores(id), { method: "POST" });
      if (!res.ok) throw new Error("Failed to refresh external scores");
      return res.json() as Promise<JobAccepted>;
    }
  );
}

export function useScrapeMovie(id: string) {
  return useSWRMutation(
    API.libraryMovie(id),
    async (): Promise<ScrapeResult> => {
      const res = await fetch(API.libraryScrape(id), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          mode: "auto",
          overwrite: false,
          write_nfo: true,
          download_artwork: true,
        }),
      });
      if (!res.ok) {
        const errorBody = await res.json().catch(() => null);
        throw new Error(errorBody?.detail?.message || "Failed to scrape metadata");
      }
      return res.json();
    }
  );
}

export function useConfirmScrapeMovie(id: string) {
  return useSWRMutation(
    API.libraryMovie(id),
    async (_url: string, { arg: tmdbId }: { arg: number }): Promise<ScrapeResult> => {
      const res = await fetch(`${API.libraryScrapeConfirm(id)}?tmdb_id=${tmdbId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          mode: "manual",
          overwrite: false,
          write_nfo: true,
          download_artwork: true,
        }),
      });
      if (!res.ok) {
        const errorBody = await res.json().catch(() => null);
        throw new Error(errorBody?.detail?.message || "Failed to scrape metadata");
      }
      return res.json();
    }
  );
}

export function useIgnoreMovie(id: string) {
  return useSWRMutation(
    API.libraryMovie(id),
    async () => {
      const res = await fetch(API.libraryIgnore(id), { method: "POST" });
      if (!res.ok) throw new Error("Failed to ignore movie");
      return res.json();
    }
  );
}
