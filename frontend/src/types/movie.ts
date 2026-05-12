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

export interface AudioTrack {
  codec?: string;
  language?: string;
  channels?: string;
}

export interface LibraryMovie {
  id: string;
  title: string;
  title_cn?: string;
  year: number;
  backdrop_path?: string;
  backdrop_local?: string;
  poster_local?: string;
  overview?: string;
  plot?: string;
  runtime?: number | null;
  countries?: string[] | null;
  audio_tracks?: AudioTrack[] | null;
  micro_genre?: string;
  genres?: string[];
  director?: string;
  library_status?: "available" | "missing";
  missing_since?: string | null;
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
  runtime?: number | null;
  countries?: string[] | null;
  audio_tracks?: AudioTrack[] | null;
  micro_genre: string;
  micro_genre_definition?: string;
  analysis_status: string;
  analysis_data?: AnalysisData | null;
  director?: string;
  media_path?: string | null;
  folder_path?: string | null;
  file_size?: number | null;
  file_mtime?: number | null;
  last_seen_at?: string | null;
  missing_since?: string | null;
  library_status?: "available" | "missing";
  metadata_updated_at?: string | null;
}
