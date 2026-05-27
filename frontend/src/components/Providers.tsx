"use client";

import { SWRConfig } from "swr";
import { fetcher } from "@/lib/fetcher";
import { TechnicalModeProvider } from "./TechnicalModeProvider";

export default function Providers({ children }: { children: React.ReactNode }) {
  return (
    <SWRConfig
      value={{
        fetcher,
        revalidateOnFocus: false,
        dedupingInterval: 5000,
        errorRetryCount: 1,
      }}
    >
      <TechnicalModeProvider>
        {children}
      </TechnicalModeProvider>
    </SWRConfig>
  );
}
