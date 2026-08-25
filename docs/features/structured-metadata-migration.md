# Structured Metadata Migration

Status: In Progress
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
- Backfill supported legacy metadata deterministically in a later slice.
- Keep NFO and TMDB observations synchronized with Canonical metadata in a
  later slice without widening legacy response shapes.
- Preserve raw field-local values for unresolved metadata while keeping paths,
  credentials, and whole source documents out of review records and reports.

## Non-goals

- Film-to-Concept persistence before W4 factual Assertions.
- Assertion, Evidence, AnalysisRun, Graph API, Graph UI, or merge UI.
- Full cast/crew ingestion, Theme/Movement inference, ExternalScore, Studio, or
  Collection normalization.
- Any HTTP API, frontend, or legacy Movie response change.

## Existing behavior

Canonical Film, LibraryItem, MediaAsset, Viewing, and the legacy compatibility
layer are implemented through schema version 5; Slice 1 adds the schema-only
structured metadata foundation in version 6. Legacy Movie still owns
localized title, country names, director text, actor name/role dictionaries,
and genre strings. TMDB person and genre identifiers are currently discarded
when the legacy projection is assembled. Gate A remains blocked on naturally
aged private-library and Docker evidence; this W3 work is not part of that
Gate's pass criteria and does not authorize Graph UI.

## Acceptance criteria

- [x] Existing and fresh databases reach schema version 6 idempotently.
- [x] Person names are not unique; exact external identities remain unique.
- [x] Source-scoped provisional identities never expose the source name or a
  person name in their stable identifier.
- [x] Credit, title, country, alias, provenance, and review records have stable
  deduplication rules and restrictive foreign keys.
- [x] Full data clear removes structured metadata in dependency order while
  ordinary Library clear preserves Film-level metadata.
- [x] Legacy API routes and payload fields remain unchanged.
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

## Open questions

- None for Slice 1. Genre vocabulary contents and source precedence are locked
  before Slice 2 starts.

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

Status: Pending

- Intended behavior: backfill FilmTitle, FilmCountry, source-scoped Person,
  Credit, the controlled Genre dictionary, aliases, provenance, and review
  records from legacy Movie rows without persisting Film-to-Concept edges.
- Likely affected areas: a versioned/resumable backfill service, migration
  reports, fixtures, and consistency checks.
- Dependencies: Slice 1 and an adopted Genre vocabulary/source precedence.
- Verification: stable-order reruns, same-name people, multi-director input,
  country mapping, ambiguous aliases, provenance supersession, and privacy.

### Slice 3 — NFO and TMDB runtime synchronization

Status: Pending

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

Status: Pending

- Intended behavior: produce a privacy-safe consistency report and make the
  structured metadata foundation ready for W4 Assertion persistence.
- Likely affected areas: audit tooling, Domain Model, Roadmap, and quality
  evidence.
- Dependencies: Slices 1–3.
- Verification: fixture and curated-library rehearsal, unresolved review
  accounting, no orphan entities/provenance, and an explicit W3 conclusion.

## Verification evidence

- `.\.venv\Scripts\python.exe -m unittest test_structured_metadata_schema.py test_database_migrations.py test_database_restore.py test_canonical_schema.py test_canonical_runtime.py test_gate_a.py`
  — 53 focused tests passed on 2026-08-25.
- Complete backend unittest set except credential-dependent `test_agent.py` —
  135 tests passed on 2026-08-25 in 58.698 seconds.
- `.\.venv\Scripts\python.exe -m compileall -q app scripts test_structured_metadata_schema.py test_database_migrations.py test_canonical_runtime.py test_gate_a.py`
  — passed.
- `.\.venv\Scripts\python.exe -m app.migrations.gate_a rehearse --input-dir data/gate-a/input --run-dir data/gate-a/runs/structured-metadata-v6-20260825`
  upgraded to schema v6 and
  passed every local phase with the source unchanged. Docker and overall status
  remain Blocked.

## Remaining risks

- Existing NFO parsing retains only one director and a bounded actor list;
  Slice 3 must introduce an internal observation shape without changing the
  legacy API.
- Source-instance reuse can still conflate two people with the same normalized
  name inside one source. They remain provisional and reviewable until an exact
  identity or manual merge decision exists.
- Gate A is independently Blocked and Graph UI remains prohibited.
