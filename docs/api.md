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

### Get All Movies
- **URL**: `/library`
- **Method**: `GET`
- **Description**: Get all movies currently stored in the local library.
- **Response**: Array of `Movie` objects.

### Get Movie Details
- **URL**: `/library/{movie_id}`
- **Method**: `GET`
- **Description**: Get detailed information for a specific movie by ID.
- **Path Parameters**:
  - `movie_id` (string): The ID of the movie.
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
- **Description**: Scans a directory for TMM-scraped movies (NFO files) and adds them to the library database.
- **Query Parameters**:
  - `media_dir` (string, optional): Target directory to scan. Defaults to system media dir config.
- **Response**: 
  ```json
  {
    "scanned": 10,
    "added": 10,
    "queued_for_analysis": 10,
    "media_dir": "/path/to/media"
  }
  ```

### Clear Library
- **URL**: `/library`
- **Method**: `DELETE`
- **Description**: Clears all movies from the library database.
- **Response**: `{"message": "Library cleared"}`

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
- **Description**: Starts a background scan for the configured media library. Differs functionally from `/library/scan` by enforcing no-blocking execution asynchronously in standard tasks structure without returning immediate scan stats.
- **Response**: `{"status": "success", "message": "Library scan started"}`

### Clean Inbox (Agent Stream)
- **URL**: `/api/agents/clean-inbox`
- **Method**: `GET` (Supports Text/Event-Stream)
- **Description**: Summons the Librarian Agent to execute inbox organization directives. Provides streaming Server-Sent Events (SSE) representing agent thoughts, actions, tool executions, and resolutions.

---

## Data Models

### Movie schema
The core database payload associated with movies.

- `id` (String): Primary key identifier
- `title` (String): Movie canonical title
- `title_cn` (String, Optional): Chinese localized title
- `year` (Integer): Release year
- `poster_local` / `backdrop_local` (String, Optional): Local stored paths
- `poster_path` / `backdrop_path` (String, Optional): Remote or relative endpoint paths
- `tmdb_id` / `imdb_id` (String, Optional): Scraped identity IDs
- `overview` / `plot` (String, Optional): Descriptive summary
- `director` (String, Optional)
- `runtime` (Integer, Optional): Runtime length
- `imdb_rating` (Float, Optional): Score
- `genres` (Array of Strings, Optional)
- `actors` (Array of Dicts, Optional): Detailed cast
- `analysis_status` (String): Status code (default `'pending'`)
- `micro_genre` / `micro_genre_definition` (String, Optional): Analysis outputs
- `analysis_data` (JSON/Dictionary, Optional): Dense parsed metadata result
- `folder_name` / `video_file` (String, Optional): Physical system locators
- `nfo_source` (String, Optional): Indicator of metadata origin file
