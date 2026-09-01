# 5X49 Product Roadmap

- Updated: 2026-08-31
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
- Inline first-run media-directory setup, scanning and recovery for an empty Library.
- Reviewable root/inbox file organization with exact preview, confirmation and restore boundaries.
- Fresh Canonical local strict stabilization Gate with bilingual desktop and mobile evidence.
- GitHub Actions backend and frontend checks on `main` pushes and pull requests.

## In delivery

Diary is complete on its feature branch: multiple independent Viewing facts,
bilingual timeline, and latest-per-Film recent-view semantics
have passed local backend, frontend, and browser checks. It moves into the
completed baseline after the authorized `main` push passes both CI jobs.

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

### 1. Factual Explore

- Explore the local Library by accepted genre, person, country and decade facts.
- Reuse synchronous read models and factual Graph visibility; do not require a
  model call or expose inferred edges.
- Make active filters and provenance understandable and deterministic.

Exit: a user can move from a trusted fact or Graph node to a reproducible Film
set without silently relaxed constraints.

### 2. Ask MVP

- Let the model structure intent while the database and Graph perform strict
  filtering and entity lookup.
- Explain already selected results and the constraints that produced them.
- Exclude private paths, notes and secrets from provider input by default.

Exit: Ask is a bounded interface over trusted local facts, not an autonomous
database or filesystem agent.

### Parallel quality track — Finish Gate B

- Resolve the public Evidence network preflight without weakening the SSRF boundary.
- Run all 36 adjudicated cases with one pinned model and pricing manifest.
- Complete human review, restore, idempotency, cost and privacy evidence.
- Run strict `conclude` and publish only the redacted quality summary.

Only a Passed conclusion may release accepted inferred Graph edges. Gate B does
not block Diary, factual Explore, export or deterministic local queries.

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
