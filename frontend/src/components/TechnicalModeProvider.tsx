"use client";

import { createContext, useContext, useMemo, useState } from "react";

interface TechnicalModeContextValue {
  isTechnical: boolean;
  setIsTechnical: (value: boolean) => void;
}

const STORAGE_KEY = "5x49:technical-mode";
const TechnicalModeContext = createContext<TechnicalModeContextValue | null>(null);

export function TechnicalModeProvider({ children }: { children: React.ReactNode }) {
  const [isTechnical, setIsTechnicalState] = useState(() => {
    if (typeof window === "undefined") return false;
    return window.localStorage.getItem(STORAGE_KEY) === "true";
  });

  const setIsTechnical = (value: boolean) => {
    setIsTechnicalState(value);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(STORAGE_KEY, String(value));
    }
  };

  const value = useMemo(() => ({ isTechnical, setIsTechnical }), [isTechnical]);

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
