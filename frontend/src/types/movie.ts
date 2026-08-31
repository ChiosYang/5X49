export interface AudioTrack {
  codec?: string;
  language?: string;
  channels?: string;
}

export interface ExternalScore {
  source: string;
  label: string;
  kind: "rating" | "rank";
  value?: number | null;
  scale?: number | null;
  rank?: number | null;
  previous_rank?: number | null;
  votes?: number | null;
  list_name?: string;
  edition?: string;
  source_uri?: string | null;
  fetched_at: string;
  expires_at?: string | null;
  matched_by?: string | null;
  confidence?: number | null;
}

export interface FilmProfileState {
  film_id: string;
  watched: boolean;
  watched_at?: string | null;
  rating?: number | null;
  favorite: boolean;
  notes?: string | null;
  updated_at?: string | null;
}

export interface FilmProfileStateUpdate {
  watched?: boolean | null;
  watched_at?: string | null;
  rating?: number | null;
  favorite?: boolean | null;
  notes?: string | null;
}

export interface ResolvedSource {
  source_kind?: string | null;
  observed_at?: string | null;
  policy_version: string;
  conflicted: boolean;
}

export interface LibraryEdition {
  id: string;
  film_id: string;
  display_name?: string | null;
  source_type: string;
  status: "available" | "missing" | "ignored";
  added_at?: string | null;
  last_seen_at?: string | null;
  missing_since?: string | null;
  metadata: {
    source?: string | null;
    updated_at?: string | null;
    scrape_status: "pending" | "matched" | "needs_review" | "failed";
    scrape_error?: string | null;
    scraped_at?: string | null;
    match_confidence?: number | null;
  };
  artwork: {
    poster_local?: string | null;
    backdrop_local?: string | null;
    poster_thumb_local?: string | null;
    backdrop_thumb_local?: string | null;
    poster_provider?: string | null;
    backdrop_provider?: string | null;
  };
  video?: {
    file_name?: string | null;
    file_size?: number | null;
    file_mtime?: number | null;
    width?: number | null;
    height?: number | null;
    codec?: string | null;
    bitrate?: number | null;
    duration_seconds?: number | null;
    fps?: number | null;
    dynamic_range?: string | null;
    bit_depth?: number | null;
    audio_tracks?: AudioTrack[] | null;
  } | null;
}

export interface LibraryFilmSummary {
  id: string;
  title: string;
  original_title?: string | null;
  year?: number | null;
  release_date?: string | null;
  runtime_minutes?: number | null;
  overview?: string | null;
  identities: { tmdb?: string | null; imdb?: string | null };
  countries: string[];
  genres: string[];
  directors: string[];
  micro_genre?: string | null;
  primary_item: LibraryEdition;
  profile_state: FilmProfileState;
  external_scores: ExternalScore[];
  analysis: {
    status: "pending" | "queued" | "running" | "succeeded" | "failed" | "cancelled";
    latest_run_id?: string | null;
    summary?: string | null;
  };
  resolved_sources?: Record<string, ResolvedSource>;
}

export interface LibraryFilmDetail extends LibraryFilmSummary {
  editions: LibraryEdition[];
}

export interface FilmAnalysisTarget {
  entity_id: string;
  entity_type?: "film" | "person" | "concept";
  display_name?: string;
  release_year?: number | null;
  kind?: string;
}

export interface FilmAnalysisRelation {
  id: string;
  predicate: string;
  direction: "subject_to_target" | "target_to_subject";
  target: FilmAnalysisTarget;
  qualifiers: Record<string, unknown>;
  rationale?: string | null;
  review_status: "proposed" | "accepted" | "rejected";
  evidence_ids: string[];
}

export interface FilmAnalysisView {
  film_id: string;
  status: "queued" | "running" | "succeeded" | "failed" | "cancelled";
  run: {
    id: string;
    provider: string;
    model: string;
    created_at: string;
    finished_at?: string | null;
    error_code?: string | null;
  };
  summary?: string | null;
  relations: FilmAnalysisRelation[];
  evidence: Array<{
    id: string;
    source_title: string;
    source_uri: string;
    publisher?: string | null;
    claim: string;
    retrieved_at: string;
    stance: "supports" | "contradicts" | "context";
  }>;
  reviews: Array<{
    id: string;
    predicate?: string | null;
    candidate_kind: string;
    reason_code: string;
    candidate_summary: Record<string, unknown>;
    status: "open" | "resolved" | "dismissed";
  }>;
}

export interface GraphNode {
  id: string;
  entity_type: "film" | "person" | "concept";
  display_label: string;
  release_year?: number | null;
  concept_kind?: string | null;
  in_library: boolean;
}

export interface GraphEdge {
  id: string;
  edge_kind: "credit" | "assertion";
  subject_id: string;
  object_id: string;
  relation: string;
  direction: "subject_to_object";
  review_status: "accepted";
  source_kinds: string[];
  active_evidence_count: number;
  conflicted: boolean;
}

export interface FilmGraphView {
  root: GraphNode;
  nodes: GraphNode[];
  edges: GraphEdge[];
  truncated: boolean;
  visibility_policy: "graph-visibility.v1" | "graph-visibility.v2";
  projection_version: string;
}

export interface WatchHistoryEntry {
  film: LibraryFilmSummary;
  viewing: {
    id: string;
    film_id: string;
    watched_at?: string | null;
    watched_at_precision: "timestamp" | "date" | "year" | "unknown";
    source: string;
  };
  profile_state: FilmProfileState;
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

export interface FilmArtworkOptions {
  film_id: string;
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

export interface FilmArtworkUpdateResponse {
  status: "success";
  film_id: string;
  film: LibraryFilmDetail;
  poster_path?: string | null;
  backdrop_path?: string | null;
}

export interface ScrapeResult {
  status: "success" | "needs_review" | "failed" | "skipped";
  film_id: string;
  message: string;
  film?: LibraryFilmDetail;
  candidates: MetadataSearchResult[];
}

export interface EventRecord {
  id: string;
  aggregate_type: "film" | "library_item" | "viewing" | "assertion" | "analysis_run" | "job" | string;
  aggregate_id?: string | null;
  film_id?: string | null;
  display_title?: string | null;
  operation_snapshot_id?: string | null;
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

export interface OperationSnapshotPreview {
  snapshot_id: string;
  aggregate_type: "film" | "library_item";
  aggregate_id: string;
  operation_kind: string;
  status: "available" | "restored" | "expired";
  before: Record<string, unknown>;
  after: Record<string, unknown>;
  current_matches_after: boolean;
  confirmation_token?: string | null;
}

export interface OperationRestoreResult {
  status: "restored";
  snapshot_id: string;
  aggregate_type: "film" | "library_item";
  aggregate_id: string;
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

export interface OrganizationCandidate {
  source_path: string;
  source_location: "root" | "legacy_inbox";
  filename: string;
  size: number;
  mtime: number;
  stable: boolean;
  parsed_title: string;
  parsed_year: number;
  status: "needs_organize" | "waiting_for_stability";
}

export interface OrganizationPreview {
  source: {
    source_path: string;
    filename: string;
    size: number;
    source_location: "root" | "legacy_inbox";
  };
  match: MetadataSearchResult;
  target: {
    folder_name: string;
    video_name: string;
  };
  rename_style: "preserve_stem" | "title_year";
  sidecars: Array<{
    source_name: string;
    target_name: string;
    conflict: boolean;
  }>;
  post_actions: {
    write_nfo: boolean;
    download_artwork: boolean;
  };
  conflicts: Array<{
    kind: "video" | "sidecar";
    name: string;
  }>;
  can_confirm: boolean;
  confirmation_token: string;
}

export type WorkflowStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled";

export interface WorkflowProgress {
  stage?: string;
  current?: number;
  total?: number;
  message?: string;
  counts?: Record<string, number>;
}

export interface WorkflowStepView {
  id: string;
  step_key: string;
  position: number;
  status: "pending" | "queued" | "running" | "succeeded" | "failed" | "cancelled";
  attempt: number;
  max_attempts: number;
  result_summary?: string | null;
  compensation_status: "none" | "pending" | "running" | "succeeded" | "failed";
  started_at?: string | null;
  finished_at?: string | null;
}

export interface WorkflowRunView {
  id: string;
  type: string;
  definition_version: string;
  subject_type: "library" | "film" | "library_item" | "system";
  subject_id?: string | null;
  status: WorkflowStatus;
  current_step?: string | null;
  progress?: WorkflowProgress | null;
  result_summary?: string | null;
  error_code?: string | null;
  error_message?: string | null;
  cancel_requested?: boolean;
  steps: WorkflowStepView[];
  created_at: string;
  updated_at: string;
  started_at?: string | null;
  finished_at?: string | null;
}

export interface WorkflowAccepted {
  status: "queued";
  message: string;
  workflow_id: string;
  workflow: WorkflowRunView;
}
