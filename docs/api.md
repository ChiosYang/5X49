# Backend API Documentation

This document describes the REST API endpoints available in the backend application, built with FastAPI. Base URL depends on where the API is hosted (default typically `http://localhost:8000`).

## General 

### Health Check
- **URL**: `/health`
- **Method**: `GET`
- **Description**: Returns the health status of the API.
- **Response**:
  ```json
  {
    "status": "healthy"
  }
  ```

### Root Info
- **URL**: `/`
- **Method**: `GET`
- **Description**: Returns basic info about the running API and media directory setup.
- **Response**:
  ```json
  {
    "message": "Film Genealogy API is running",
    "media_dir": "/path/to/media"
  }
  ```

---

## Library Management

### Search Metadata
- **URL**: `/metadata/search`
- **Method**: `GET`
- **Description**: Searches TMDB using the configured `TMDB_API_KEY` and returns scored movie candidates.
- **Query Parameters**:
  - `query` (string, required): Title or filename-derived query.
  - `year` (integer, optional): Release year hint.
  - `language` (string, optional): TMDB language such as `zh-CN` or `en-US`. Defaults to the app language.
- **Response**:
  ```json
  [
    {
      "tmdb_id": 27205,
      "title": "Inception",
      "original_title": "Inception",
      "year": 2010,
      "overview": "...",
      "poster_path": "/...",
      "backdrop_path": "/...",
      "popularity": 80.5,
      "score": 95.0
    }
  ]
  ```
- **Errors**: `503 TMDB_API_KEY is not configured`, `502 Metadata search failed`.

### Get Metadata Movie Candidate
- **URL**: `/metadata/movie/{tmdb_id}`
- **Method**: `GET`
- **Description**: Looks up one TMDB movie ID and returns it in the same candidate shape used by metadata search. This is used to review a manually entered TMDB ID before confirming a scrape or root video organization.
- **Path Parameters**:
  - `tmdb_id` (integer): TMDB movie ID.
- **Query Parameters**:
  - `language` (string, optional): TMDB language such as `zh-CN` or `en-US`.
- **Response**:
  ```json
  {
    "tmdb_id": 603,
    "title": "The Matrix",
    "original_title": "The Matrix",
    "year": 1999,
    "overview": "...",
    "poster_path": "/poster.jpg",
    "backdrop_path": "/backdrop.jpg",
    "popularity": 100,
    "score": 100
  }
  ```

### Get All Movies
- **URL**: `/library`
- **Method**: `GET`
- **Description**: Get all movies currently stored in the local library.
- **Response**: Array of `Movie` objects.

### Subscribe To Library Events
- **URL**: `/library/events`
- **Method**: `GET`
- **Description**: Opens a Server-Sent Events stream for library invalidation events.
- **Response Type**: `text/event-stream`
- **Events**:
  - `connected`: Emitted when the stream is established.
  - `library_changed`: Emitted after library records are scanned, reconciled, seeded, cleared, or marked missing.
  - `job_queued`, `job_started`, `job_progress`, `job_succeeded`, `job_failed`, `job_cancelled`, `job_retried`: Emitted by the background job runtime for queued actor jobs.
  - `heartbeat`: Emitted periodically to keep long-lived connections open.
- **Example Event**:
  ```text
  event: library_changed
  data: {"reason":"folder_scanned","movie_id":"603_1999","folder_path":"/media/The Matrix (1999)","timestamp":"2026-05-11T00:00:00+00:00"}
  ```

### List Library Audit Events
- **URL**: `/library/audit-events`
- **Method**: `GET`
- **Description**: Lists persisted audit events recorded by library, metadata, organizer, analysis, and external score actions. This is a historical event log and is separate from the live `/library/events` SSE stream.
- **Query Parameters**:
  - `aggregate_type` (string, optional): Filter by aggregate type, such as `movie`, `library`, or `file`.
  - `aggregate_id` (string, optional): Filter by aggregate ID, usually a movie ID for `movie` aggregates.
  - `type` (string, optional): Filter by event type, such as `MovieDiscovered`, `MetadataMatched`, or `AnalysisCompleted`.
  - `command_id` (string, optional): Filter by the command that created related events.
  - `correlation_id` (string, optional): Filter by the operation trace shared by related events.
  - `limit` (integer, optional): Number of events to return, 1-500. Defaults to 100.
- **Response**: Array of `EventRecord` objects, newest first.

### Dry-Run Library Operation
- **URL**: `/library/operations/dry-run`
- **Method**: `GET`
- **Description**: Runs a read-only consistency check for one correlated operation. It does not mutate the database or filesystem.
- **Query Parameters**:
  - `correlation_id` (string, optional): Operation trace ID to inspect. Required if `command_id` is not provided.
  - `command_id` (string, optional): Command ID to inspect. Required if `correlation_id` is not provided.
  - `limit` (integer, optional): Number of events to inspect, 1-500. Defaults to 500.
- **Response**: Object containing `status`, `checks`, `side_effects`, `recoverable_fields`, `missing_payload`, `unsafe_actions`, and boolean summaries such as `can_restore_poster`, `can_trace_nfo_writer`, and `can_reverse_root_move`.

### Restore Library Operation
- **URL**: `/library/operations/restore`
- **Method**: `POST`
- **Description**: Executes supported compensation actions for one correlated operation. It first runs the operation dry-run, then restores narrowly supported file side effects or conflict-checked `Movie` field values and records compensation events. It does not delete original events.
- **Request Body**:
  - `correlation_id` (string, optional): Operation trace ID to restore. Required if `command_id` is not provided.
  - `command_id` (string, optional): Command ID to restore. Required if `correlation_id` is not provided.
  - `actions` (array of strings, optional): Any of `restore_metadata`, `restore_artwork_selection`, `restore_poster`, `restore_nfo`, or `reverse_root_move`. Defaults to all supported actions.
  - `limit` (integer, optional): Number of events to inspect, 1-500. Defaults to 500.
- **Response**: Object containing `status`, `operation_id`, restore command/correlation IDs, `restored`, `skipped`, and the dry-run report used for safety checks.
- **Compensation Events**: Supported actions append `MetadataRestored`, `ArtworkSelectionRestored`, `ArtworkRestored`, `NfoRestored`, or `RootVideoMoveReversed` with `causation_id` pointing at the original side-effect event. Field-level restores only write fields whose current value still matches the original event's `current` value; conflicts are reported and skipped. When a reversed root video move belongs to an operation that created a new movie record, the restore also appends `RootVideoOrganizationReverted` and projects that movie to `library_status=reverted`.

### Background Jobs
- **URL**: `/jobs`
- **Method**: `GET`
- **Description**: Lists recent background jobs created by long-running library, metadata, analysis, organizer, and external score actions.
- **Query Parameters**:
  - `status` (string, optional): Filter by `queued`, `running`, `cancelling`, `succeeded`, `failed`, or `cancelled`.
  - `type` (string, optional): Filter by job type, such as `library.reconcile`.
  - `limit` (integer, optional): Number of jobs to return, 1-200. Defaults to 50.
- **Response**: Array of `Job` objects.

### Get Background Job
- **URL**: `/jobs/{job_id}`
- **Method**: `GET`
- **Description**: Returns one job record.
- **Response**:
  ```json
  {
    "id": "job_abc",
    "type": "library.reconcile",
    "status": "succeeded",
    "payload": {"media_dir": "/media"},
    "progress": {"stage": "scanning", "current": 10, "total": 10, "message": "Scanning library"},
    "result": {"scanned": 10, "added": 2, "missing": 1},
    "result_summary": "Scanned 10, added 2, missing 1",
    "error": null,
    "attempts": 1,
    "max_attempts": 1,
    "dedupe_key": "library.reconcile:/media",
    "cancel_requested": false,
    "created_at": "2026-05-19T00:00:00+00:00",
    "updated_at": "2026-05-19T00:00:03+00:00",
    "started_at": "2026-05-19T00:00:01+00:00",
    "finished_at": "2026-05-19T00:00:03+00:00"
  }
  ```
- **Errors**: `404 Job not found`.

### Cancel Background Job
- **URL**: `/jobs/{job_id}/cancel`
- **Method**: `POST`
- **Description**: Cancels a queued job immediately or requests cooperative cancellation for a running job.
- **Response**: `Job` object.

### Retry Background Job
- **URL**: `/jobs/{job_id}/retry`
- **Method**: `POST`
- **Description**: Creates a new queued job using the failed or cancelled job's payload.
- **Response**: Accepted-job envelope.

### Delete Background Job
- **URL**: `/jobs/{job_id}`
- **Method**: `DELETE`
- **Description**: Deletes a terminal job. Active jobs cannot be deleted.
- **Response**: `{"status": "success", "deleted": true}`

Long-running mutation endpoints return an accepted-job envelope:

```json
{
  "status": "queued",
  "message": "Library reconcile queued",
  "job_id": "job_abc",
  "job": {}
}
```

### Get Movie Details
- **URL**: `/library/{movie_id}`
- **Method**: `GET`
- **Description**: Get detailed information for a specific movie by ID.
- **Path Parameters**:
  - `movie_id` (string): ASCII movie ID, such as `603_1999`, `tt0133093_1999`, or `local_<hash>`.
- **Response**: `Movie` object.
- **Errors**: `400 Invalid ID format`, `404 Movie not found`.

### Get Movie Audit Events
- **URL**: `/library/{movie_id}/audit-events`
- **Method**: `GET`
- **Description**: Lists persisted audit events for one movie.
- **Path Parameters**:
  - `movie_id` (string): ASCII movie ID.
- **Query Parameters**:
  - `type` (string, optional): Filter by event type.
  - `limit` (integer, optional): Number of events to return, 1-500. Defaults to 100.
- **Response**: Array of `EventRecord` objects, newest first.
- **Errors**: `400 Invalid ID format`, `404 Movie not found`.

### Dry-run Movie Projection Rebuild
- **URL**: `/library/projections/movie/rebuild`
- **Method**: `POST`
- **Description**: Runs a read-only Movie projection consistency check. It can either start from the current `Movie` snapshot (`base=current`) or replay the supported subset of movie events from an empty in-memory state (`base=empty`). It does not clear, rebuild, or mutate the `movie` table.
- **Query Parameters**:
  - `dry_run` (boolean, optional): Must be `true`. Defaults to `true`; `false` returns `400`.
  - `base` (string, optional): `current` or `empty`. Defaults to `current`.
  - `movie_id` (string, optional): Restrict the check to one movie.
  - `limit` (integer, optional): Maximum movie events to process, 1-5000. Defaults to 1000.
  - `since` (string, optional): Only include events whose `occurred_at` is greater than or equal to this timestamp.
- **Response**:
  ```json
  {
    "dry_run": true,
    "mode": "current_snapshot_plus_events",
    "note": "Consistency dry-run only; this is not a canonical replay from an empty state.",
    "base": "current",
    "movie_id": "local_xxx",
    "since": null,
    "limit": 1000,
    "events_processed": 12,
    "projectable_events": 4,
    "skipped_projectable_events": 0,
    "skipped_events": [],
    "unsupported_events": 8,
    "unsupported_event_types": {"MovieDiscovered": 1, "MetadataMatched": 7},
    "movies_compared": 1,
    "movies_with_differences": 0,
    "differences": []
  }
  ```
- **Projectable Events**:
  - `base=current`: `MovieIgnored`, `MovieMarkedMissing`, `MovieRestored`, `MetadataRestored`, `ArtworkSelectionRestored`, `RootVideoOrganizationReverted`, `AnalysisStarted`, `AnalysisCompleted`, and `AnalysisFailed`.
  - `base=empty`: all `base=current` events plus `MovieDiscovered` and `MovieFileObserved`.
- **Notes**: `base=empty` is still a dry-run and only replays the currently supported subset. Events that are projectable in principle but cannot be applied, such as a `MovieFileObserved` without a prior projected `MovieDiscovered`, are counted in `skipped_projectable_events` and summarized in `skipped_events`.
- **Errors**: `400 Only dry_run=true is supported`, `400 base must be 'current' or 'empty'`, `400 Invalid movie ID format`, `404 Movie not found`.

### Backfill MovieDiscovered Events
- **URL**: `/library/events/backfill/movie-discovered`
- **Method**: `POST`
- **Description**: Creates missing `MovieDiscovered` initialization events for existing `Movie` rows. Defaults to dry-run mode. When executed with `dry_run=false`, it only appends events to the `events` table and does not modify the `movie` table.
- **Query Parameters**:
  - `dry_run` (boolean, optional): Defaults to `true`. Set to `false` to append missing initialization events.
  - `movie_id` (string, optional): Restrict the backfill check or execution to one movie.
  - `sample_limit` (integer, optional): Number of sample event specs to return, 0-50. Defaults to 20.
- **Response**:
  ```json
  {
    "dry_run": true,
    "event_type": "MovieDiscovered",
    "movie_id": null,
    "movies_checked": 42,
    "already_initialized": 0,
    "events_to_create": 42,
    "created_events": 0,
    "created_event_ids": [],
    "sample_events": [
      {
        "type": "MovieDiscovered",
        "aggregate_type": "movie",
        "aggregate_id": "local_xxx",
        "actor_type": "migration",
        "payload": {"id": "local_xxx", "movie_id": "local_xxx", "title": "Example", "year": 2026},
        "context": {"source": "movie_discovered_backfill", "reason": "initialize_event_replay"},
        "occurred_at": "2026-05-20T00:00:00+00:00"
      }
    ],
    "timestamp_strategy": "Backfilled initialization events are placed just before each movie's earliest existing movie event when one exists; otherwise they use added_at, last_seen_at, or current time."
  }
  ```
- **Notes**: The timestamp strategy makes historical initialization events sort before existing per-movie events so `base=empty` replay can apply later events in order. Existing movies that already have `MovieDiscovered` are skipped.
- **Errors**: `400 Invalid movie ID format`, `404 Movie not found`.

### Dry-run NFO Signatures
- **URL**: `/library/events/dry-run/nfo-signatures`
- **Method**: `POST`
- **Description**: Scans a media directory or one movie folder and compares observed NFO file signatures against the current `Movie` table. This is read-only: it does not update `Movie` rows and does not append events.
- **Query Parameters**:
  - `media_dir` (string, optional): Media root to scan. Defaults to configured media directory.
  - `folder_path` (string, optional): Restrict the check to one movie folder.
  - `limit` (integer, optional): Maximum result rows to return, 1-1000. Defaults to 200.
  - `include_unchanged` (boolean, optional): Include unchanged matches in `results`. Defaults to `false`.
- **Response**:
  ```json
  {
    "dry_run": true,
    "media_dir": "/media",
    "folder_path": null,
    "folders_scanned": 42,
    "nfo_files_found": 40,
    "matched_movies": 39,
    "unchanged": 20,
    "new_signatures": 12,
    "changed_signatures": 7,
    "unmatched_movies": 1,
    "folders_without_nfo": 2,
    "results_returned": 20,
    "results_truncated": false,
    "results": [
      {
        "status": "changed",
        "movie_id": "local_xxx",
        "title": "Example",
        "year": 2026,
        "folder_path": "/media/Example (2026)",
        "nfo_path": "/media/Example (2026)/movie.nfo",
        "observed": {
          "nfo_file": "movie.nfo",
          "nfo_path": "/media/Example (2026)/movie.nfo",
          "nfo_size": 1234,
          "nfo_mtime": 1778583332.9761415,
          "nfo_fingerprint": "..."
        },
        "current": {
          "nfo_file": "movie.nfo",
          "nfo_path": "/media/Example (2026)/movie.nfo",
          "nfo_size": 1200,
          "nfo_mtime": 1778583000.0,
          "nfo_fingerprint": "..."
        },
        "changed_fields": ["nfo_size", "nfo_mtime", "nfo_fingerprint"],
        "parse_error": null
      }
    ]
  }
  ```
- **Result Statuses**: `new_signature` means the movie exists but has no stored NFO signature yet; `changed` means at least one signature field changed; `unchanged` means the observed signature matches the stored signature; `unmatched_movie` means an NFO file was found but no existing `Movie` row matched it.
- **Movie Fields**: `Movie` now includes `nfo_file`, `nfo_path`, `nfo_size`, `nfo_mtime`, and `nfo_fingerprint` when available.
- **Errors**: `404 Movie folder not found`, `404 Media directory not found`.

### Refresh Movie External Scores
- **URL**: `/library/{movie_id}/external-scores/refresh`
- **Method**: `POST`
- **Description**: Queues a job to refresh external score and ranking signals for one movie. The current implementation imports TSPDT data from `dataset/TSPDT - 1,000 Greatest Films (Table).csv` and writes high-confidence matches to the movie's `external_scores`.
- **Path Parameters**:
  - `movie_id` (string): The ID of the movie.
- **Query Parameters**:
  - `force` (boolean, optional): Reserved for sources with TTL caches. Defaults to `false`.
- **Response**: Accepted-job envelope. Final result is stored in the job's `result`.
- **Errors**: `400 Invalid ID format`, `404 Movie not found`.

### Refresh Library External Scores
- **URL**: `/library/external-scores/refresh`
- **Method**: `POST`
- **Description**: Queues a background refresh of external score sources for available movies.
- **Query Parameters**:
  - `force` (boolean, optional): Reserved for sources with TTL caches. Defaults to `false`.
- **Response**: Accepted-job envelope.

### Get External Score Refresh Status
- **URL**: `/library/external-scores/status`
- **Method**: `GET`
- **Description**: Returns the latest batch external score refresh status.
- **Response**:
  ```json
  {
    "state": "idle",
    "last_started_at": "2026-05-18T00:00:00+00:00",
    "last_finished_at": "2026-05-18T00:01:00+00:00",
    "last_error": null,
    "last_result": {"processed": 100, "updated": 20, "skipped": 80, "failed": 0}
  }
  ```

### Seed Library
- **URL**: `/library/seed`
- **Method**: `POST`
- **Description**: Seeds the library with test data.
- **Response**: Success message objects from the manager.

### Scan Library (from Directory)
- **URL**: `/library/scan`
- **Method**: `POST`
- **Description**: Queues a media directory reconciliation job that scans movie folders, upserts discovered records, and marks disappeared movies as missing.
- **Query Parameters**:
  - `media_dir` (string, optional): Target directory to scan. Defaults to system media dir config.
- **Response**: Accepted-job envelope. Final reconcile counts are stored in the job's `result`.

### Reconcile Library
- **URL**: `/library/reconcile`
- **Method**: `POST`
- **Description**: Queues a full library reconciliation and marks movies not seen in the pass as `missing`.
- **Query Parameters**:
  - `media_dir` (string, optional): Target directory to scan. Defaults to system media dir config.
- **Response**: Accepted-job envelope. Final reconcile counts are stored in the job's `result`.

### Scan Folder
- **URL**: `/library/scan-folder`
- **Method**: `POST`
- **Description**: Queues a scan for a single movie folder and upserts the corresponding movie record.
- **Query Parameters**:
  - `folder_path` (string, required): Absolute path to a movie folder.
- **Response**: Accepted-job envelope. Final movie payload is stored in the job's `result`.

### Refresh Movie
- **URL**: `/library/{movie_id}/refresh`
- **Method**: `POST`
- **Description**: Queues a refresh for one movie from its known local folder while preserving the existing movie ID.
- **Path Parameters**:
  - `movie_id` (string): The ID of the movie.
- **Response**: Accepted-job envelope. Final movie payload is stored in the job's `result`.
- **Errors**: `400 Invalid ID format`, `404 Movie not found`.

### Get Movie Artwork Options
- **URL**: `/library/{movie_id}/artwork`
- **Method**: `GET`
- **Description**: Lists selectable TMDB posters and backdrops for a movie that already has a `tmdb_id`.
- **Path Parameters**:
  - `movie_id` (string): The ID of the movie.
- **Response**:
  ```json
  {
    "movie_id": "603_1999",
    "tmdb_id": 603,
    "posters": [
      {
        "file_path": "/poster.jpg",
        "url": "https://image.tmdb.org/t/p/original/poster.jpg",
        "thumbnail_url": "https://image.tmdb.org/t/p/w500/poster.jpg",
        "width": 2000,
        "height": 3000,
        "aspect_ratio": 0.667,
        "language": "en",
        "vote_average": 5.3,
        "vote_count": 10
      }
    ],
    "backdrops": [],
    "current_poster_path": "/poster.jpg",
    "current_backdrop_path": "/backdrop.jpg"
  }
  ```
- **Errors**: `400 Invalid ID format`, `404 Movie not found`, `409 Movie does not have a TMDB ID`, `503 TMDB_API_KEY is not configured`.

### Update Movie Artwork
- **URL**: `/library/{movie_id}/artwork`
- **Method**: `PUT`
- **Description**: Applies a selected TMDB poster and/or backdrop. The backend verifies the selected TMDB paths, downloads them over the existing `<video-stem>-poster.jpg` / `<video-stem>-fanart.jpg` files, updates artwork references in the local NFO when present, rescans the folder, and returns the updated movie.
- **Body**:
  ```json
  {
    "poster_path": "/poster.jpg",
    "backdrop_path": "/backdrop.jpg"
  }
  ```
  Each field is optional, but at least one must be provided.
- **Response**:
  ```json
  {
    "status": "success",
    "movie_id": "603_1999",
    "movie": {},
    "poster_path": "/poster.jpg",
    "backdrop_path": "/backdrop.jpg"
  }
  ```
- **Errors**: `400 Invalid ID format`, `404 Movie not found`, `409` for missing TMDB ID, invalid selection, or missing folder, `503 TMDB_API_KEY is not configured`.

### Scrape Movie Metadata
- **URL**: `/library/{movie_id}/scrape`
- **Method**: `POST`
- **Description**: Uses TMDB to enrich one movie, optionally downloading `<video-stem>-poster.jpg` / `<video-stem>-fanart.jpg`, writing `<video-stem>.nfo`, rescanning the folder, and updating the database.
- **Body**:
  ```json
  {
    "mode": "auto",
    "language": "zh-CN",
    "artwork_language": "en",
    "overwrite": false,
    "write_nfo": true,
    "download_artwork": true,
    "tmdb_id": null
  }
  ```
- **Artwork Language**: `artwork_language` is optional and controls posters/backdrops independently from metadata text. Supported values are `metadata` (follow `language`), `zh`, `en`, and `none` (textless). When omitted, the saved `/settings/artwork-language` value is used.
- **Response**:
  ```json
  {
    "status": "success",
    "movie_id": "local_...",
    "message": "Metadata scraped",
    "movie": {},
    "candidates": []
  }
  ```
- **Needs Review**: If the best automatic match has low confidence, or `/settings/scrape-confirmation` is enabled, returns `status: "needs_review"` with up to 20 scored `candidates`.
- **Errors**: `400 Invalid ID format`, `409` with a scrape result payload when scraping fails.

### Confirm Movie Metadata Match
- **URL**: `/library/{movie_id}/scrape/confirm`
- **Method**: `POST`
- **Description**: Scrapes one movie using a user-selected TMDB ID.
- **Query Parameters**:
  - `tmdb_id` (integer, required): Confirmed TMDB movie ID.
- **Body**: Same options as Scrape Movie Metadata.
- **Response**: Same shape as Scrape Movie Metadata.

### Scrape Library Metadata
- **URL**: `/library/scrape`
- **Method**: `POST`
- **Description**: Starts a background metadata scrape for movies matching the requested scope.
- **Body**:
  ```json
  {
    "scope": "unscraped",
    "movie_ids": null,
    "language": "zh-CN",
    "artwork_language": "en",
    "overwrite": false,
    "write_nfo": true,
    "download_artwork": true
  }
  ```
- **Scopes**:
  - `unscraped`: Available movies with `metadata_source=filename` and `scrape_status` of `pending` or `failed`.
  - `missing_artwork`: Movies missing local poster or backdrop.
  - `all`: Every available movie.
  - `selected`: Only IDs listed in `movie_ids`.
- **Confirmation Mode**: When `/settings/scrape-confirmation` is enabled, automatic matches are counted as `needs_review` and are not written until confirmed with `/library/{movie_id}/scrape/confirm`.
- **Response**: Accepted-job envelope. Final batch scrape counts are stored in the job's `result`.

Root video organization accepts the same `language` and `artwork_language` scrape options when moving and scraping direct media-root videos.

### Get Metadata Scrape Status
- **URL**: `/library/scrape/status`
- **Method**: `GET`
- **Description**: Returns latest batch metadata scrape state.
- **Response**:
  ```json
  {
    "state": "idle",
    "last_started_at": "2026-05-12T00:00:00+00:00",
    "last_finished_at": "2026-05-12T00:01:00+00:00",
    "last_error": null,
    "last_result": {
      "processed": 10,
      "succeeded": 8,
      "needs_review": 1,
      "failed": 1,
      "skipped": 0
    }
  }
  ```

### Organize Root Videos
- **URL**: `/library/organize-root`
- **Method**: `POST`
- **Description**: Queues a background job that looks only at video files placed directly in the configured media root, waits for stable files, matches them with TMDB, moves high-confidence matches into movie folders, then scrapes metadata/artwork/NFO. When `/settings/scrape-confirmation` is enabled, matched files return `needs_review` before any move or scrape writes occur.
- **Body**:
  ```json
  {
    "min_confidence": 85,
    "rename_style": "preserve_stem",
    "overwrite": false,
    "write_nfo": true,
    "download_artwork": true,
    "language": "zh-CN"
  }
  ```
- **Rename Styles**:
  - `preserve_stem`: Keep the original video filename and move it into a matched movie folder.
  - `title_year`: Rename the video to the matched title/year.
- **Response**: Accepted-job envelope. Final organization counts are stored in the job's `result`.

### Confirm Root Video Organization
- **URL**: `/library/organize-root/confirm`
- **Method**: `POST`
- **Description**: Queues a job that moves one stable direct media-root video into a movie folder and scrapes it using a user-confirmed TMDB ID. This is the confirmation path for root videos when `/settings/scrape-confirmation` is enabled.
- **Body**:
  ```json
  {
    "path": "/media/The.Matrix.1999.1080p.mkv",
    "tmdb_id": 603,
    "options": {
      "rename_style": "preserve_stem",
      "overwrite": false,
      "write_nfo": true,
      "download_artwork": true,
      "language": "zh-CN"
    }
  }
  ```
- **Response**: Accepted-job envelope. Final organization payload is stored in the job's `result`.
- **Errors**: `404 Root video file not found`.

### Get Root Organization Status
- **URL**: `/library/organize/status`
- **Method**: `GET`
- **Description**: Returns latest root video organization state.
- **Response**:
  ```json
  {
    "state": "idle",
    "last_error": null,
    "last_result": {
      "processed": 1,
      "organized": 1,
      "scraped": 1,
      "needs_review": 0,
      "failed": 0,
      "skipped": 0
    }
  }
  ```

### List Root Videos
- **URL**: `/library/root-videos`
- **Method**: `GET`
- **Description**: Lists direct video files under the configured media root that are waiting for organization. This endpoint is read-only and does not create library records.
- **Response**:
  ```json
  [
    {
      "path": "/media/output.mp4",
      "filename": "output.mp4",
      "size": 7697577,
      "mtime": 1778580000.0,
      "stable": true,
      "parsed_title": "output",
      "parsed_year": 0,
      "status": "needs_organize"
    }
  ]
  ```

### Get Library Sync Status
- **URL**: `/library/sync/status`
- **Method**: `GET`
- **Description**: Returns last reconciliation status and automatic watcher status.
- **Response**:
  ```json
  {
    "sync": {
      "state": "idle",
      "last_started_at": "2026-05-10T00:00:00+00:00",
      "last_finished_at": "2026-05-10T00:00:03+00:00",
      "last_error": null,
      "last_result": {"scanned": 10, "added": 2, "missing": 1}
    },
    "watcher": {
      "running": true,
      "media_dir": "/media",
      "mode": "events",
      "last_event_at": 1778371200.0,
      "last_error": null,
      "pending": 0
    }
  }
  ```

### Clear Library
- **URL**: `/library`
- **Method**: `DELETE`
- **Description**: Clears all movies from the library database.
- **Response**: `{"message": "Library cleared"}`

### Ignore Movie
- **URL**: `/library/{movie_id}/ignore`
- **Method**: `POST`
- **Description**: Marks one movie as `library_status=ignored` so it is hidden from normal library views and skipped by reconciliation/scrape batches.
- **Path Parameters**:
  - `movie_id` (string): The ID of the movie.
- **Response**: `{"status": "success", "movie": Movie}`
- **Errors**: `400 Invalid ID format`, `404 Movie not found`.

### Clean Missing Records
- **URL**: `/library/missing`
- **Method**: `DELETE`
- **Description**: Deletes database records already marked as `library_status=missing`.
- **Response**: `{"status": "success", "deleted": 3}`

---

## Analysis

### Analyze Genealogy (Specific Movie)
- **URL**: `/analyze/{movie_name}`
- **Method**: `GET`
- **Description**: Synchronously analyzes the genealogy of a given movie name.
- **Path Parameters**:
  - `movie_name` (string): The name of the movie to analyze.
- **Response**: Analysis result payload.
- **Errors**: `404 Film not found or analysis failed`.

### Trigger Analysis (Background)
- **URL**: `/library/analyze/{movie_id}`
- **Method**: `POST`
- **Description**: Queues an analysis run for a specific movie in the background.
- **Path Parameters**:
  - `movie_id` (string): The ID of the movie.
- **Response**: Accepted-job envelope.

---

## Settings & Configuration

### Get Settings
- **URL**: `/settings`
- **Method**: `GET`
- **Description**: Retrieves whole current system settings dictionary.
- **Response Notes**: Includes library watcher fields such as `watch_library`, `watch_mode` (`events` or `polling`), `watch_debounce_seconds`, `watch_interval_seconds`, `media_file_stable_seconds`, `scrape_require_confirmation`, and `artwork_language`. Secret values such as `tmdb_api_key` are not returned; TMDB configuration is represented by the `tmdb` status object.

### Get Model Setting
- **URL**: `/settings/model`
- **Method**: `GET`
- **Description**: Get the currently configured model and list of available models.
- **Response**:
  ```json
  {
    "current_model": "gpt-4",
    "available_models": ["gpt-4", "gpt-3.5-turbo"]
  }
  ```

### Update Model Setting
- **URL**: `/settings/model`
- **Method**: `PUT`
- **Description**: Updates the currently active model.
- **Query Parameters**:
  - `model_name` (string, required): The intended model to use.
- **Response**: `{"message": "Model updated", "model_name": "..."}`
- **Errors**: `500 Failed to save settings`

### Get Media Directory
- **URL**: `/settings/media-dir`
- **Method**: `GET`
- **Description**: Fetches the currently configured media directory pathway.
- **Response**: `{"media_dir": "/path/to/media"}`

### Update Media Directory
- **URL**: `/settings/media-dir`
- **Method**: `PUT`
- **Description**: Updates the media directory location setting.
- **Query Parameters**:
  - `media_dir` (string, required): The target filesystem path string.
- **Response**: Success status with a prompt to restart server for static files changes.

### Get Language Setting
- **URL**: `/settings/language`
- **Method**: `GET`
- **Description**: Fetches the current language localization ('zh' or 'en').
- **Response**: `{"language": "zh"}`

### Update Language Setting
- **URL**: `/settings/language`
- **Method**: `PUT`
- **Description**: Sets the system language configuration.
- **Query Parameters**:
  - `language` (string, required): Allowed values `zh` or `en`.

### Get Library Watch Setting
- **URL**: `/settings/library-watch`
- **Method**: `GET`
- **Description**: Gets whether automatic library watching is enabled and the current watcher status.
- **Response**: `{"watch_library": true, "watcher": {...}}`

### Update Library Watch Setting
- **URL**: `/settings/library-watch`
- **Method**: `PUT`
- **Description**: Enables or disables the automatic library watcher immediately and persists the setting.
- **Query Parameters**:
  - `enabled` (boolean, required): Whether to run the watcher.
  - The watcher defaults to native filesystem events with debounce to avoid repeated full-tree scans.
  - Set `watch_mode` to `polling` in settings or `WATCH_MODE=polling` to use the legacy polling fallback for mounts where native events are unreliable.

### Get Auto Organize Root Setting
- **URL**: `/settings/auto-organize-root`
- **Method**: `GET`
- **Description**: Gets whether stable direct video files in the media root are automatically organized when the watcher is running.
- **Response**: `{"auto_organize_root_videos": false}`

### Update Auto Organize Root Setting
- **URL**: `/settings/auto-organize-root`
- **Method**: `PUT`
- **Description**: Enables or disables automatic root video organization.
- **Query Parameters**:
  - `enabled` (boolean, required): Whether to organize root videos automatically.

### Get Scrape Confirmation Setting
- **URL**: `/settings/scrape-confirmation`
- **Method**: `GET`
- **Description**: Gets whether automatic TMDB matches require manual confirmation before writing artwork, NFO files, or matched metadata.
- **Response**: `{"scrape_require_confirmation": false}`

### Update Scrape Confirmation Setting
- **URL**: `/settings/scrape-confirmation`
- **Method**: `PUT`
- **Description**: Enables or disables manual confirmation before automatic metadata scraping writes files or matched metadata.
- **Query Parameters**:
  - `enabled` (boolean, required): Whether every automatic TMDB match must be confirmed first.

### Get Artwork Language Setting
- **URL**: `/settings/artwork-language`
- **Method**: `GET`
- **Description**: Gets the poster/backdrop language used by TMDB scraping when a request does not provide `artwork_language`.
- **Response**: `{"artwork_language": "metadata"}`

### Update Artwork Language Setting
- **URL**: `/settings/artwork-language`
- **Method**: `PUT`
- **Description**: Sets poster/backdrop language separately from metadata text language.
- **Query Parameters**:
  - `language` (string, required): One of `metadata`, `zh`, `en`, or `none`.

### Get TMDB Setting
- **URL**: `/settings/tmdb`
- **Method**: `GET`
- **Description**: Gets TMDB API key configuration status without exposing the key.
- **Response**:
  ```json
  {
    "configured": true,
    "source": "environment"
  }
  ```
- **Response Fields**:
  - `configured` (boolean): Whether a TMDB API key is available.
  - `source` (string, nullable): `environment`, `settings`, or `null`.

### Update TMDB Setting
- **URL**: `/settings/tmdb`
- **Method**: `PUT`
- **Description**: Saves a TMDB API key in settings when `TMDB_API_KEY` is not managed by the process environment. Sending an empty `api_key` clears the saved settings key.
- **Request Body**:
  ```json
  {
    "api_key": "..."
  }
  ```
- **Response**: `{"status": "success", "configured": true, "source": "settings"}`
- **Errors**: `409 TMDB_API_KEY is configured by environment`, `500 Failed to save settings`

### Test TMDB API Key
- **URL**: `/settings/tmdb/test`
- **Method**: `POST`
- **Description**: Tests the currently configured TMDB API key by calling TMDB configuration.
- **Response**:
  ```json
  {
    "status": "success",
    "message": "TMDB API key is valid"
  }
  ```
- **Errors**: `503 TMDB_API_KEY is not configured`, `502 TMDB API test failed`

### Get Base URL
- **URL**: `/settings/base-url`
- **Method**: `GET`
- **Description**: Get the designated API base URL setting.

### Update Base URL
- **URL**: `/settings/base-url`
- **Method**: `PUT`
- **Description**: Updates the designated API base URL.
- **Query Parameters**:
  - `base_url` (string, required): URL payload.

### Refresh Models
- **URL**: `/settings/models/refresh`
- **Method**: `POST`
- **Description**: Forces a refresh caching update of the available models from the OpenRouter API.

### Test API Key
- **URL**: `/settings/test-api-key`
- **Method**: `GET`
- **Description**: Ping test verifying the integrity of the OpenRouter API Key configured in the environment.
- **Response**: Status and count of valid accessible models or an error state message.

---

## System & Agents

### List Directories
- **URL**: `/sys/list-dirs`
- **Method**: `GET`
- **Description**: List valid subdirectories under a given folder path. Used primarily for frontend file browser components.
- **Query Parameters**:
  - `path` (string, optional): Starts at `/` by default.
- **Response**:
  ```json
  {
    "current_path": "/path",
    "parent_path": "/",
    "directories": [
      {
        "name": "Movies",
        "path": "/path/Movies"
      }
    ]
  }
  ```

### Trigger Manual Scan
- **URL**: `/sys/scan-library`
- **Method**: `POST`
- **Description**: Starts a background reconciliation for the configured media library without returning immediate scan stats.
- **Response**: Accepted-job envelope.

### Clean Inbox (Agent Stream)
- **URL**: `/api/agents/clean-inbox`
- **Method**: `GET` (Supports Text/Event-Stream)
- **Description**: Summons the Librarian Agent to execute inbox organization directives. Provides streaming Server-Sent Events (SSE) representing agent thoughts, actions, tool executions, and resolutions.

---

## Data Models

### Job schema

Background jobs are persisted in SQLite and executed by the in-process actor runtime.

- `id` (String): Primary key, formatted as `job_<uuid-hex>`.
- `type` (String): Actor command such as `library.reconcile`, `metadata.scrape_library`, `analysis.analyze_movie`, or `organizer.organize_root`.
- `status` (String): `queued`, `running`, `cancelling`, `succeeded`, `failed`, or `cancelled`.
- `payload` (Object, Optional): Input captured when the job was queued.
- `progress` (Object, Optional): Current stage, message, and optional `current` / `total` counters.
- `result` (Object, Optional): Final handler result for succeeded jobs.
- `result_summary` (String, Optional): UI-ready result text.
- `error` (String, Optional): Failure message for failed jobs.
- `attempts` / `max_attempts` (Integer): Execution attempt counters.
- `priority` (Integer): Higher-priority jobs are claimed first.
- `dedupe_key` (String, Optional): Active jobs with the same key are reused instead of duplicated.
- `cancel_requested` (Boolean): Cooperative cancellation flag checked by long-running handlers.
- `created_at`, `updated_at`, `started_at`, `finished_at` (String, Optional): UTC ISO timestamps.

### EventRecord schema

Audit events are persisted in the `events` table. Most events currently act as an audit sidecar while selected low-risk events such as `MovieIgnored`, `MovieMarkedMissing`, `MovieRestored`, `MetadataRestored`, `ArtworkSelectionRestored`, `RootVideoOrganizationReverted`, `AnalysisStarted`, `AnalysisCompleted`, and `AnalysisFailed` are synchronously projected into the `Movie` current-state table.

- `id` (String): Primary key, formatted as `evt_<uuid-hex>`.
- `aggregate_type` (String): Event aggregate category, such as `movie`, `library`, or `file`.
- `aggregate_id` (String, Optional): Aggregate identifier. Movie events use the current movie ID.
- `type` (String): Semantic event type, for example `MovieDiscovered`, `MovieFileObserved`, `MovieFolderScanned`, `MovieMetadataParsedFromNfo`, `MovieMarkedMissing`, `MovieIgnored`, `MetadataMatchSuggested`, `MetadataMatched`, `MetadataRestored`, `MetadataScrapeFailed`, `ArtworkSelected`, `ArtworkSelectionRestored`, `ArtworkRestored`, `NfoRestored`, `RootVideoMoveReversed`, `RootVideoOrganizationReverted`, `RootVideoOrganized`, `AnalysisStarted`, `AnalysisCompleted`, `AnalysisFailed`, `ExternalScoresRefreshed`, or `ExternalScoresRefreshFailed`.
- `actor_type` / `actor_id` (String, Optional): Actor metadata. Stage 1 defaults to `system`.
- `command_id`, `correlation_id`, `causation_id` (String, Optional): Optional command and trace identifiers reserved for later event-sourced workflows.
- `payload` (Object): Event-specific details.
- `context` (Object): Additional metadata reserved for later use.
- `schema_version` (Integer): Event payload schema version.
- `occurred_at` (String): UTC ISO timestamp.

Scan-related events are de-duplicated: `MovieDiscovered` is recorded for new records, `MovieFileObserved` is recorded only when key local file fields change, `MovieMetadataParsedFromNfo` is recorded only when NFO signature fields change, and `MovieRestored` is recorded when a previously missing movie is observed as available again. Successful folder scans no longer append `MovieFolderScanned` by default; UI refresh notifications are still published through `/library/events`.

Stage 4 side-effect events carry richer audit payloads. `MetadataMatched` and `ArtworkSelected` include `changed_fields`, `previous`, and `current` summaries for the fields they changed. `ArtworkDownloaded` records poster/backdrop file writes, `NfoWritten` records NFO creation or artwork updates, and both include `backup_path` when an existing file was backed up before overwrite. `RootVideoMoved` records the root video move before later scan/scrape steps run. `RootVideoOrganized` includes source/target file snapshots and the selected TMDB candidate. Scrape, artwork, and root-video organization flows also populate `command_id` and `correlation_id` so related side-effect and scan events can be grouped. `/library/operations/restore` can use this event chain to execute supported compensation actions and append `MetadataRestored`, `ArtworkSelectionRestored`, `ArtworkRestored`, `NfoRestored`, or `RootVideoMoveReversed`. For root-video operations that created a new movie record, the restore also appends `RootVideoOrganizationReverted` so the record is hidden from normal library views instead of later appearing as missing.

### Movie schema
The core database payload associated with movies.

- `id` (String): Primary key identifier. IDs are URL-safe ASCII strings. Movies with TMDB/IMDb metadata use that external ID plus year; local-only movies use a stable `local_<hash>` derived from the media path.
- `title` (String): Movie canonical title
- `title_cn` (String, Optional): Chinese localized title
- `year` (Integer): Release year
- `poster_local` / `backdrop_local` (String, Optional): Local stored original artwork paths
- `poster_thumb_local` / `backdrop_thumb_local` (String, Optional): Backend-generated local thumbnail paths served from `/artwork-cache`
- `poster_path` / `backdrop_path` (String, Optional): Remote or relative endpoint paths
- `tmdb_id` / `imdb_id` (String, Optional): Scraped identity IDs
- `overview` / `plot` (String, Optional): Descriptive summary
- `director` (String, Optional)
- `runtime` (Integer, Optional): Runtime length
- `countries` (Array of Strings, Optional): Production countries parsed from NFO metadata
- `audio_tracks` (Array of Dicts, Optional): Audio stream summaries with `codec`, `language`, and `channels` when available
- `imdb_rating` (Float, Optional): Score
- `external_scores` (Array of Dicts, Optional): External score/ranking signals. TSPDT entries use `source=tspdt`, `kind=rank`, `rank`, `previous_rank`, `list_name`, `edition`, `matched_by`, and `confidence`. Future rating sources may use `kind=rating`, `value`, `scale`, `votes`, `url`, `fetched_at`, and `expires_at`.
- `external_scores_updated_at` (String, Optional): Last external score refresh timestamp for this movie
- `external_scores_error` (String, Optional): Last external score refresh error, if any
- `genres` (Array of Strings, Optional)
- `actors` (Array of Dicts, Optional): Detailed cast
- `analysis_status` (String): Status code (default `'pending'`)
- `micro_genre` / `micro_genre_definition` (String, Optional): Analysis outputs
- `analysis_data` (JSON/Dictionary, Optional): Dense parsed metadata result
- `folder_name` / `video_file` (String, Optional): Physical system locators
- `nfo_source` (String, Optional): Indicator of metadata origin file
- `media_path` (String, Optional): Absolute path to the primary video file
- `folder_path` (String, Optional): Absolute path to the movie folder
- `file_size` (Integer, Optional): Primary video file size in bytes
- `file_mtime` (Float, Optional): Primary video file modification time
- `video_width` / `video_height` (Integer, Optional): Primary video resolution from `ffprobe`
- `video_codec` (String, Optional): Primary video stream codec, for example `h264`, `hevc`, or `av1`
- `video_bitrate` (Integer, Optional): Primary video bitrate in bits per second, falling back to container bitrate when stream bitrate is unavailable
- `video_duration` (Float, Optional): Primary video duration in seconds
- `video_fps` (Float, Optional): Average frame rate
- `video_dynamic_range` (String, Optional): Detected dynamic range, usually `SDR`, `HDR10`, `HLG`, `Dolby Vision`, or `unknown`
- `video_bit_depth` (Integer, Optional): Detected video bit depth when exposed by the stream metadata
- `added_at` (String, Optional): Timestamp when the movie record was first added to the local library
- `last_seen_at` (String, Optional): Last successful scan timestamp
- `missing_since` (String, Optional): Timestamp when the movie was first marked missing
- `library_status` (String): Library availability status, `available`, `missing`, or `ignored`
- `metadata_updated_at` (String, Optional): Last metadata parse timestamp
- `metadata_source` (String, Optional): Metadata origin such as `filename`, `tmm`, or `tmdb`
- `scrape_status` (String): Metadata scrape status, `pending`, `matched`, `needs_review`, or `failed`
- `scrape_error` (String, Optional): Last metadata scrape error
- `scraped_at` (String, Optional): Last successful metadata scrape timestamp
- `tmdb_confidence` (Float, Optional): Automatic TMDB match confidence score

Filename-only records are discovery records, not confirmed identity metadata. They are created with `metadata_source=filename` and `scrape_status=pending`; high-confidence or user-confirmed TMDB scraping changes them to `scrape_status=matched`. For discovery records and TMDB matching, the primary video filename is the source of the parsed title/year; folder names are treated as physical containers, not movie identity.

Root video organization only processes direct files under the media root. It does not scan nested folders as root videos, skips unstable or temporary files, and requires a high-confidence TMDB match before moving files. Root videos are surfaced by `/library/root-videos` so the UI can show pending files without treating the media root as a movie folder.
