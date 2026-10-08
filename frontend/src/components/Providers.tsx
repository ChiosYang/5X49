"use client";

import { SWRConfig } from "swr";
import { fetcher } from "@/lib/fetcher";
import FilmReturnRestoration from "./FilmReturnRestoration";
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
        <FilmReturnRestoration />
        {children}
      </TechnicalModeProvider>
    </SWRConfig>
  );
}
