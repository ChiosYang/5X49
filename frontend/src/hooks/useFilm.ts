import useSWR from "swr";
import useSWRMutation from "swr/mutation";

import { API } from "@/lib/api";
import type {
  FilmAnalysisView,
  FilmProfileState,
  FilmProfileStateUpdate,
  JobAccepted,
  LibraryFilmDetail,
  OperationRestoreResult,
  OperationSnapshotPreview,
  ScrapeResult,
  WatchHistoryEntry,
} from "@/types/movie";

const errorMessage = async (response: Response, fallback: string) => {
  const body = await response.json().catch(() => null) as { detail?: unknown } | null;
  if (typeof body?.detail === "string") return body.detail;
  return fallback;
};

export function useFilm(filmId: string, fallbackData?: LibraryFilmDetail) {
  return useSWR<LibraryFilmDetail>(filmId ? API.libraryFilm(filmId) : null, {
    fallbackData,
    refreshInterval: (data) => data?.analysis.status === "running" ? 5000 : 0,
  });
}

export function useFilmAnalysis(filmId: string) {
  return useSWR<FilmAnalysisView | null>(filmId ? API.filmAnalysis(filmId) : null, {
    refreshInterval: (data) => data?.status === "running" ? 5000 : 0,
  });
}

export function useFilmProfileState(filmId: string) {
  return useSWR<FilmProfileState>(filmId ? API.filmProfileState(filmId) : null);
}

export function useUpdateFilmProfileState(filmId: string) {
  return useSWRMutation(
    filmId ? API.filmProfileState(filmId) : null,
    async (_key: string, { arg }: { arg: FilmProfileStateUpdate }): Promise<FilmProfileState> => {
      const response = await fetch(API.filmProfileState(filmId), {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(arg),
      });
      if (!response.ok) throw new Error(await errorMessage(response, "Failed to update Film state"));
      return response.json();
    },
  );
}

export function useWatchHistory() {
  return useSWR<WatchHistoryEntry[]>(API.watchHistory());
}

export function useAnalyzeFilm(filmId: string) {
  return useSWRMutation(
    filmId ? API.filmAnalysisRuns(filmId) : null,
    async (): Promise<JobAccepted> => {
      const response = await fetch(API.filmAnalysisRuns(filmId), { method: "POST" });
      if (!response.ok) throw new Error(await errorMessage(response, "Failed to trigger analysis"));
      return response.json();
    },
  );
}

export function useRefreshLibraryItem(itemId: string) {
  return useSWRMutation(
    itemId ? API.libraryItemRefresh(itemId) : null,
    async (): Promise<JobAccepted> => {
      const response = await fetch(API.libraryItemRefresh(itemId), { method: "POST" });
      if (!response.ok) throw new Error(await errorMessage(response, "Failed to refresh edition"));
      return response.json();
    },
  );
}

export function useRefreshFilmExternalScores(filmId: string) {
  return useSWRMutation(
    filmId ? API.filmExternalScores(filmId) : null,
    async (): Promise<JobAccepted> => {
      const response = await fetch(API.filmExternalScores(filmId), { method: "POST" });
      if (!response.ok) throw new Error(await errorMessage(response, "Failed to refresh external scores"));
      return response.json();
    },
  );
}

export function useScrapeFilm(filmId: string) {
  return useSWRMutation(
    filmId ? API.filmScrape(filmId) : null,
    async (): Promise<ScrapeResult> => {
      const response = await fetch(API.filmScrape(filmId), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode: "auto", overwrite: false, write_nfo: true, download_artwork: true }),
      });
      if (!response.ok) throw new Error(await errorMessage(response, "Failed to scrape metadata"));
      return response.json();
    },
  );
}

export function useConfirmScrapeFilm(filmId: string) {
  return useSWRMutation(
    filmId ? API.filmScrapeConfirm(filmId) : null,
    async (_key: string, { arg: tmdbId }: { arg: number }): Promise<ScrapeResult> => {
      const response = await fetch(`${API.filmScrapeConfirm(filmId)}?tmdb_id=${tmdbId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode: "manual", overwrite: false, write_nfo: true, download_artwork: true }),
      });
      if (!response.ok) throw new Error(await errorMessage(response, "Failed to scrape metadata"));
      return response.json();
    },
  );
}

export function useIgnoreLibraryItem(itemId: string) {
  return useSWRMutation(
    itemId ? API.libraryItemIgnore(itemId) : null,
    async () => {
      const response = await fetch(API.libraryItemIgnore(itemId), { method: "POST" });
      if (!response.ok) throw new Error(await errorMessage(response, "Failed to ignore edition"));
      return response.json();
    },
  );
}

export function useOperationPreview(snapshotId?: string | null) {
  return useSWR<OperationSnapshotPreview>(snapshotId ? API.operationPreview(snapshotId) : null);
}

export function useRestoreOperation(snapshotId?: string | null) {
  return useSWRMutation(
    snapshotId ? API.operationRestore(snapshotId) : null,
    async (_key: string, { arg }: { arg: { confirmation_token: string } }): Promise<OperationRestoreResult> => {
      const response = await fetch(API.operationRestore(snapshotId || ""), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(arg),
      });
      if (!response.ok) throw new Error(await errorMessage(response, "Operation restore failed"));
      return response.json();
    },
  );
}
