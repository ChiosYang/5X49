# 5X49 Canonical Event Contracts

- Status: Adopted
- Contract version: `fresh-canonical-events.v1`

## Purpose

EventRecord is a durable, bounded audit trail for commands against canonical
resources. It supports Activity, correlation and OperationSnapshot causation.
It is not a complete event-sourcing log and is never replayed to reconstruct a
deleted database.

## Envelope

Every event has:

| Field | Contract |
| --- | --- |
| `id` | Opaque `evt_` ID. |
| `type` | Stable event type. |
| `aggregate_type` | `film`, `library_item`, `viewing`, `assertion`, `analysis_run`, `job`, `library`, or `operation`. |
| `aggregate_id` | Stable canonical resource ID. |
| `payload` | Bounded JSON with allowlisted fields. |
| `actor_type` | `system`, `user`, or bounded runtime actor. |
| `command_id` | Optional command correlation ID. |
| `correlation_id` | Optional multi-step operation ID. |
| `causation_id` | Optional source event ID for a compensation event. |
| `occurred_at` | UTC timestamp. |

The state mutation and EventRecord are committed in the same SQLModel Session.
If either write fails, neither commits.

## Privacy boundary

Event payloads must not contain:

- absolute paths or file URIs;
- API keys, authorization headers, userinfo or secret query parameters;
- raw NFO/XML, raw model input/output, provider exception bodies or webpage content;
- full before/after domain objects;
- titles solely for Activity display.

Activity resolves display titles from the current Film/LibraryItem. File
operations store only stable resource IDs, counts, state names, content hashes
or opaque private manifest references.

## Library and metadata events

| Event | Aggregate | Bounded payload intent |
| --- | --- | --- |
| `LibraryItemDiscovered` | `library_item` | `film_id`, availability. |
| `LibraryItemObserved` | `library_item` | `film_id`, availability. |
| `LibraryItemMarkedMissing` | `library_item` | `film_id`, missing timestamp. |
| `LibraryItemRestored` | `library_item` | `film_id`, availability. |
| `LibraryItemIgnored` | `library_item` | `film_id`, resulting status. |
| `LibraryCleared` | `library` | retired count. |
| `LibraryDataCleared` | `library` | bounded deleted-count map. |
| `MissingLibraryItemsCleaned` | `library` | retired count. |
| `MetadataMatchSuggested` | `film` | candidate count, optional best provider ID and confidence. |
| `MetadataMatched` | `film` | Film/LibraryItem IDs, provider ID, bounded options and changed-field count. |
| `MetadataScrapeFailed` | `film` | stable error category/code only. |
| `ArtworkSelected` | `film` | selected-kind booleans and LibraryItem ID. |
| `ArtworkDownloaded` | `film` | asset-kind booleans/counts; no URL or path. |
| `NfoWritten` | `library_item` | write/backup booleans; no path or document. |
| `RootVideoOrganized` | `library_item` | Film/LibraryItem IDs and controlled manifest reference. |

Routine repeated observation may be omitted when it would add no audit value.
Reconcile remains idempotent and does not emit path-rich per-file diagnostics.

## Profile and Viewing events

| Event | Aggregate | Payload |
| --- | --- | --- |
| `FilmProfileStateUpdated` | `film` | changed field names and derived watched state. |
| `ViewingConfirmed` | `viewing` | Film ID, source and bounded timestamp. |
| `ViewingRevoked` | `viewing` | Film ID and source. |

Notes and free-form review text are not copied into EventRecord.

## Analysis and score events

| Event | Aggregate | Payload |
| --- | --- | --- |
| `AnalysisStarted` | `analysis_run` | Film ID, run ID and version identifiers. |
| `AnalysisCompleted` | `analysis_run` | Film/run IDs and bounded counts/status. |
| `AnalysisFailed` | `analysis_run` | stable category/code and bounded safe message. |
| `ExternalScoresRefreshed` | `film` | source, score count and refresh status. |
| `ExternalScoresRefreshFailed` | `film` | source and stable safe error code. |

No Analysis event contains candidate relations, raw output, Evidence body or
hidden reasoning. Those are queried from validated structured tables.

## Operation snapshots and compensation

A supported command can attach one `OperationSnapshot` to its EventRecord. The
snapshot stores a bounded allowlisted before/after state and the after-state
hash. Preview is read-only and returns a confirmation token only when current
state still matches.

`OperationRestored` uses `aggregate_type=operation`, includes only snapshot ID,
operation kind and target resource, and points `causation_id` at the original
event. Restoration never deletes or rewrites the source event.

File organization restoration requires an opaque controlled manifest. The
manifest is private operational data under the ignored data directory. A move
is rejected if source/target escape the configured media root, the target was
replaced, the original path is occupied or any sidecar state conflicts.

## Live events

`GET /library/events` is a separate in-memory/SSE invalidation stream. Its
events include `connected`, `library_changed`, Job lifecycle notifications and
`heartbeat`. The stream is not a durable audit source and follows the same
privacy boundary.

## Change rules

- Add a new event type only when Activity, diagnosis or restoration needs it.
- Keep payloads versionable, bounded and identity-based.
- Never introduce resource snapshots for convenience.
- Add a regression test for atomic commit and sensitive-data exclusion when a
  new write command begins emitting events.
- Update this document with any material event meaning or payload change.
