import useSWR from "swr";
import useSWRMutation from "swr/mutation";
import { API } from "@/lib/api";

// =====================
// Queries
// =====================

export function useModelSettings() {
  return useSWR<{ current_model: string; available_models: string[] }>(
    API.settingsModel()
  );
}

export function useBaseUrl() {
  return useSWR<{ base_url: string }>(API.settingsBaseUrl());
}

export function useMediaDir() {
  return useSWR<{ media_dir: string }>(API.settingsMediaDir());
}

export function useLanguageSetting() {
  return useSWR<{ language: string }>(API.settingsLanguage());
}

export interface LibraryWatchStatus {
  running: boolean;
  media_dir: string | null;
  last_event_at: number | null;
  last_error: string | null;
  pending: number;
}

export interface LibrarySyncStatus {
  sync: {
    state: string;
    last_started_at: string | null;
    last_finished_at: string | null;
    last_error: string | null;
    last_result: Record<string, unknown> | null;
  };
  watcher: LibraryWatchStatus;
}

export interface LibraryScrapeStatus {
  state: string;
  last_started_at: string | null;
  last_finished_at: string | null;
  last_error: string | null;
  last_result: {
    processed?: number;
    succeeded?: number;
    needs_review?: number;
    failed?: number;
    skipped?: number;
  } | null;
}

export interface LibraryOrganizeStatus {
  state: string;
  last_started_at: string | null;
  last_finished_at: string | null;
  last_error: string | null;
  last_result: {
    processed?: number;
    organized?: number;
    scraped?: number;
    needs_review?: number;
    failed?: number;
    skipped?: number;
  } | null;
}

export function useLibraryWatchSetting() {
  return useSWR<{ watch_library: boolean; watcher: LibraryWatchStatus }>(
    API.settingsLibraryWatch()
  );
}

export function useAutoOrganizeRootSetting() {
  return useSWR<{ auto_organize_root_videos: boolean }>(
    API.settingsAutoOrganizeRoot()
  );
}

export function useLibrarySyncStatus() {
  return useSWR<LibrarySyncStatus>(API.librarySyncStatus(), {
    refreshInterval: 5000,
  });
}

export function useLibraryScrapeStatus() {
  return useSWR<LibraryScrapeStatus>(API.libraryScrapeStatus(), {
    refreshInterval: 5000,
  });
}

export function useLibraryOrganizeStatus() {
  return useSWR<LibraryOrganizeStatus>(API.libraryOrganizeStatus(), {
    refreshInterval: 5000,
  });
}

// =====================
// Mutations
// =====================

export function useUpdateModel() {
  return useSWRMutation(
    API.settingsModel(),
    async (url: string, { arg: model }: { arg: string }) => {
      const res = await fetch(
        `${url}?model_name=${encodeURIComponent(model)}`,
        { method: "PUT" }
      );
      if (!res.ok) throw new Error("Failed to update model");
      return res.json();
    }
  );
}

export function useUpdateBaseUrl() {
  return useSWRMutation(
    API.settingsBaseUrl(),
    async (url: string, { arg: baseUrl }: { arg: string }) => {
      const res = await fetch(
        `${url}?base_url=${encodeURIComponent(baseUrl)}`,
        { method: "PUT" }
      );
      if (!res.ok) throw new Error("Failed to update base URL");
      return res.json();
    }
  );
}

export function useUpdateMediaDir() {
  return useSWRMutation(
    API.settingsMediaDir(),
    async (url: string, { arg: mediaDir }: { arg: string }) => {
      const res = await fetch(
        `${url}?media_dir=${encodeURIComponent(mediaDir)}`,
        { method: "PUT" }
      );
      if (!res.ok) throw new Error("Failed to update media dir");
      return res.json();
    }
  );
}

export function useUpdateLanguage() {
  return useSWRMutation(
    API.settingsLanguage(),
    async (url: string, { arg: language }: { arg: string }) => {
      const res = await fetch(`${url}?language=${language}`, {
        method: "PUT",
      });
      if (!res.ok) throw new Error("Failed to update language");
      return res.json();
    }
  );
}

export function useUpdateLibraryWatch() {
  return useSWRMutation(
    API.settingsLibraryWatch(),
    async (url: string, { arg: enabled }: { arg: boolean }) => {
      const res = await fetch(`${url}?enabled=${enabled}`, {
        method: "PUT",
      });
      if (!res.ok) throw new Error("Failed to update library watch setting");
      return res.json();
    }
  );
}

export function useUpdateAutoOrganizeRoot() {
  return useSWRMutation(
    API.settingsAutoOrganizeRoot(),
    async (url: string, { arg: enabled }: { arg: boolean }) => {
      const res = await fetch(`${url}?enabled=${enabled}`, {
        method: "PUT",
      });
      if (!res.ok) throw new Error("Failed to update auto organize setting");
      return res.json();
    }
  );
}

export function useTestApiKey() {
  return useSWRMutation(
    API.settingsTestApiKey(),
    async (url: string) => {
      const res = await fetch(url);
      if (!res.ok) throw new Error("Failed to test API key");
      return res.json();
    }
  );
}

export function useScanLibrary() {
  return useSWRMutation(
    API.systemScanLibrary(),
    async (url: string) => {
      const res = await fetch(url, { method: "POST" });
      if (!res.ok) throw new Error("Failed to start scan");
      return res.json();
    }
  );
}

export function useReconcileLibrary() {
  return useSWRMutation(
    API.libraryReconcile(),
    async (url: string) => {
      const res = await fetch(url, { method: "POST" });
      if (!res.ok) throw new Error("Failed to reconcile library");
      return res.json();
    }
  );
}

export function useScrapeLibrary() {
  return useSWRMutation(
    API.libraryScrapeBatch(),
    async (url: string) => {
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          scope: "unscraped",
          overwrite: false,
          write_nfo: true,
          download_artwork: true,
        }),
      });
      if (!res.ok) throw new Error("Failed to start metadata scrape");
      return res.json();
    }
  );
}

export function useOrganizeRootVideos() {
  return useSWRMutation(
    API.libraryOrganizeRoot(),
    async (url: string) => {
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          min_confidence: 85,
          rename_style: "preserve_stem",
          overwrite: false,
          write_nfo: true,
          download_artwork: true,
        }),
      });
      if (!res.ok) throw new Error("Failed to organize root videos");
      return res.json();
    }
  );
}

export function useCleanupMissingMovies() {
  return useSWRMutation(
    API.libraryCleanupMissing(),
    async (url: string) => {
      const res = await fetch(url, { method: "DELETE" });
      if (!res.ok) throw new Error("Failed to clean missing movies");
      return res.json();
    }
  );
}
