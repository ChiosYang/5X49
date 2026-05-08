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
