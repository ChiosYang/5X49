# 5X49 Product Roadmap

- Updated: 2026-08-26
- Product: self-hosted personal cinema knowledge and viewing system
- Current architecture: Fresh Canonical v1

## Product loop

```text
Import → Understand → Explore → Remember → Ask
```

5X49 serves people with a local movie/NFO collection who want a trustworthy,
explainable view of films, relationships and their own viewing history. It is
not a player, media server, downloader, social network or general chatbot.

## Current baseline

Complete:

- Next.js/React multilingual cinematic UI on port 5549.
- FastAPI/SQLModel embedded SQLite backend.
- Film as the canonical work and LibraryItem as a local edition.
- Deterministic multi-edition library list and details.
- NFO/TMDB metadata, artwork and source provenance.
- Person, Credit, Country and controlled Concept metadata.
- Film-level favorite/rating/notes and Viewing-derived watched history.
- Normalized external scores and refresh state.
- Durable Workflow/Step status, sanitized SSE and Activity events; Job is private execution state.
- Bounded OperationSnapshot preview/restore for supported commands.
- Analysis V2 persistence, entity resolution, Assertions, Evidence and reviews.
- Fixed 36-case Gate B evaluation tooling and adjudicated dataset.
- Fresh Canonical database epoch and resource API; historical compatibility is retired.

## Active quality gate

### Gate B — Analysis V2 quality

Status: **Blocked**.

Tooling and the frozen evaluation dataset are complete. A strict pass still
requires a 36-case live run against one exact model/pricing snapshot, successful
public Evidence validation, complete human helpfulness/relation review, cost and
privacy thresholds, idempotency/rejected-state protection and restore evidence.

No result may be called Passed while live or human evidence is missing. This
gate is independent of database migration and is the only architecture quality
gate currently carried forward from W4.

## Next delivery sequence

### 1. Fresh Canonical stabilization

Status: **Complete** for the local strict Gate. Docker remains separately
unavailable and live external smoke remains advisory.

- Complete desktop and 375px bilingual smoke coverage.
- Exercise scanning, missing/restore, multi-edition ordering and dangerous clear
  against generated media in an isolated database.
- Exercise snapshot preview/restore for metadata, artwork, availability and
  controlled file organization.
- Validate Docker first install when Docker is available.
- Keep privacy scans for Event, Workflow/Job, logs and quality reports in CI.

Exit: fresh first start is deterministic; no removed compatibility symbol or
table is reachable; media remains untouched during database cutover.

### 2. Provenance and synchronous read models

- centralize deterministic metadata selection and conflict reporting;
- add transactional Library, Detail, Search and Graph read models;
- provide offline projection verify/rebuild and strict stale-state handling.

Exit: product reads are reproducible, projection rebuild digests match and no
read model is treated as durable truth.

### 3. Factual Film Graph

- expose accepted factual Assertions and selected Credits on Film detail;
- ship a bounded accessible SVG plus list fallback;
- keep every inferred edge server-side hidden before Gate B.

Exit: factual Graph contract, accessibility, privacy and bounded traversal pass.

### 4. Durable workflows and constrained Analysis

- persisted Workflow steps now own reconcile, metadata and Analysis execution;
- retries, cancellation and crash recovery preserve completed step state;
- one Historian call now feeds deterministic resolution, policy criticism and
  Evidence verification shared by production and Gate B.

Exit: restart and retry cannot duplicate domain or external side effects.

### 5. Finish Gate B

- Resolve the public Evidence network preflight or document an approved product
  policy that changes the Evidence requirement.
- Run all 36 adjudicated cases with a pinned exact model and pricing manifest.
- Fill `analysis-eval-human-review.v1` for every successful case and new relation.
- Run strict `conclude` and publish only the redacted quality summary.

Exit: every `gate-b-policy` threshold passes and Gate B is explicitly recorded
as Passed.

### 6. Reviewed inferred Graph

Only after Gate B passes:

- film detail graph using accepted factual and reviewed inferred Assertions;
- relation Evidence and review-state inspection;
- clear distinction between owned and non-owned Films;
- bounded traversal and accessible non-graph fallback.

Graph UI is additionally subject to its own product/accessibility/performance
acceptance. A quality-gate pass does not automatically ship it.

### 7. Local-first portability, Diary and Explore

- deterministic `library-export.v1` export and validation are complete;
- multiple explicit Viewing records and diary editing;
- Explore by the most reliable dimensions: genre, person, country/decade;
- explainable Cinema DNA based on accepted facts and user Viewing data;
- local-first export/backup and setup health.
- keep multi-device synchronization out of scope until a separate conflict and
  security contract exists.

### 8. Ask MVP

- database/graph performs strict filtering and entity lookup;
- the model structures intent and explains already selected results;
- constraints are never silently relaxed;
- private paths, notes and secrets are excluded from provider input by default.

## Engineering principles

- One canonical schema and one resource API; no dual read/write path.
- Film identity never depends on a localized title or filesystem path.
- LibraryItem owns availability and media; Film owns shared knowledge/state.
- Viewing is a fact; watched is derived.
- Structured facts, external Evidence and model inference remain distinct.
- Accepted/rejected user decisions survive automatic refresh and re-analysis.
- Background tasks are idempotent and expose sanitized public state.
- Destructive and restorative operations use preview, confirmation and state hashes.
- No database or model quality claim without reproducible evidence.

## Out of scope until evidence demands it

- multi-user accounts and cloud sync;
- TV/music libraries;
- playback, streaming or transcoding;
- Neo4j or another dedicated graph database;
- autonomous multi-agent library mutation;
- paid subscriptions and licensing;
- Jellyfin/Plex write integration;
- whole-library automatic analysis without cost controls.
