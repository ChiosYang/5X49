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

export interface ExternalScore {
  source: string;
  label: string;
  kind: "rating" | "rank";
  value?: number;
  scale?: number;
  rank?: number;
  previous_rank?: number | null;
  votes?: number | null;
  list_name?: string;
  edition?: string;
  url?: string;
  fetched_at?: string;
  expires_at?: string;
  matched_by?: string;
  confidence?: number;
}

export interface LibraryMovie {
  id: string;
  title: string;
  title_cn?: string;
  year: number;
  backdrop_path?: string;
  backdrop_local?: string;
  poster_local?: string;
  backdrop_thumb_local?: string | null;
  poster_thumb_local?: string | null;
  overview?: string;
  plot?: string;
  runtime?: number | null;
  countries?: string[] | null;
  audio_tracks?: AudioTrack[] | null;
  video_width?: number | null;
  video_height?: number | null;
  video_codec?: string | null;
  video_bitrate?: number | null;
  video_duration?: number | null;
  video_fps?: number | null;
  video_dynamic_range?: string | null;
  video_bit_depth?: number | null;
  added_at?: string | null;
  micro_genre?: string;
  genres?: string[];
  director?: string;
  library_status?: "available" | "missing" | "ignored";
  missing_since?: string | null;
  metadata_source?: string | null;
  metadata_updated_at?: string | null;
  scrape_status?: "pending" | "matched" | "needs_review" | "failed";
  scrape_error?: string | null;
  scraped_at?: string | null;
  tmdb_confidence?: number | null;
  external_scores?: ExternalScore[] | null;
  external_scores_updated_at?: string | null;
  external_scores_error?: string | null;
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
  backdrop_thumb_local?: string | null;
  poster_thumb_local?: string | null;
  overview?: string;
  plot?: string;
  runtime?: number | null;
  countries?: string[] | null;
  audio_tracks?: AudioTrack[] | null;
  video_width?: number | null;
  video_height?: number | null;
  video_codec?: string | null;
  video_bitrate?: number | null;
  video_duration?: number | null;
  video_fps?: number | null;
  video_dynamic_range?: string | null;
  video_bit_depth?: number | null;
  micro_genre: string;
  micro_genre_definition?: string;
  analysis_status: string;
  analysis_data?: AnalysisData | null;
  director?: string;
  media_path?: string | null;
  folder_path?: string | null;
  file_size?: number | null;
  file_mtime?: number | null;
  added_at?: string | null;
  last_seen_at?: string | null;
  missing_since?: string | null;
  library_status?: "available" | "missing" | "ignored";
  metadata_updated_at?: string | null;
  metadata_source?: string | null;
  scrape_status?: "pending" | "matched" | "needs_review" | "failed";
  scrape_error?: string | null;
  scraped_at?: string | null;
  tmdb_confidence?: number | null;
  external_scores?: ExternalScore[] | null;
  external_scores_updated_at?: string | null;
  external_scores_error?: string | null;
}

export interface MetadataSearchResult {
  tmdb_id: number;
  title: string;
  original_title?: string | null;
  year: number;
  overview: string;
  poster_path?: string | null;
  backdrop_path?: string | null;
  popularity: number;
  score: number;
}

export interface ArtworkImage {
  file_path: string;
  url: string;
  thumbnail_url: string;
  width: number;
  height: number;
  aspect_ratio: number;
  language?: string | null;
  vote_average: number;
  vote_count: number;
}

export interface MovieArtworkOptions {
  movie_id: string;
  tmdb_id: number;
  posters: ArtworkImage[];
  backdrops: ArtworkImage[];
  current_poster_path?: string | null;
  current_backdrop_path?: string | null;
}

export interface ArtworkSelection {
  poster_path?: string | null;
  backdrop_path?: string | null;
}

export interface ScrapeResult {
  status: "success" | "needs_review" | "failed" | "skipped";
  movie_id: string;
  message: string;
  movie?: MovieDetail;
  candidates: MetadataSearchResult[];
}

export interface EventRecord {
  id: string;
  aggregate_type: "movie" | "library" | "file" | string;
  aggregate_id?: string | null;
  type: string;
  actor_type: string;
  actor_id?: string | null;
  command_id?: string | null;
  correlation_id?: string | null;
  causation_id?: string | null;
  payload?: Record<string, unknown> | null;
  context?: Record<string, unknown> | null;
  schema_version: number;
  occurred_at: string;
}

export interface OperationDryRunCheck {
  status: "safe" | "partial" | "unsafe" | "unknown" | "not_applicable" | string;
  can: boolean;
  message: string;
  event_id?: string | null;
  details: Record<string, unknown>;
  missing_payload: string[];
  unsafe_actions: string[];
}

export interface OperationDryRunReport {
  dry_run: boolean;
  operation_id?: string | null;
  correlation_id?: string | null;
  command_id?: string | null;
  status: "safe" | "partial" | "unsafe" | "unknown" | string;
  events_analyzed: number;
  event_types: Record<string, number>;
  can_restore_poster: boolean;
  can_trace_nfo_writer: boolean;
  can_reverse_root_move: boolean;
  can_list_scrape_side_effects: boolean;
  checks: Record<string, OperationDryRunCheck>;
  side_effects: Array<Record<string, unknown>>;
  recoverable_fields: Array<Record<string, unknown>>;
  missing_payload: Array<Record<string, unknown>>;
  unsafe_actions: Array<Record<string, unknown>>;
  events: Array<Record<string, unknown>>;
}

export type OperationRestoreAction = "restore_poster" | "restore_nfo" | "reverse_root_move";

export interface OperationRestoreReport {
  status: "restored" | "skipped" | string;
  operation_id?: string | null;
  correlation_id?: string | null;
  command_id?: string | null;
  restore_command_id?: string | null;
  restore_correlation_id?: string | null;
  actions_requested: OperationRestoreAction[];
  restored: Array<Record<string, unknown>>;
  skipped: Array<Record<string, unknown>>;
  dry_run: OperationDryRunReport;
}

export interface RootVideo {
  path: string;
  filename: string;
  size: number;
  mtime: number;
  stable: boolean;
  parsed_title: string;
  parsed_year: number;
  status: "needs_organize" | "waiting_for_stability";
}

export type JobStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled" | "cancelling";

export interface JobProgress {
  stage?: string;
  current?: number;
  total?: number;
  message?: string;
  counts?: Record<string, number>;
}

export interface Job {
  id: string;
  type: string;
  status: JobStatus;
  payload?: Record<string, unknown> | null;
  progress?: JobProgress | null;
  result?: Record<string, unknown> | null;
  result_summary?: string | null;
  error?: string | null;
  attempts: number;
  max_attempts: number;
  priority?: number;
  dedupe_key?: string | null;
  cancel_requested?: boolean;
  created_at: string;
  updated_at: string;
  started_at?: string | null;
  finished_at?: string | null;
}

export interface JobAccepted {
  status: "queued";
  message: string;
  job_id: string;
  job: Job;
}
