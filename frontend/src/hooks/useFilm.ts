import useSWR from "swr";
import useSWRMutation from "swr/mutation";
import { mutate } from "swr";

import { API } from "@/lib/api";
import { fetcher, responseError } from "@/lib/fetcher";
import { refreshViewingReadCaches } from "@/lib/viewing-write";
import { isDnaCacheKey } from "@/lib/cinema-dna";
import type {
  FilmAnalysisView,
  FilmGraphView,
  FilmProfileState,
  FilmProfileStateUpdate,
  WorkflowAccepted,
  LibraryFilmDetail,
  MetadataSearchResult,
  OperationRestoreResult,
  OperationSnapshotPreview,
  ScrapeResult,
  ViewingDeleteResult,
  ViewingPage,
  ViewingView,
} from "@/types/movie";


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

export function useFilmGraph(filmId: string) {
  return useSWR<FilmGraphView>(filmId ? API.filmGraph(filmId) : null);
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
      if (!response.ok) throw await responseError(response, "Failed to update Film state");
      return response.json();
    },
    { revalidate: false },
  );
}

export function useProfileViewings(
  limit = 100,
  offset = 0,
  filmId?: string,
  enabled = true,
  view: "timeline" | "recent" = "timeline",
) {
  return useSWR<ViewingPage>(enabled ? API.profileViewings({ limit, offset, filmId, view }) : null);
}

export function useFilmViewings(filmId: string) {
  return useSWR<ViewingView[]>(filmId ? API.filmViewings(filmId) : null);
}

export function useCreateFilmViewing(filmId: string) {
  return useSWRMutation(
    filmId ? API.filmViewings(filmId) : null,
    async (_key: string, { arg }: { arg: { watched_at: string | null } }): Promise<ViewingView> => {
      const response = await fetch(API.filmViewings(filmId), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(arg),
      });
      if (!response.ok) throw await responseError(response, "Failed to create Viewing");
      return response.json();
    },
    { revalidate: false },
  );
}

export function useUpdateViewing(viewingId?: string | null) {
  return useSWRMutation(
    viewingId ? API.viewing(viewingId) : null,
    async (_key: string, { arg }: { arg: { watched_at: string | null } }): Promise<ViewingView> => {
      const response = await fetch(API.viewing(viewingId || ""), {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(arg),
      });
      if (!response.ok) throw await responseError(response, "Failed to update Viewing");
      return response.json();
    },
    { revalidate: false },
  );
}

export function useDeleteViewing(viewingId?: string | null) {
  return useSWRMutation(
    viewingId ? API.viewing(viewingId) : null,
    async (): Promise<ViewingDeleteResult> => {
      const response = await fetch(API.viewing(viewingId || ""), { method: "DELETE" });
      if (!response.ok) throw await responseError(response, "Failed to delete Viewing");
      return response.json();
    },
    { revalidate: false },
  );
}

export async function invalidateViewingCaches(filmId: string, cacheKeys?: Iterable<string>) {
  if (cacheKeys) {
    const directKeys = new Set([API.filmViewings(filmId), API.filmProfileState(filmId), API.libraryFilm(filmId), API.libraryFilms()]);
    const keys = [...cacheKeys].filter((key) => directKeys.has(key) || key.startsWith(`${API.libraryFilmPage()}?`)
      || isDnaCacheKey(key, API.cinemaDna())
      || key === API.profileViewings() || key.startsWith(`${API.profileViewings()}?`));
    // SWR revalidation resolves with stale data on HTTP errors. Supply an explicit
    // read as mutation data instead, so the receipt can distinguish a failed read.
    await refreshViewingReadCaches(keys, fetcher, (key, read) => mutate(key, read, {
      revalidate: false, throwOnError: true,
    }));
    return;
  }
  await Promise.all([
    mutate((key) => isDnaCacheKey(key, API.cinemaDna()), undefined, { revalidate: true }),
    mutate(API.filmViewings(filmId)),
    mutate(API.filmProfileState(filmId)),
    mutate(API.libraryFilm(filmId)),
    mutate(API.libraryFilms()),
    mutate(
      (key) => typeof key === "string" && key.startsWith(API.profileViewings()),
      undefined,
      { revalidate: true },
    ),
  ]);
}

export function useAnalyzeFilm(filmId: string) {
  return useSWRMutation(
    filmId ? API.filmAnalysisRuns(filmId) : null,
    async (): Promise<WorkflowAccepted> => {
      const response = await fetch(API.filmAnalysisRuns(filmId), { method: "POST" });
      if (!response.ok) throw await responseError(response, "Failed to trigger analysis");
      return response.json();
    },
  );
}

export function useRefreshLibraryItem(itemId: string) {
  return useSWRMutation(
    itemId ? API.libraryItemRefresh(itemId) : null,
    async (): Promise<WorkflowAccepted> => {
      const response = await fetch(API.libraryItemRefresh(itemId), { method: "POST" });
      if (!response.ok) throw await responseError(response, "Failed to refresh edition");
      return response.json();
    },
  );
}

export function useRefreshFilmExternalScores(filmId: string) {
  return useSWRMutation(
    filmId ? API.filmExternalScores(filmId) : null,
    async (): Promise<WorkflowAccepted> => {
      const response = await fetch(API.filmExternalScores(filmId), { method: "POST" });
      if (!response.ok) throw await responseError(response, "Failed to refresh external scores");
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
      if (!response.ok) throw await responseError(response, "Failed to scrape metadata");
      return response.json();
    },
  );
}

export function useFilmScrapeCandidates(filmId: string, enabled = true) {
  return useSWR<MetadataSearchResult[]>(
    enabled && filmId ? API.filmScrapeCandidates(filmId) : null,
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
      if (!response.ok) throw await responseError(response, "Failed to scrape metadata");
      return response.json();
    },
  );
}

export function useIgnoreLibraryItem(itemId: string) {
  return useSWRMutation(
    itemId ? API.libraryItemIgnore(itemId) : null,
    async () => {
      const response = await fetch(API.libraryItemIgnore(itemId), { method: "POST" });
      if (!response.ok) throw await responseError(response, "Failed to ignore edition");
      return response.json();
    },
  );
}

export function useSelectPrimaryEdition(filmId: string) {
  return useSWRMutation(API.filmPrimaryEdition(filmId),
    async (_key: string, { arg }: { arg: string }): Promise<LibraryFilmDetail> => {
      const response = await fetch(API.filmPrimaryEdition(filmId), {method: "PUT",
        headers: { "Content-Type": "application/json" }, body: JSON.stringify({library_item_id: arg})});
      if (!response.ok) throw await responseError(response, "Failed to select primary edition");
      return response.json();
    }, { revalidate: false });
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
      if (!response.ok) throw await responseError(response, "Operation restore failed");
      return response.json();
    },
  );
}
