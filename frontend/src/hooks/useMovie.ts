import useSWR from "swr";
import useSWRMutation from "swr/mutation";
import { API } from "@/lib/api";
import type { MovieDetail } from "@/types/movie";

export function useMovie(id: string, fallbackData?: MovieDetail) {
  return useSWR<MovieDetail>(id ? API.libraryMovie(id) : null, {
    fallbackData,
    // Poll every 5s while analysis is processing, stop otherwise
    refreshInterval: (data?: MovieDetail) => {
      if (data?.analysis_status === "processing") return 5000;
      return 0;
    },
  });
}

export function useAnalyzeMovie(id: string) {
  return useSWRMutation(
    API.libraryMovie(id),
    async () => {
      const res = await fetch(API.libraryAnalyze(id), { method: "POST" });
      if (!res.ok) throw new Error("Failed to trigger analysis");
      return res.json();
    }
  );
}
