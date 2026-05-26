import useSWR from "swr";
import useSWRMutation from "swr/mutation";
import { API } from "@/lib/api";
import type {
  EventRecord,
  JobAccepted,
  MovieDetail,
  MovieTimelineRestorePreviewReport,
  MovieTimelineRestoreReport,
  MovieTimelineRestoreRequest,
  ScrapeResult,
} from "@/types/movie";

function mutationErrorMessage(detail: unknown, fallback: string) {
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object") {
    const record = detail as Record<string, unknown>;
    if (typeof record.reason === "string") return record.reason;
    if (typeof record.message === "string") return record.message;
    try {
      return JSON.stringify(record);
    } catch {
      return fallback;
    }
  }
  return fallback;
}

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

export function useMovieAuditEvents(id: string, enabled = true) {
  return useSWR<EventRecord[]>(id && enabled ? API.libraryMovieAuditEvents(id) : null, {
    refreshInterval: 5000,
  });
}

export function useMovieTimelineRestorePreview(id?: string | null, scope?: string | null) {
  return useSWRMutation(
    id ? `movie-timeline-restore-preview:${id}:${scope || "default"}` : null,
    async (_key: string, { arg }: { arg: { before_event_id?: string | null; at?: string | null } }): Promise<MovieTimelineRestorePreviewReport> => {
      const res = await fetch(API.libraryMovieTimelineRestorePreviewUrl(id || "", arg));
      if (!res.ok) {
        const errorBody = await res.json().catch(() => null) as { detail?: unknown } | null;
        throw new Error(mutationErrorMessage(errorBody?.detail, "Timeline restore preview failed"));
      }
      return res.json();
    }
  );
}

export function useMovieTimelineRestore(id?: string | null, scope?: string | null) {
  return useSWRMutation(
    id ? `movie-timeline-restore:${id}:${scope || "default"}` : null,
    async (_key: string, { arg }: { arg: MovieTimelineRestoreRequest }): Promise<MovieTimelineRestoreReport> => {
      const res = await fetch(API.libraryMovieTimelineRestore(id || ""), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(arg),
      });
      if (!res.ok) {
        const errorBody = await res.json().catch(() => null) as { detail?: unknown } | null;
        throw new Error(mutationErrorMessage(errorBody?.detail, "Timeline restore failed"));
      }
      return res.json();
    }
  );
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
