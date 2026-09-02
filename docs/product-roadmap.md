# 5X49 Product Roadmap

- Updated: 2026-09-02
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
- Factual Explore Schema v4 read models, strict Genre/Person/Country/Decade
  semantics, progressive Lens UI and the Passed 200/1,000-Film engineering gate.
- GitHub Actions backend and frontend checks on `main` pushes and pull requests.

## In delivery

None. The next committed delivery is W9 Cinema DNA V1; implementation starts
only after its formula and evidence contract are frozen.

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

### 1. W9 — Cinema DNA V1

- Compute exposure and preference from accepted local facts, Film state and
  confirmed Viewings with a deterministic, versioned formula.
- Show sample size, calculation basis and contributing Films/Viewings; report
  insufficient evidence instead of presenting a false-precision profile.
- Keep the baseline available without an AI key and do not use an LLM or Agent
  to calculate or mutate Cinema DNA.

Exit: Cinema DNA is a transparent, reproducible local statistic whose inputs
and limitations remain visible to the user.

### 2. W10 — Ask MVP

- Let the model structure intent while the database and Graph perform strict
  filtering and entity lookup.
- Explain already selected results and the constraints that produced them.
- Exclude private paths, notes and secrets from provider input by default.

Exit: Ask is a bounded interface over trusted local facts, not an autonomous
database or filesystem agent.

### 3. W11 — RC stabilization

- Freeze feature expansion and verify upgrade, backup, restore preview, complete
  restore, diagnostics and projection rebuild behavior.
- Exercise no-key, read-only directory, low-disk and external-provider failure
  paths; clear blocker and high-priority defects before release candidacy.

Exit: core data and the Import → Understand → Explore → Remember → Ask loop
remain reliable through supported failures and upgrades.

### 4. W12 — Public Beta and validation

- Open recruitment only after the Beta Ready gate passes, with installation,
  privacy, diagnostics and known-issue guidance in place.
- Use real activation, trust, repeated-core-behavior and safety evidence to
  decide whether to continue, focus, delay or contract the product.

Exit: Beta is an evidence-based product decision, not a date-driven launch;
W13–W14 retention tracking is prepared without claiming results early.

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
