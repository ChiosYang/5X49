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
  - `heartbeat`: Emitted periodically to keep long-lived connections open.
- **Example Event**:
  ```text
  event: library_changed
  data: {"reason":"folder_scanned","movie_id":"603_1999","folder_path":"/media/The Matrix (1999)","timestamp":"2026-05-11T00:00:00+00:00"}
  ```

### Get Movie Details
- **URL**: `/library/{movie_id}`
- **Method**: `GET`
- **Description**: Get detailed information for a specific movie by ID.
- **Path Parameters**:
  - `movie_id` (string): ASCII movie ID, such as `603_1999`, `tt0133093_1999`, or `local_<hash>`.
- **Response**: `Movie` object.
- **Errors**: `400 Invalid ID format`, `404 Movie not found`.

### Seed Library
- **URL**: `/library/seed`
- **Method**: `POST`
- **Description**: Seeds the library with test data.
- **Response**: Success message objects from the manager.

### Scan Library (from Directory)
- **URL**: `/library/scan`
- **Method**: `POST`
- **Description**: Reconciles a media directory, scans movie folders, upserts discovered records, and marks disappeared movies as missing.
- **Query Parameters**:
  - `media_dir` (string, optional): Target directory to scan. Defaults to system media dir config.
- **Response**: 
  ```json
  {
    "scanned": 10,
    "added": 10,
    "missing": 1,
    "queued_for_analysis": 10,
    "media_dir": "/path/to/media"
  }
  ```

### Reconcile Library
- **URL**: `/library/reconcile`
- **Method**: `POST`
- **Description**: Performs a full library reconciliation and marks movies not seen in the pass as `missing`.
- **Query Parameters**:
  - `media_dir` (string, optional): Target directory to scan. Defaults to system media dir config.
- **Response**: `{"scanned": 10, "added": 2, "missing": 1, "media_dir": "/path/to/media"}`

### Scan Folder
- **URL**: `/library/scan-folder`
- **Method**: `POST`
- **Description**: Scans a single movie folder and upserts the corresponding movie record.
- **Query Parameters**:
  - `folder_path` (string, required): Absolute path to a movie folder.
- **Response**: `{"status": "success", "movie": Movie}`

### Refresh Movie
- **URL**: `/library/{movie_id}/refresh`
- **Method**: `POST`
- **Description**: Refreshes one movie from its known local folder while preserving the existing movie ID.
- **Path Parameters**:
  - `movie_id` (string): The ID of the movie.
- **Response**: `{"status": "success", "movie_id": "...", "updated": true, "movie": Movie}`
- **Errors**: `400 Invalid ID format`, `404 Movie not found`, `409 Movie does not have a folder path`.

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
- **Response**: `{"status": "started", "message": "Metadata scrape started"}`

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
- **Description**: Starts a background job that looks only at video files placed directly in the configured media root, waits for stable files, matches them with TMDB, moves high-confidence matches into movie folders, then scrapes metadata/artwork/NFO. When `/settings/scrape-confirmation` is enabled, matched files return `needs_review` before any move or scrape writes occur.
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
- **Response**: `{"status": "started", "message": "Root video organization started"}`

### Confirm Root Video Organization
- **URL**: `/library/organize-root/confirm`
- **Method**: `POST`
- **Description**: Moves one stable direct media-root video into a movie folder and scrapes it using a user-confirmed TMDB ID. This is the confirmation path for root videos when `/settings/scrape-confirmation` is enabled.
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
- **Response**:
  ```json
  {
    "status": "success",
    "source_path": "/media/The.Matrix.1999.1080p.mkv",
    "target_path": "/media/The Matrix (1999)/The.Matrix.1999.1080p.mkv",
    "movie_id": "local_...",
    "tmdb_id": 603,
    "scrape_status": "success"
  }
  ```
- **Errors**: `400` when the file is not a stable direct root video, `409` when the target exists or organization fails.

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
- **Description**: Manually triggers an analysis run for a specific movie in the background.
- **Path Parameters**:
  - `movie_id` (string): The ID of the movie.
- **Response**: `{"message": "Analysis queued for {movie_id}"}`

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
- **Response**: `{"status": "success", "message": "Library scan started"}`

### Clean Inbox (Agent Stream)
- **URL**: `/api/agents/clean-inbox`
- **Method**: `GET` (Supports Text/Event-Stream)
- **Description**: Summons the Librarian Agent to execute inbox organization directives. Provides streaming Server-Sent Events (SSE) representing agent thoughts, actions, tool executions, and resolutions.

---

## Data Models

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
