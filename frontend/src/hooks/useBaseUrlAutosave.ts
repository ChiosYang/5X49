"use client";

import { useEffect, useState, useSyncExternalStore } from "react";
import { mutate as updateCache } from "swr";
import { API } from "@/lib/api";
import { useBaseUrl, writeBaseUrl } from "./useSettings";
import { createBaseUrlAutosave, type BaseUrlSaveState } from "@/lib/settings-autosave";
import { createAutosaveSessionRegistry } from "@/lib/settings-autosave-session";

const sessions = createAutosaveSessionRegistry<string, Exclude<BaseUrlSaveState["notice"], "saved" | null>, { base_url: string }>();

export function useBaseUrlAutosave() {
  const { data } = useBaseUrl();
  const [autosave] = useState(() => sessions.get(() => ({
    initial: data ?? null, value: result => result.base_url, create: createBaseUrlAutosave,
    write: async value => {
      const result = await writeBaseUrl(value);
      const saved = typeof result.base_url === "string" ? result.base_url : value;
      await updateCache(API.settingsBaseUrl(), { base_url: saved }, false);
      return { base_url: saved };
    },
  }), typeof window !== "undefined"));
  const state = useSyncExternalStore(autosave.subscribe, autosave.getSnapshot, autosave.getSnapshot);
  useEffect(() => { if (data) autosave.syncSaved(data); }, [autosave, data]);
  return { autosave, state, data };
}
