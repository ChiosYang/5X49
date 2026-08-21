# Local Anonymous Product Event Contract

Status: Adopted contract; no automatic upload is implemented.

The executable schemas live in `backend/app/contracts/anonymous_events.py`.
They define locally stored, low-sensitivity product events and the only format
eligible for a user-initiated anonymous metrics export.

## Local events

Allowed events cover installation, import, first Film open, analysis, Graph,
Viewing, Explore, Ask, and application reopen. Their properties are a closed
set of result categories, capability/source enums, bounded counts, bounded
durations, attempt number, and offline-mode flag.

The contract cannot contain Movie/Film/LibraryItem IDs, titles, paths, provider
IDs, Viewing timestamps, ratings, reviews, notes, prompts, model output, API
keys, or arbitrary dictionaries. Event and session IDs are random anonymous
IDs used only for local deduplication and session grouping.

Events stay local by default. They are not reused as domain events, audit
events, or an event-sourcing stream and must not be added to the `events` table.

## Explicit anonymous export

`AnonymousMetricsExport` uses `anonymous-metrics-export.v1` and requires
`consent=explicit_user_export`. It contains only a time window, application and
platform family, aggregate funnel counters, and aggregate failure categories.
Raw local events and their timestamps are not exported.

There is no background sender, installation fingerprint, account identifier,
or default network destination. Implementing collection or transport later
requires a separate privacy review, retention decision, UI consent flow, and
contract test proving that arbitrary properties are still rejected.
