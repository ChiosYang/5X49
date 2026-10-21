"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { createSettingsScanGuard } from "@/lib/settings-scan-guard";

interface SettingsSession {
  rootsDraft: string[] | null;
  setRootsDraft: (value: string[] | null) => void;
  rootsSaving: boolean;
  setRootsSaving: (value: boolean) => void;
}
const Session = createContext<SettingsSession | null>(null);

export function SettingsSessionProvider({ children }: { children: ReactNode }) {
  const [rootsDraft, updateDraft] = useState<string[] | null>(null);
  const [rootsSaving, updateSaving] = useState(false);
  const [guard] = useState(createSettingsScanGuard);
  useEffect(() => { guard.acquire(); return () => guard.release(); }, [guard]);
  const setRootsDraft = (value: string[] | null) => { guard.setDraft(value !== null); updateDraft(value); };
  const setRootsSaving = (value: boolean) => { guard.setSaving(value); updateSaving(value); };
  return <Session.Provider value={{ rootsDraft, setRootsDraft, rootsSaving, setRootsSaving }}>{children}</Session.Provider>;
}

export function useSettingsSession() {
  const session = useContext(Session);
  if (!session) throw new Error("SettingsSessionProvider is required");
  return session;
}
