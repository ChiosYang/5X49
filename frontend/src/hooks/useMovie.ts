import useSWR from "swr";
import useSWRMutation from "swr/mutation";
import { API } from "@/lib/api";

interface FilmReference {
  title: string;
  year: number;
  type: string;
  reason: string;
}

interface AnalysisData {
  thought_chain: string;
  micro_genre: string;
  influence_impact: string;
  ancestors: FilmReference[];
  descendants: FilmReference[];
  tmdb_metadata?: Record<string, unknown>;
}

interface MovieDetail {
  id: string;
  title: string;
  title_cn?: string;
  year: number;
  backdrop_path?: string;
  backdrop_local?: string;
  poster_path?: string;
  poster_local?: string;
  overview?: string;
  plot?: string;
  micro_genre: string;
  micro_genre_definition?: string;
  analysis_status: string;
  analysis_data?: AnalysisData | null;
  director?: string;
}

export function useMovie(id: string) {
  return useSWR<MovieDetail>(id ? API.libraryMovie(id) : null, {
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
