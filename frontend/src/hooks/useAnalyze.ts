import useSWRMutation from "swr/mutation";
import { API } from "@/lib/api";

interface FilmNode {
  title: string;
  year: number;
  type?: string;
  reason: string;
}

interface GenealogyData {
  thought_chain: string;
  micro_genre: string;
  influence_impact: string;
  ancestors: FilmNode[];
  descendants: FilmNode[];
  tmdb_metadata: {
    title: string;
    year: number;
    overview: string;
    genres: string[];
    keywords: string[];
  };
}

export function useAnalyze() {
  return useSWRMutation<GenealogyData, Error, string, string>(
    "analyze",
    async (_key: string, { arg: filmName }: { arg: string }) => {
      const res = await fetch(API.analyze(filmName));
      if (!res.ok) throw new Error("Film not found or analysis failed");
      return res.json();
    }
  );
}
