export interface FilmReference {
  title: string;
  year: number;
  type: string;
  reason: string;
}

export interface AnalysisData {
  thought_chain: string;
  micro_genre: string;
  influence_impact: string;
  ancestors: FilmReference[];
  descendants: FilmReference[];
  tmdb_metadata?: Record<string, unknown>;
}

export interface MovieDetail {
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
