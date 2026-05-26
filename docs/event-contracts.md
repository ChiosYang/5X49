# Library Event Contracts

This document freezes the current v1 event semantics for the library event
system. The system is still a hybrid model: the `Movie` table remains the
current-state table, while persisted events provide audit history, partial
projection support, operation dry-runs, and compensation actions.

## Envelope

Every persisted event is an `EventRecord` row in the `events` table.

- `id`: Event ID, formatted as `evt_<uuid-hex>`.
- `aggregate_type`: Aggregate category. Current values include `movie`, `library`, and `file`.
- `aggregate_id`: Aggregate identifier. Movie events use the movie ID; file events usually use a path.
- `type`: Semantic event type.
- `actor_type`: Actor category. Current default is `system`.
- `actor_id`: Optional actor identifier.
- `command_id`: Optional command identifier for one command execution.
- `correlation_id`: Optional operation identifier used to group related events.
- `causation_id`: Optional source event ID, mainly used by compensation events.
- `payload`: Event-specific v1 payload.
- `context`: Additional metadata such as `{ "operation": "scrape_movie" }`.
- `schema_version`: Payload schema version. Current code defaults to `1`.
- `occurred_at`: UTC ISO timestamp.

## Compatibility Rules

- Current persisted events are treated as `schema_version=1` when the field is absent or defaulted.
- Events missing required replay payload must be reported as `unsupported`; replay must not invent state.
- Events missing optional display or trace payload can be tolerated with `ignore`.
- Initialization facts that can be derived from the current `Movie` table should be handled by a later `backfill` with `source=backfill`.
- Runtime upcasters are not implemented yet. `upcast` is reserved for future schema migrations.
- File side effects are not blindly replayed. They can only be audited or compensated when the event has enough payload.
- Timeline state dry-runs replay only projectable events into an in-memory target state. File side-effect events are excluded from state replay and are used only for restore-preview backup and path checks.

## Projectability

Projection rules currently implemented in `movie_projection.py`:

- `MovieDiscovered`
- `MovieFileObserved`
- `MovieMetadataParsedFromNfo`
- `MovieIgnored`
- `MovieMarkedMissing`
- `MovieRestored`
- `MovieStateBackfilled`
- `MetadataMatched`
- `ArtworkSelected`
- `MovieStateRestored`
- `MetadataRestored`
- `ArtworkSelectionRestored`
- `RootVideoOrganizationReverted`
- `AnalysisStarted`
- `AnalysisCompleted`
- `AnalysisFailed`
- `ExternalScoresRefreshed`

`movie_rebuild.py` dry-run uses the same projectable event set for `base=current`
and `base=empty`. `base=empty` still needs a usable `MovieDiscovered` event
before later per-movie events can be applied. All other events are audit-only,
side-effect-only, or not yet projectable unless this document says otherwise.

## Scan Events

| Event | Meaning | Category | Projector status | v1 payload | Compatibility |
| --- | --- | --- | --- | --- | --- |
| `MovieDiscovered` | A new movie record was created from scanning, scraping, organizing, or backfill. | domain | Projectable. It can create initial Movie state when enough payload exists. | `movie_id` or `id`, `title`, `year`, plus available scan fields such as `media_path`, `folder_path`, `video_file`, `file_size`, `file_mtime`, `last_seen_at`, `library_status`, `metadata_source`, `scrape_status`, `tmdb_id`, `imdb_id`, video fields, and NFO signature fields. | Missing `movie_id`/`id`, `title`, or `year` is `unsupported` for empty replay. Optional scan fields can be ignored. |
| `MovieFileObserved` | A known local file changed in observable file or video fields. Emitted only when key fields change. | domain | Projectable. Updates file, video, last-seen, and NFO signature fields. | `movie_id`, `changed_fields`, `previous`, `current`, and current file/video fields such as `media_path`, `folder_path`, `video_file`, `file_size`, `file_mtime`, `video_width`, `video_height`, `video_codec`, `video_duration`. | Missing movie state is `unsupported`. Missing optional fields can be ignored. |
| `MovieMetadataParsedFromNfo` | A known NFO signature changed during scan or refresh. | domain | Projectable. Updates NFO metadata and signature fields. | `movie_id`, `changed_fields`, `previous`, `current`, NFO metadata fields, and NFO signature fields such as `nfo_file`, `nfo_path`, `nfo_size`, `nfo_mtime`, `nfo_fingerprint`. | Missing current/top-level NFO payload is skipped during dry-run. |
| `MovieFolderScanned` | A folder scan completed. This is now treated as technical/audit history and is no longer emitted for successful no-change scans by default. | system/audit | Not projectable. | `folder_path` or `media_path`, optional scan result fields. | Old events can be ignored during replay. |
| `MovieMarkedMissing` | A known movie was not observed and is now marked missing. | domain | Synchronously projected: sets `library_status=missing` unless ignored/reverted, and sets `missing_since`. | `movie_id`, `missing_since`, optional `path` or `seen_at`. | Missing `missing_since` keeps status projectable but weakens audit detail. |
| `MovieRestored` | A missing movie was observed again and is now available. | domain | Synchronously projected: sets `library_status=available` and clears `missing_since`, unless ignored. | Current scan payload for the restored movie. | Missing optional scan fields can be ignored. |
| `MovieIgnored` | A movie was intentionally hidden from the normal library. | domain | Synchronously projected: sets `library_status=ignored` and clears `missing_since`. | `movie_id`, optional `title`, `year`. | Missing optional title/year can be ignored. |
| `MovieStateBackfilled` | A migration snapshot of the current Movie row was appended to improve replay coverage for older incomplete events. | migration | Projectable. Applies the payload `current` fields to the Movie projection. | `movie_id`, `current`, `source_event_ids`, `source_event_types`, `reason`, `source="backfill"`; context includes `source="backfill"` and `backfill_kind="movie_state"`. | This is not a real historical scrape/artwork action and must not be used to infer exact state before the migration timestamp. Missing `current` is skipped. |

## Metadata Match Events

| Event | Meaning | Category | Projector status | v1 payload | Compatibility |
| --- | --- | --- | --- | --- | --- |
| `MetadataMatchSuggested` | Scrape found candidates but requires review before writing metadata. | domain | Not projectable. | `movie_id`, `reason`, `candidates`. | Missing candidates still allows audit display; replay ignores it. |
| `MetadataMatched` | A movie was matched to external metadata and metadata fields were updated. | domain | Projectable. The scrape command appends this event and uses the projector for Movie metadata state. | `movie_id`, `title`, `tmdb_id`, `confidence` or `score`, `changed_fields`, `previous`, `current`. | Missing `current` and top-level metadata fields is skipped during dry-run. |
| `MovieStateRestored` | Movie fields were restored to a historical timeline target. | compensation | Synchronously projected: applies `restored_fields` to the `Movie` row. | `movie_id`, `target`, `restored_fields`, `conflicts`, `skipped_fields`, `before`, `after`, `preview_status`; `causation_id` should point to the selected `before_event_id` when available. | Missing `restored_fields` is `unsupported` for projection. |
| `MetadataRestored` | Metadata fields were restored as compensation for a previous metadata match. | compensation | Synchronously projected: applies `restored_fields` to the `Movie` row. | `restored_fields`, `skipped_fields`, source operation identifiers; `causation_id` should point to the source `MetadataMatched`. | Missing `restored_fields` is `unsupported` for projection. |
| `MetadataScrapeFailed` | A scrape attempt failed. | system/audit | Not projectable. | `movie_id`, `message` or `reason`, optional candidate/source context. | Replay ignores it. |

## Artwork Events

| Event | Meaning | Category | Projector status | v1 payload | Compatibility |
| --- | --- | --- | --- | --- | --- |
| `ArtworkDownloaded` | Poster or backdrop file was written to disk. | side-effect | Not projectable. Operation dry-run can restore file content when `backup_path` exists. | `movie_id`, `asset_type` (`poster` or `backdrop`), `destination`, `source_url` or TMDB path, `before`, `after`, optional `backup_path`. | Missing `backup_path` means file restore is unavailable, not a replay error. |
| `ArtworkSelected` | Movie artwork selection fields were changed. | domain | Projectable. The artwork selection command appends this event and uses the projector for Movie artwork state. | `movie_id`, selected poster/backdrop fields, `changed_fields`, `previous`, `current`. | Missing `current` and top-level artwork fields is skipped during dry-run. |
| `ArtworkSelectionRestored` | Artwork selection fields were restored as compensation. | compensation | Synchronously projected: applies `restored_fields` to the `Movie` row. | `restored_fields`, `skipped_fields`; `causation_id` should point to the source `ArtworkSelected`. | Missing `restored_fields` is `unsupported` for projection. |
| `ArtworkRestored` | Poster or backdrop file content was restored from backup. | compensation | Not projectable; file compensation only. | `movie_id`, `asset_type`, `source_path` or `backup_path`, `destination`, optional file snapshots; `causation_id` should point to `ArtworkDownloaded`. | Missing backup/source path means file restore cannot be repeated. |
| `MovieFileSnapshotBackfilled` | A migration snapshot recorded current poster, backdrop, or NFO file metadata. | migration/audit | Not projectable. | `movie_id`, `file_type`, `path`, `exists`, `size`, `mtime`, `restore_available=false`, `source="backfill"`; context includes `backfill_kind="file_snapshot"`. | This records current file facts only. It does not create a backup and does not make file restore available. |

## NFO Events

| Event | Meaning | Category | Projector status | v1 payload | Compatibility |
| --- | --- | --- | --- | --- | --- |
| `NfoWritten` | NFO metadata or artwork references were written to disk. | side-effect | Not projectable. Operation dry-run can restore file content when `backup_path` exists. | `movie_id`, `action`, `path`, `before`, `after`, optional `backup_path`. | Missing `backup_path` means file restore is unavailable. Missing `path` is `unsupported` for file compensation. |
| `NfoRestored` | NFO file content was restored from backup. | compensation | Not projectable; file compensation only. | `movie_id`, `path`, `backup_path` or `source_path`, optional file snapshots; `causation_id` should point to `NfoWritten`. | Missing source/backup path means the event is audit-only. |

## Root Video Events

| Event | Meaning | Category | Projector status | v1 payload | Compatibility |
| --- | --- | --- | --- | --- | --- |
| `RootVideoOrganizationNeedsReview` | A root video organization candidate requires manual review. | system/audit | Not projectable. | `path`, `reason`, `candidate`, optional `min_confidence`. | Replay ignores it. |
| `RootVideoMoved` | A root-level video file was moved into a movie folder. | side-effect | Not projectable. Operation dry-run can reverse when source/target snapshots are complete and paths are safe. | `source_path`, `target_path`, `source`, `target`, optional movie/candidate context. | Missing source or target path is `unsupported` for reverse move. |
| `RootVideoMoveReversed` | A root video move was reversed. | compensation | Not projectable; file compensation only. | `source_path`, `target_path`, optional file snapshots; `causation_id` should point to `RootVideoMoved`. | Missing paths makes it audit-only. |
| `RootVideoOrganized` | Root video organization completed and produced a library movie. | side-effect | Not directly projectable; used as operation summary. | `movie_id`, `source_path`, `target_path`, `source`, `target`, selected TMDB candidate fields. | Replay should not move files from this event. |
| `RootVideoOrganizationReverted` | A movie record created by root-video organization was reverted after reverse move. | compensation | Synchronously projected: sets `library_status=reverted` and clears `missing_since`. | `movie_id`, `source_path`, `target_path`, optional source operation identifiers. | Missing `movie_id` is `unsupported` for projection. |

## Analysis Events

| Event | Meaning | Category | Projector status | v1 payload | Compatibility |
| --- | --- | --- | --- | --- | --- |
| `AnalysisStarted` | Movie genealogy analysis started. | domain | Synchronously projected: sets `analysis_status=processing`. | `movie_id`, optional `title`, `tmdb_id`. | Missing optional display fields can be ignored. |
| `AnalysisCompleted` | Movie genealogy analysis completed. | domain | Synchronously projected: sets `analysis_status=completed`, `analysis_data`, `micro_genre`, and `micro_genre_definition`. | `movie_id`, `analysis_data`, `micro_genre`, `micro_genre_definition`. | Missing `analysis_data` still projects status but loses result detail. |
| `AnalysisFailed` | Movie genealogy analysis failed. | domain | Synchronously projected: sets `analysis_status=failed`. | `movie_id`, `message`. | Missing message can be ignored. |

## External Score Events

| Event | Meaning | Category | Projector status | v1 payload | Compatibility |
| --- | --- | --- | --- | --- | --- |
| `ExternalScoresRefreshed` | External score/ranking data changed for a movie. | domain | Projectable. The successful external score refresh command appends this event and uses the projector for Movie score state. | `movie_id`, `updated_sources`, `skipped_sources`, `force`, `changed_fields`, `previous`, `current`. `current` should include `external_scores`, `external_scores_updated_at`, and `external_scores_error`. | Old events without `current` or top-level score fields are skipped during dry-run. |
| `ExternalScoresRefreshFailed` | External score/ranking refresh failed for a movie. | system/audit | Not projectable. | `movie_id`, `source`, `message`. | Replay ignores it. |

## Library/System Events

| Event | Meaning | Category | Projector status | v1 payload | Compatibility |
| --- | --- | --- | --- | --- | --- |
| `LibraryReconciled` | A library reconcile pass finished. | system/audit | Not projectable. | `media_dir`, result counters such as `processed`, `added`, `updated`, `missing`, or similar result fields. | Replay ignores it. |
| `LibraryCleared` | The library table was cleared. | system/audit | Not projectable. | `deleted`. | Replay ignores it until a dedicated destructive-event strategy exists. |
| `MissingMoviesCleaned` | Missing movie rows were deleted. | system/audit | Not projectable. | `deleted`, `movie_ids`, `truncated`. | Replay ignores it until delete/tombstone projection exists. |
| `LibrarySeeded` | Test seed data was inserted. | system/audit | Not projectable. | `count`. | Replay ignores it. |
| `MovieProjectionRebuilt` | A controlled projection rebuild replaced one Movie read-model row from an empty-base replay. | projection/audit | Not projectable. | `movie_id`, `confirmation_token`, `fields_replaced`, `before`, `after`, `dry_run_summary`; `aggregate_type="projection"`. | Audit only. It must not be replayed as a movie domain event. |

## Compensation Rules

- Compensation events never delete or mutate the original event.
- `causation_id` should point to the event being compensated whenever the source event is known.
- Operation-level undo is not the same as historical time travel. Current restore behavior compensates a selected operation back toward its pre-operation state.
- Field compensation should only write fields when the current value still matches the source event's `current` value; conflicts must be reported and skipped.
- File compensation requires an existing backup/source path and must report partial or skipped recovery when files are missing.
- `MetadataMatched`, `ArtworkSelected`, and successful `ExternalScoresRefreshed` commands are append-first for Movie state: the command records the domain event and uses projection for the Movie row, while file side effects still execute before their result events.
