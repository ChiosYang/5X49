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

### Scrape Movie Metadata
- **URL**: `/library/{movie_id}/scrape`
- **Method**: `POST`
- **Description**: Uses TMDB to enrich one movie, optionally downloading `<video-stem>-poster.jpg` / `<video-stem>-fanart.jpg`, writing `<video-stem>.nfo`, rescanning the folder, and updating the database.
- **Body**:
  ```json
  {
    "mode": "auto",
    "language": "zh-CN",
    "overwrite": false,
    "write_nfo": true,
    "download_artwork": true,
    "tmdb_id": null
  }
  ```
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
- **Needs Review**: If the best automatic match has low confidence, returns `status: "needs_review"` with up to five scored `candidates`.
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
- **Response**: `{"status": "started", "message": "Metadata scrape started"}`

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
- **Response Notes**: Includes library watcher fields such as `watch_library`, `watch_mode` (`events` or `polling`), `watch_debounce_seconds`, `watch_interval_seconds`, and `media_file_stable_seconds`.

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
- `poster_local` / `backdrop_local` (String, Optional): Local stored paths
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
