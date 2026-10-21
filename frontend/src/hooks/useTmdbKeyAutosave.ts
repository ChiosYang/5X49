"use client";

import { useState, useSyncExternalStore } from "react";
import { mutate as updateCache } from "swr";
import { API } from "@/lib/api";
import { useTmdbSettings, writeTmdbKey } from "./useSettings";
import { createTmdbKeyAutosave } from "@/lib/settings-autosave";
import { createAutosaveSessionRegistry } from "@/lib/settings-autosave-session";

// The private session retains only the latest submitted key for serialization.
// SWR and the public API receive configuration metadata only, never the key.
const sessions = createAutosaveSessionRegistry<string, "invalidTmdbKey" | "tmdbSaveFailed", string>();

export function useTmdbKeyAutosave() {
  const { data, error } = useTmdbSettings();
  const [autosave] = useState(() => sessions.get(() => ({
    initial: null, value: result => result, create: createTmdbKeyAutosave, retainFailedDraft: true,
    write: async value => {
      const result = await writeTmdbKey(value);
      await updateCache(API.settingsTmdb(), { configured: result.configured, source: result.source }, false);
      return value;
    },
  }), typeof window !== "undefined"));
  const state = useSyncExternalStore(autosave.subscribe, autosave.getSnapshot, autosave.getSnapshot);
  return { autosave, state, data, error };
}
