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
| `GET/PUT` | `/settings/media-dir` | Local media root and non-secret availability. `PUT` requires an existing readable directory and applies immediately without an application restart. |
| `GET` | `/media/{relative_path}` | Serve a file from the current media root with traversal and symlink-escape protection. |
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

`GET /settings/media-dir` returns the configured path without enumerating its
contents or exposing settings secrets:

```json
{
  "media_dir": "/media",
  "exists": true,
  "readable": true
}
```

`readable` is true only when the path exists, is a directory, and is readable by
the backend process. A successful `PUT` includes the same three fields plus its
existing `status` and `message` fields. Invalid targets return `400` with an
actionable `detail` string.

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

## Factual Explore

All Explore routes read only the synchronous Schema v4 Explore projections and
use visibility policy `factual-explore.v1`. They never invoke a model, generate
similar results, relax constraints, or fall back to Canonical live joins. A
missing or stale Library/Explore projection returns `503` with stable code
`projection_unavailable`.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/explore` | Return visible Film total, per-dimension coverage and the top 12 facets. |
| `GET` | `/explore/context` | Return deterministic next-step factual clues for the current strict query. |
| `GET` | `/explore/facets/{dimension}` | Search and paginate one `genre`, `person`, `country`, or `decade` facet set. |
| `GET` | `/explore/films` | Return the reproducible strict intersection selected by repeated fact filters. |

`GET /explore` separates each dimension into `covered_films`,
`conflicted_films`, and `missing_films`. Each facet includes owned, watched and
unwatched Film counts, merged Person roles, and safe source kinds. Top facets
sort by Film count descending, normalized label ascending, then stable facet
key. Responses identify both registered projections
(`factual-explore-film.v1` and `factual-explore-facet.v1`).

`GET /explore/context` accepts the same repeated Genre, Person, Country and
Decade filters as `/explore/films`, plus `view=all|watched|unwatched` and
`limit` (default 6 per dimension, 1–12). It returns `current_total` and one
entry for each dimension:

- when that dimension is empty, `operator=and` and each clue's `result_count`
  is the exact strict total after adding it;
- when that dimension already has a selected value, `operator=or` and
  `additional_count` is the number of Films newly admitted by that clue;
- selected and ineligible facets are excluded, ordering is deterministic, and
  `has_more` indicates that Fact Finder can reveal more than the returned
  clues.

Each clue may include one deterministic `preview_film` drawn from the clue's
actual contribution set. OR clues prefer a newly added Film. Preview selection
prefers safe local thumbnails, then provider artwork, then a stable no-artwork
fallback. The response copies only public Film identity and the existing
Library read model's six safe artwork fields. Context calculation performs
fixed bulk reads rather than one query per facet, and preserves the same
unresolved, conflict, privacy and `503 projection_unavailable` semantics as the
other Explore endpoints.

`GET /explore/facets/{dimension}` accepts optional `q` (at most 100
characters), `limit` (default 30, 1–100), and non-negative `offset`. The
response includes `total`, `next_offset`, and the complete coverage summary for
that dimension. Person Directors and Actors share one facet collection; roles
are returned as `director` and/or `actor`.

`GET /explore/films` accepts repeated Canonical `genre=con_<id>` (and
normalizes the longer `concept_<id>` spelling),
`person=person_<id>`, `country=<ISO alpha-2>`, and `decade=<four-digit decade>`
parameters, with at most 20 unique values per dimension. It also accepts:

- `view=all|watched|unwatched` (default `all`);
- `sort=title|year` (default `title`);
- `dir=asc|desc` (default `asc` for title and `desc` for year);
- `limit` (default 40, 1–100) and non-negative `offset`.

Values are deduplicated and sorted. Values within one dimension are ORed;
non-empty dimensions and the Viewing-derived watched state are ANDed. Empty
release years never match a decade. Malformed values return `422`. A validly
formatted but missing, deleted, conflicted, or otherwise unavailable facet is
preserved in `unresolved_filters`. A dimension containing only unresolved
values therefore matches zero Films; it is never removed from the query.

The Film response includes normalized `active_filters`, display-ready filter
details, `unresolved_filters`, strict total/pagination fields, public
`LibraryFilmSummary` rows, and each Film's actually matched facts. Matched facts
expose only dimension, stable key, label, Person roles, safe source kind and
selection policy, or `release-year-decade.v1` derivation. Sorting always uses
Film ID as the final tie-breaker.

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
| `GET` | `/library/missing` | List path-safe summaries for every missing LibraryItem. |
| `DELETE` | `/library/missing` | Retire missing LibraryItems. |
| `DELETE` | `/library` | Retire all LibraryItems but preserve Film-level data. |
| `DELETE` | `/library/data` | Delete domain data while retaining settings, migration journal and fixed references. |
| `POST` | `/library/seed` | Insert normal demonstration Films for local development. |

Scan and organizer Job payloads expose only stable IDs, counts and controlled
manifest references. Absolute paths are held in Git-ignored private manifests,
not public Job/Event payloads.

`GET /library/missing` returns `{ count, items }`. Each item contains only
`library_item_id`, `film_id`, selected Film title/year, `display_name`, and
`missing_since`, sorted by missing time, title, and LibraryItem ID. It never
returns a source key, media locator, or absolute path.

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
  "manual_watched": false,
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
- Derived `manual_watched` is true only while the singleton quick-toggle Viewing
  is active. Clients use it to avoid overwriting Diary-only watched state.

### Diary

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/profile/viewings?view=timeline|recent&limit=100&offset=0&film_id=...` | Return the complete timeline or one latest Viewing per Film; `film_id` is optional. |
| `GET` | `/films/{film_id}/viewings` | Return every active confirmed Viewing for one Film. |
| `POST` | `/films/{film_id}/viewings` | Create a new confirmed Diary Viewing. |
| `PATCH` | `/viewings/{viewing_id}` | Change only the Viewing date/precision. |
| `DELETE` | `/viewings/{viewing_id}` | Idempotently soft-delete one editable Viewing. |

Create and update requests use `{"watched_at": ...}`. Accepted values are an
exact `YYYY-MM-DD` date, a four-digit year, a timezone-aware RFC 3339 timestamp,
or `null` for unknown. Duplicate dates remain independent records. Manual and
Diary sources are editable; other sources return `409` with code
`viewing_read_only`.

`GET /profile/viewings` returns `items`, `total`, `limit`, `offset`, and
`next_offset`. Each item contains the Viewing, a lightweight Film identity with
`in_library`, and the derived Film profile state. `view=timeline` is the default
and returns every active confirmed Viewing. `view=recent` selects the latest
Viewing for each Film before pagination. Known dates sort descending, unknown
dates sort last, and the default/maximum page sizes are 100/200.

## Metadata, artwork and external scores

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/metadata/search?query=...&year=...&language=...` | Search TMDB candidates. |
| `GET` | `/metadata/movie/{tmdb_id}` | Load one confirmation candidate. |
| `POST` | `/films/{film_id}/scrape` | Scrape one Film. |
| `GET` | `/films/{film_id}/scrape/candidates?language=...` | Find bounded TMDB candidates without changing Film, edition, Event, or file state. |
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
Candidate lookup requires an available edition with a present video locator and
returns an empty array when TMDB has no matches. It never marks the Film as
reviewed or writes metadata; confirmation remains an explicit `POST`.

## File organization

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/library/organization/candidates` | List direct-root and legacy-inbox videos using relative source paths. |
| `POST` | `/library/organization/preview` | Resolve one TMDB identity and preview the exact file plan without writes. |
| `POST` | `/library/organization/confirm` | Revalidate a preview token and queue one confirmed file plan. |
| `GET` | `/library/root-videos` | Deprecated compatibility view for direct-root videos. |
| `POST` | `/library/organize-root` | Queue explicitly enabled automatic root-only organization. |
| `GET` | `/library/organize/status` | Latest organizer status. |

`POST /library/organization/preview` accepts:

```json
{"source_path":"inbox/Messy.Name.1999.mkv","tmdb_id":603,"rename_style":"preserve_stem"}
```

The response contains the source summary, selected TMDB candidate, target folder
and video name, sidecar plan, post-actions, conflicts, `can_confirm`, and a
64-character `confirmation_token`. It never returns an absolute source path and
does not create directories, move files, or write metadata.

Confirmation repeats the preview body and adds its token. A stale source,
changed identity or rename style, or a new target conflict returns `409` before
enqueue. The Workflow validates the same token again before moving anything.
Unsupported, nested, or escaping paths return `400`; a missing source returns
`404`. Manual confirmation never overwrites target video or sidecar files.

Confirmed files may come directly from the media root or its direct `inbox`
child. Automatic organization remains root-only. Restorable moves reference a
private controlled manifest; the Event and OperationSnapshot store only its
opaque reference. File-location restore covers the video, associated sidecars,
and database locator; generated NFO and artwork files remain.

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
- `/profile/watch-history`
- `/library/analyze/{movie_id}`
- `/analyze/{movie_name}`
- Movie timeline, projection rebuild and historical backfill endpoints

The generated OpenAPI document at `/docs` is authoritative for request-model
field details. Any route or response-shape change must update this document and
`skills/5x49-backend/SKILL.md` together.
