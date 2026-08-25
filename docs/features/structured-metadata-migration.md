# Structured Metadata Migration

Status: Done
Last updated: 2026-08-25
Related: W3 in `docs/product-roadmap.md`, `docs/domain-model.md`,
`docs/analysis-v2-contract.md`

## Goal

Normalize titles, countries, people, credits, and the controlled Concept
dictionary without changing the legacy Library API. Establish the trusted
factual metadata needed before W4 persists Graph Assertions.

## Scope

- Add FilmTitle, FilmCountry, Person, Credit, Concept, provenance, and review
  schema through additive migration version 6.
- Backfill supported legacy metadata deterministically through data migration
  version 7 and the versioned Genre/Country vocabulary.
- Keep NFO and TMDB observations synchronized with Canonical metadata without
  widening legacy response shapes.
- Preserve raw field-local values for unresolved metadata while keeping paths,
  credentials, and whole source documents out of review records and reports.
- W4 version 9 now consumes the completed Genre observations to materialize
  factual Assertions without changing the W3 contract or conclusion.

## Non-goals

- Film-to-Concept persistence before W4 factual Assertions.
- Assertion, Evidence, AnalysisRun, Graph API, Graph UI, or merge UI.
- Full cast/crew ingestion, Theme/Movement inference, ExternalScore, Studio, or
  Collection normalization.
- Any HTTP API, frontend, or legacy Movie response change.

## Existing behavior

Canonical Film, LibraryItem, MediaAsset, Viewing, and the legacy compatibility
layer are implemented through schema version 7. Version 6 introduced the
schema-only structured metadata foundation; version 7 deterministically
backfills legacy titles, countries, people, credits, the controlled Genre
dictionary, provenance, and bounded review records. NFO and TMDB refreshes now
write the same structures transactionally while Legacy Movie remains the
unchanged compatibility projection. Gate A remains blocked on naturally aged
private-library and Docker evidence; W3 completion is not part of that Gate's
pass criteria and does not authorize Graph UI.

W4 data migration version 9 and the runtime synchronizer now consume the W3
Genre observations as factual `HAS_GENRE` Assertions. This is a downstream W4
capability and does not retroactively expand W3 or Gate A acceptance criteria.

## Acceptance criteria

- [x] Existing and fresh databases reach schema version 6 idempotently.
- [x] Existing and fresh databases reach data migration version 7; rerunning
  the structured backfill creates no additional records.
- [x] Person names are not unique; exact external identities remain unique.
- [x] Source-scoped provisional identities never expose the source name or a
  person name in their stable identifier.
- [x] Credit, title, country, alias, provenance, and review records have stable
  deduplication rules and restrictive foreign keys.
- [x] Full data clear removes structured metadata in dependency order while
  ordinary Library clear preserves Film-level metadata.
- [x] Legacy API routes and payload fields remain unchanged.
- [x] NFO and TMDB observations update Canonical structured metadata in the
  same transaction as Event and Legacy projections.
- [x] Source refreshes supersede only their own provenance; selected values use
  `curated > NFO > TMDB > Legacy/filename`.
- [x] The isolated W3 rehearsal passes consistency, idempotence, lifecycle, and
  privacy checks without changing its source database or media root.
- [x] Gate A remains Blocked until its independent strict evidence is complete.

## Decisions

- Exact provider identities such as `tmdb.person` may reuse Person. A person
  without one is provisional and is reused only within one source instance by
  a hash of `source_instance_id + normalized_name`; names alone never merge
  people across sources.
- Normalization is NFKC, surrounding-whitespace removal, internal-whitespace
  collapse, and case folding. It does not strip punctuation or diacritics.
- Credit is the canonical Film/Person relation. Multiple observations attach
  provenance to one semantic Credit; a source refresh supersedes only that
  source's observations and never curated provenance.
- Concept supports `genre`, `theme`, `movement`, `visual_style`, and
  `micro_genre`. W3 backfills only the controlled Genre dictionary and aliases.
- W3 does not add FilmConcept or persist Assertion. Film-to-Genre becomes a
  factual Assertion in W4; legacy `Movie.genres` remains the compatibility
  source until then.
- FilmTitle stores canonical, original, localized, and alternative values with
  source ownership. Film.canonical_title remains the selected display value.
- FilmCountry accepts uppercase ISO 3166-1 alpha-2 only. Unknown or ambiguous
  names remain bounded raw review values rather than becoming stable IDs.
- Provenance references are stable opaque LibraryItem, Film, or provider record
  identifiers. Absolute paths are forbidden.
- Migration version 6 is schema-only: it performs no network access, file
  access, dictionary seeding, or legacy data backfill.
- Migration version 7 is data-only. It seeds `tmdb-movie-genres:v1` with the 19
  TMDB Movie Genre concepts and aliases, uses the bundled ISO 3166-1 alpha-2
  vocabulary, and backfills legacy rows in stable Movie ID order without
  network or media access.
- Unknown Genre values never create ad-hoc Concept rows. Unknown countries,
  invalid credits, and unmapped genres create source-owned review records.
- Runtime source precedence is `curated > NFO > TMDB > legacy_movie >
  filename`. A refresh supersedes only records owned by the same source and
  source reference.

## Open questions

- None for W3. Film-to-Genre edges remain a W4 factual Assertion decision.

## Slices

### Slice 1 — Boundary contract and schema v6

Status: Complete

- Intended behavior: create the additive structured-metadata schema,
  deterministic key helpers, lifecycle integration, tests, and documentation.
- Likely affected areas: Canonical models, migration registry, full-data clear,
  migration/Gate tests, and W3 documentation.
- Dependencies: Canonical Migration Slices 1–4; no Gate A pass required.
- Verification: schema constraints, legacy fixture matrix, fresh create_all,
  backup/restore, clear semantics, backend suite, and a non-gating local Gate A
  regression rehearsal.

### Slice 2 — Deterministic legacy backfill

Status: Complete

- Intended behavior: backfill FilmTitle, FilmCountry, source-scoped Person,
  Credit, the controlled Genre dictionary, aliases, provenance, and review
  records from legacy Movie rows without persisting Film-to-Concept edges.
- Likely affected areas: a versioned/resumable backfill service, migration
  reports, fixtures, and consistency checks.
- Dependencies: Slice 1 and an adopted Genre vocabulary/source precedence.
- Verification: stable-order reruns, same-name people, multi-director input,
  country mapping, ambiguous aliases, provenance supersession, and privacy.

### Slice 3 — NFO and TMDB runtime synchronization

Status: Complete

- Intended behavior: retain raw provider person/genre/country identifiers in an
  internal observation contract and synchronize structured metadata in the same
  transaction as Canonical/legacy metadata updates.
- Likely affected areas: scanner observations, TMDB scrape projection,
  Canonical writer, and compatibility rebuild.
- Dependencies: Slice 2 stable backfill and difference report.
- Verification: refresh idempotence, exact provider reuse, source-local
  provisional reuse, stale-source supersession, curated preservation, and
  rollback on either projection failure.

### Slice 4 — W3 consistency and handoff

Status: Complete

- Intended behavior: produce a privacy-safe consistency report and make the
  structured metadata foundation ready for W4 Assertion persistence.
- Likely affected areas: audit tooling, Domain Model, Roadmap, and quality
  evidence.
- Dependencies: Slices 1–3.
- Verification: fixture and curated-library rehearsal, unresolved review
  accounting, no orphan entities/provenance, and an explicit W3 conclusion.

## Verification evidence

- The ignored raw rehearsal `w3-20260825-02` upgraded the fixed offline input
  to v7 and passed every W3 upgrade, backfill, consistency, runtime, lifecycle,
  privacy, and source-immutability check. The Git-safe summary is
  `docs/quality/structured-metadata-w3.md`.
- The versioned TMDB fixture and synthetic tests cover exact Person identity,
  source precedence, same-observation no-op behavior, source-owned
  supersession, NFO compatibility output, review lifecycle, and transactional
  rollback without network access.
- Complete backend unittest discovery excluding credential-dependent
  `test_agent.py` passed 160 tests on 2026-08-25 in 83.456 seconds after
  integration with the TMDB safe-concurrency changes.
- The final 55-test W3/migration/metadata/TMDB-concurrency focused run passed.
  The earlier 30-test W3-focused run also passed with `ResourceWarning`
  promoted to an error, and `compileall` passed for the app, scripts, and
  affected test modules.
- Gate A remains Blocked independently; its local regression is recorded in
  `docs/quality/canonical-gate-a.md`.

## Remaining risks

- Legacy responses intentionally retain one director and five actors while the
  internal NFO observation retains all directors and the first ten actors.
- Versioned runtime observations intentionally stop at ten actors; full
  cast/crew ingestion remains outside W3.
- Source-instance reuse can still conflate two people with the same normalized
  name inside one source. They remain provisional and reviewable until an exact
  identity or manual merge decision exists.
- Gate A is independently Blocked and Graph UI remains prohibited.
