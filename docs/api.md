# 5X49 Backend API

This document describes the Fresh Canonical resource API. The backend normally
listens on `http://127.0.0.1:8000`; the frontend proxies `/api/*` and `/media/*`
from port `5549`.

The staged Graph, Workflow and portability interfaces are tracked in
`docs/features/cinema-knowledge-architecture.md`. They are added here only when
their implementation slice is complete; the feature document is not a runtime
compatibility promise.

## Resource IDs

- Film IDs use `film_<32 lowercase hex>`.
- LibraryItem IDs use `lib_<32 lowercase hex>`.
- OperationSnapshot IDs use `snap_<32 lowercase hex>`.
- Film is the stable public work identity. A Film may own several LibraryItems.
- LibraryItem is used only for a concrete local edition or source item.

There are no Movie IDs, aliases, compatibility responses, or selectable read
sources. Invalid resource IDs return `400`; missing resources return `404`.

## Core and settings

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Process health. |
| `GET` | `/` | Service information. |
| `GET` | `/settings` | Combined non-secret settings. |
| `GET/PUT` | `/settings/model` | Analysis model selection. |
| `GET/PUT` | `/settings/media-dir` | Local media root. |
| `GET/PUT` | `/settings/language` | Application language. |
| `GET/PUT` | `/settings/artwork-language` | Preferred artwork language. |
| `GET/PUT` | `/settings/library-watch` | Filesystem watcher state. |
| `GET/PUT` | `/settings/auto-organize-root` | Root-video automation. |
| `GET/PUT` | `/settings/scrape-confirmation` | Require confirmation before scraping. |
| `GET/PUT` | `/settings/tmdb` | TMDB configuration state/write. Reads never expose the secret. |
| `POST` | `/settings/tmdb/test` | Test TMDB access. |
| `GET/PUT` | `/settings/base-url` | OpenAI-compatible endpoint setting. |
| `POST` | `/settings/models/refresh` | Refresh model catalog. |
| `GET` | `/settings/test-api-key` | Test the configured analysis provider. |

## Library Films

### `GET /library/films`

Returns `LibraryFilmSummary[]`, one row per visible Film. Each row includes the
selected title and metadata, `primary_item`, profile state, external scores and
analysis status. Films whose only editions are ignored are omitted. The
optional `q` query parameter filters the synchronous local search projection.

Primary edition selection is deterministic:

1. `available` before `missing` and `ignored`;
2. an edition with a present main video first;
3. `last_seen_at` descending;
4. LibraryItem ID ascending.

### `GET /library/films/{film_id}`

Returns `LibraryFilmDetail`, including every non-retired `LibraryEdition` for
the Film, selected structured metadata, profile state, scores and analysis
status.

Both Film endpoints read only versioned synchronous projections. Responses may
include `resolved_sources`, containing only source kind, observation time,
selection-policy version and conflict state. Missing or stale projections
return `503` with stable code `projection_unavailable`; the API does not fall
back to live Canonical joins.

### `GET /films/{film_id}/graph`

Returns a one-hop `FilmGraphView` assembled only from Graph read models. Under
`graph-visibility.v1`, the service includes Resolver-selected Director/Actor
Credits and active, accepted, factual Assertions. Proposed, rejected,
superseded and inferred Assertions are excluded server-side.

The response is bounded to 65 nodes and 64 edges, uses stable Genre/Director/
other-fact/Actor priority, and reports `truncated`, `visibility_policy` and
`projection_version`. Nodes expose only public identity and display fields;
edges expose public source kinds, review status, active Evidence count and
conflict state, never internal provenance references.

### `POST /library/items/{library_item_id}/refresh`

Queues `library.refresh_item`. The response is an accepted Job envelope.

### `POST /library/items/{library_item_id}/ignore`

Marks one edition ignored and returns the updated edition. Other editions and
the shared Film metadata/profile/analysis are unchanged.

### Scanning and lifecycle

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/library/scan` | Queue a full reconcile. |
| `POST` | `/library/reconcile` | Alias of the canonical reconcile command. |
| `POST` | `/library/scan-folder?folder_path=...` | Queue one controlled folder/file scan. |
| `GET` | `/library/sync/status` | Reconcile and watcher state. |
| `DELETE` | `/library/missing` | Retire missing LibraryItems. |
| `DELETE` | `/library` | Retire all LibraryItems but preserve Film-level data. |
| `DELETE` | `/library/data` | Delete domain data while retaining settings, migration journal and fixed references. |
| `POST` | `/library/seed` | Insert normal demonstration Films for local development. |

Scan and organizer Job payloads expose only stable IDs, counts and controlled
manifest references. Absolute paths are held in Git-ignored private manifests,
not public Job/Event payloads.

## Profile state and Viewing

### `GET /films/{film_id}/profile-state`

Returns one `FilmProfileState` with:

```json
{
  "film_id": "film_0123456789abcdef0123456789abcdef",
  "favorite": false,
  "rating": null,
  "notes": null,
  "watched": false,
  "watched_at": null,
  "updated_at": null
}
```

### `PUT /films/{film_id}/profile-state`

Accepts any subset of `favorite`, `rating` (1–5 or null), `notes` (up to 10,000
characters), `watched`, and `watched_at`.

- `watched=true` creates or restores a confirmed manual Viewing.
- `watched=false` revokes only the manual Viewing.
- Other confirmed sources, including future Diary entries, are preserved.
- Derived `watched` is true when any active confirmed Viewing exists.

### `GET /profile/watch-history`

Returns at most one entry per Film, ordered by the latest active confirmed
Viewing. Each entry embeds the Film summary and derived profile state.

## Metadata, artwork and external scores

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/metadata/search?query=...&year=...&language=...` | Search TMDB candidates. |
| `GET` | `/metadata/movie/{tmdb_id}` | Load one confirmation candidate. |
| `POST` | `/films/{film_id}/scrape` | Scrape one Film. |
| `POST` | `/films/{film_id}/scrape/confirm?tmdb_id=...` | Scrape with an explicit candidate. |
| `GET` | `/films/{film_id}/artwork` | List TMDB artwork options. |
| `PUT` | `/films/{film_id}/artwork` | Apply validated poster/backdrop paths. |
| `POST` | `/films/{film_id}/external-scores/refresh` | Queue one Film score refresh. |
| `POST` | `/library/external-scores/refresh` | Queue library-wide score refresh. |
| `GET` | `/library/external-scores/status` | Latest source refresh state. |
| `POST` | `/library/scrape` | Queue a batch metadata scrape. |
| `GET` | `/library/scrape/status` | Batch scrape status. |

TMDB requests require `TMDB_API_KEY` from the environment or managed setting.
The API never returns the key. External scores are normalized
`FilmExternalScore` resources rather than JSON stored on a library row.

## Root organizer

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/library/root-videos` | List videos directly under the media root. |
| `POST` | `/library/organize-root` | Queue automatic organization. |
| `POST` | `/library/organize-root/confirm` | Confirm one path and TMDB identity. |
| `GET` | `/library/organize/status` | Latest organizer status. |

File moves are bounded by the configured media root. Restorable moves reference
a private controlled manifest; the Event and OperationSnapshot store only its
opaque reference.

## Analysis V2

### `POST /films/{film_id}/analysis-runs`

Queues `analysis.analyze_film`. The runtime builds Canonical input, validates
`analysis-output.v2`, resolves entities and transactionally persists
AnalysisRun, Assertion, provenance, Evidence and resolution reviews.

### `GET /films/{film_id}/analysis`

Returns `FilmAnalysisView` assembled from the latest successful AnalysisRun and
active structured records. It contains a bounded summary, relations, Evidence,
reviews and status. Raw prompts/responses, hidden reasoning and compatibility
JSON are never stored or returned.

## Activity and operation restore

### `GET /activity/events`

Lists bounded `EventRecord` objects newest first. Optional filters are
`aggregate_type`, `aggregate_id`, `type`, `command_id`, `correlation_id`, and
`limit` (1–500). Canonical aggregate types include `film`, `library_item`,
`viewing`, `assertion`, `analysis_run`, and `workflow`.

### `GET /library/events`

Server-Sent Events stream for live invalidation and Workflow status notifications.

### `GET /operations/{snapshot_id}/preview`

Returns the bounded before/after diff, current-state match and a confirmation
token when restoration remains safe.

### `POST /operations/{snapshot_id}/restore`

Body:

```json
{"confirmation_token":"<64 lowercase hex>"}
```

Returns `409` if the current state has drifted, the token is stale, the snapshot
was already restored, or a controlled file restore is no longer safe.

## Durable workflows

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/workflows` | List sanitized workflows; optional `status`, `type`, `limit`. |
| `GET` | `/workflows/{workflow_id}` | Get a workflow and its ordered steps. |
| `POST` | `/workflows/{workflow_id}/cancel` | Cancel or request cancellation. |
| `POST` | `/workflows/{workflow_id}/retry` | Resume from the first failed/cancelled step. |

Long-running commands return:

```json
{
  "status": "queued",
  "message": "...",
  "workflow_id": "workflow_0123456789abcdef0123456789abcdef",
  "workflow": {}
}
```

Public Workflow/Step representations never include credentials, absolute paths,
raw model/provider output, titles used as privacy canaries, or full dedupe values.
The `job` table is an internal single-step execution queue and has no public API.

## Compatibility policy

This is a deliberate breaking baseline. The following endpoints do not exist:

- `/library/{movie_id}`
- `/library/user-states`
- `/watch-history`
- `/library/analyze/{movie_id}`
- `/analyze/{movie_name}`
- Movie timeline, projection rebuild and historical backfill endpoints

The generated OpenAPI document at `/docs` is authoritative for request-model
field details. Any route or response-shape change must update this document and
`skills/5x49-backend/SKILL.md` together.
