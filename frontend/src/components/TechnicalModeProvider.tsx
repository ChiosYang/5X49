"use client";

import { createContext, useCallback, useContext, useMemo, useSyncExternalStore } from "react";

interface TechnicalModeContextValue {
  isTechnical: boolean;
  setIsTechnical: (value: boolean) => void;
}

const STORAGE_KEY = "5x49:technical-mode";
const STORAGE_CHANGE_EVENT = "5x49:technical-mode-change";
const TechnicalModeContext = createContext<TechnicalModeContextValue | null>(null);

function subscribeToTechnicalMode(onStoreChange: () => void) {
  window.addEventListener("storage", onStoreChange);
  window.addEventListener(STORAGE_CHANGE_EVENT, onStoreChange);
  return () => {
    window.removeEventListener("storage", onStoreChange);
    window.removeEventListener(STORAGE_CHANGE_EVENT, onStoreChange);
  };
}

function getTechnicalModeSnapshot() {
  return window.localStorage.getItem(STORAGE_KEY) === "true";
}

function getServerTechnicalModeSnapshot() {
  return false;
}

export function TechnicalModeProvider({ children }: { children: React.ReactNode }) {
  const isTechnical = useSyncExternalStore(
    subscribeToTechnicalMode,
    getTechnicalModeSnapshot,
    getServerTechnicalModeSnapshot,
  );

  const setIsTechnical = useCallback((value: boolean) => {
    window.localStorage.setItem(STORAGE_KEY, String(value));
    window.dispatchEvent(new Event(STORAGE_CHANGE_EVENT));
  }, []);

  const value = useMemo(() => ({ isTechnical, setIsTechnical }), [isTechnical, setIsTechnical]);

  return (
    <TechnicalModeContext.Provider value={value}>
      {children}
    </TechnicalModeContext.Provider>
  );
}

export function useTechnicalMode() {
  const value = useContext(TechnicalModeContext);
  if (!value) {
    throw new Error("useTechnicalMode must be used inside TechnicalModeProvider");
  }
  return value;
}
