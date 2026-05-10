"use client";

import { useSWRConfig } from "swr";
import { API } from "@/lib/api";
import { useAnalyzeMovie, useMovie } from "@/hooks/useMovie";
import type { MovieDetail } from "@/types/movie";
import GenealogySection from "../../components/GenealogySection";

interface MovieAnalysisSectionProps {
  movieId: string;
  initialMovie: MovieDetail;
}

export default function MovieAnalysisSection({ movieId, initialMovie }: MovieAnalysisSectionProps) {
  const { mutate } = useSWRConfig();
  const { data: movie = initialMovie } = useMovie(movieId, initialMovie);
  const { trigger: analyze, isMutating: analyzing } = useAnalyzeMovie(movieId);

  const triggerAnalysis = async () => {
    if (!movieId || analyzing) return;
    await analyze();
    await mutate(API.libraryMovie(movieId));
  };

  return (
    <GenealogySection
      analysisData={movie.analysis_data || null}
      analysisStatus={movie.analysis_status}
      onTriggerAnalysis={triggerAnalysis}
      analyzing={analyzing}
    />
  );
}
