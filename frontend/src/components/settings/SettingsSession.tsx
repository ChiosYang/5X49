"use client";

import { createContext, useContext, useState, type Dispatch, type ReactNode, type SetStateAction } from "react";

interface SettingsSession {
  rootsDraft: string[] | null;
  setRootsDraft: Dispatch<SetStateAction<string[] | null>>;
  rootsSaving: boolean;
  setRootsSaving: Dispatch<SetStateAction<boolean>>;
}
const Session = createContext<SettingsSession | null>(null);

export function SettingsSessionProvider({ children }: { children: ReactNode }) {
  const [rootsDraft, setRootsDraft] = useState<string[] | null>(null);
  const [rootsSaving, setRootsSaving] = useState(false);
  return <Session.Provider value={{ rootsDraft, setRootsDraft, rootsSaving, setRootsSaving }}>{children}</Session.Provider>;
}

export function useSettingsSession() {
  const session = useContext(Session);
  if (!session) throw new Error("SettingsSessionProvider is required");
  return session;
}
