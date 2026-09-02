# 5X49 Fresh Canonical Domain Model

- Status: Adopted
- Database epoch: `fresh-canonical-v1`
- Schema version: `4`

## Boundaries

5X49 has one durable model. It does not keep an older Movie read model, alias
table, dual writer, shadow reader or compatibility projection.

```text
Film (one cinematic work)
├─ ExternalIdentity (TMDB, IMDb, provider identity)
├─ FilmTitle / FilmCountry
├─ Credit → Person
├─ LibraryItem (one local edition/source item)
│  ├─ LocatorHistory
│  └─ MediaAsset
├─ FilmProfileState (favorite, rating, notes)
├─ Viewing (one viewing fact)
├─ FilmExternalScore
└─ AnalysisRun
   ├─ Assertion → GraphEntity
   ├─ Evidence
   └─ AnalysisResolutionReview
```

Film is the public identity used by pages and Film-level APIs. LibraryItem is a
specific owned edition and is used only when an operation targets a local
version. Several LibraryItems may share one Film and therefore share profile
state, structured metadata, scores and analysis.

## Knowledge architecture layers

Fresh Canonical remains the sole source of truth while the product grows four
explicit derived layers:

1. provenance resolution selects current display values and reports conflicts;
2. synchronous CQRS read models serve Library, Detail, Search, factual Explore
   and Graph;
3. durable workflows coordinate long-running external and filesystem work;
4. the constrained Analysis pipeline proposes reviewable knowledge.

Read models, Workflow state and portable exports are not domain facts. They
cannot overwrite Canonical records and must not be used as fallback truth.
EventRecord remains audit-only. The staged contract is maintained in
`docs/features/cinema-knowledge-architecture.md`.

Factual Explore has two rebuildable Schema v4 projections. The Film projection
contains only visible Library membership, stable sorting fields, release year
and Viewing-derived watched state. The facet projection contains Resolver-
selected accepted factual Genre, Director/Actor Person, ISO Country, and Decade
derived from release year. Resolver-conflicted collection facts remain
countable for review coverage but are ineligible for public facet/result
queries. These rows are not portable facts and may always be discarded and
rebuilt from Canonical state.

## Graph identity

`GraphEntity` supplies the stable identity and entity kind for Film, Person and
Concept. All domain IDs are opaque prefix UUIDs; names, paths and provider IDs
are not embedded in IDs.

`ExternalIdentity` is the only exact provider identity binding. Active provider
identities are unique. Identity conflicts do not merge by title; they create a
bounded `IdentityReview` associated with Film and optionally LibraryItem.

## Library and media

`LibraryItem` owns source instance, stable source key, lifecycle and availability:

- `available`: seen and usable;
- `missing`: source temporarily absent;
- `ignored`: intentionally excluded from the list and bulk work;
- `retired`: no longer an active edition.

`LocatorHistory` records stable locator hashes and lifecycle, while
`MediaAsset` describes present/missing/retired video, NFO and artwork assets.
Paths are operational data and must not be copied into public Event, Job or
quality-report payloads.

The primary LibraryItem is selected by availability, present main video,
`last_seen_at` descending and ID ascending. A Film with only ignored editions is
not listed by default.

## Structured metadata

- `FilmTitle` records canonical, original, localized and alternative titles by source.
- `FilmCountry` accepts ISO 3166-1 alpha-2 only and keeps source provenance.
- `Person` names are not globally unique. Exact external identity is preferred;
  source-local provisional identity is hashed from source instance and normalized name.
- `Credit` is the unique semantic Film–Person relationship; sources are tracked
  in `CreditProvenance` rather than duplicated Credits.
- `Concept` kinds are `genre`, `theme`, `movement`, `visual_style` and
  `micro_genre`. Aliases may be ambiguous across Concepts.
- `StructuredMetadataReview` captures unmapped or conflicting observations
  without storing source documents, credentials or absolute paths.

Sources are resolved in this order: user-curated, NFO, TMDB, filename. A source
refresh supersedes only records owned by that source.

Genres use the fixed `tmdb-movie-genres:v1` vocabulary. A uniquely resolved
genre is represented as accepted factual `HAS_GENRE` Assertion with structured
provenance; unknown genres remain reviewable.

## Profile state and Viewing

`FilmProfileState` stores one profile's `favorite`, `rating` and `notes` for a
Film. Viewing is a fact, not a boolean state. A Film can have any number of
active confirmed Viewings, including multiple records on the same day.

- Manual `watched=true` creates/restores one confirmed manual Viewing.
- Manual `watched=false` revokes only that manual Viewing.
- Diary creation always appends a new confirmed Viewing. A viewing date has
  `date`, `year`, `timestamp`, or `unknown` precision.
- Manual and Diary Viewings are user-editable and soft-deletable. Imported
  sources are shown in the Diary but remain read-only.
- Diary or other Viewing sources are never removed by the manual watched toggle.
- `watched` and `watched_at` are derived from all active confirmed Viewings;
  `manual_watched` reports only the quick-toggle's singleton manual Viewing.
- Diary is the only viewing-history product surface. Its `timeline` view returns
  every confirmed Viewing; its `recent` view derives one latest Viewing per Film.

`LocalProfile` remains a single local profile; account, authentication and
multi-profile behavior are outside v1.

## External scores

`FilmExternalScore` is normalized by Film, source, score kind and list/version.
`ExternalScoreRefreshState` stores source-level status, update time and bounded
error code. Scores are not serialized into an opaque Film JSON column.

## Analysis V2

`AnalysisRun` stores provider/model/version dimensions, input/output hashes,
tokens, bounded cost, status and a validated public summary. It never stores raw
prompts, raw responses, hidden reasoning or provider credentials.

`Assertion` is a subject–predicate–object edge with canonical qualifiers,
factual/curated/inferred scope and proposed/accepted/rejected review state.
Accepted or rejected user decisions cannot be overwritten by automatic runs.

`AssertionProvenance` records observations and AnalysisRun ownership.
`Evidence` contains only verified public HTTP(S) source metadata and bounded
claims. `AssertionEvidence` keeps supports/contradicts/context links and their
revocation lifecycle. Unresolved or unsafe candidates go to
`AnalysisResolutionReview`.

The predicate registry is immutable reference data. `HAS_GENRE` is factual-only;
the remaining Analysis predicates are the strict model-output subset described
in `docs/analysis-v2-contract.md`.

## Events, workflows and restoration

`EventRecord` is an append-only audit trail for canonical aggregates. A state
mutation and its event commit in the same SQL session. Events are not a full
state replay log and cannot contain old resource snapshots or filesystem paths.

`OperationSnapshot` provides bounded command restoration:

- metadata selection;
- artwork selection;
- ignore/missing/restore availability;
- controlled file organization.

Preview calculates a state hash and confirmation token. Restore fails on state
drift, stale token, repeated use, unavailable backup state or unsafe file move.
File operations reference an opaque Git-ignored manifest.

`WorkflowRun` and ordered `WorkflowStep` records own product-level background
execution state. Definitions are code-versioned, steps have stable input/output
hashes, and retry resumes from the first incomplete step. Public views contain
only stable IDs, bounded counts/status and safe summaries.

`Job` is a private single-step execution queue linked to a Workflow run/step.
It has no public route or SSE DTO and is never a domain fact source.

## Clear semantics

- `DELETE /library` retires LibraryItems and media availability but preserves
  Film, identities, profile state, Viewing, structured metadata, scores and W4 data.
- Reconcile may reactivate the same source item and shared Film.
- `DELETE /library/data` deletes all user/domain rows in FK order while
  retaining settings, schema journal and fixed predicate/genre references.

## Explicitly absent

The v1 epoch has no Movie table, per-Movie state table, permanent compatibility
alias, historical backfill report, compatibility reader, legacy projection
rebuilder, or raw analysis JSON projection. Old databases are not upgraded into this model;
they are archived and the application creates an empty Fresh Canonical database.

## Portability boundary

`library-export.v1` is a derived, read-only snapshot. It can contain canonical
Film identity and portable titles, FilmProfileState, Viewing, user-curated
metadata and explicit user Assertion decisions. It is not a fact source and
cannot be used to rebuild Read Models or replay Workflows.

The package excludes LibraryItem/MediaAsset locators, Settings, credentials,
EventRecord, Job, Workflow, OperationSnapshot, Read Models, source documents
and raw model/web content. Version 1 reserves null synchronization-version
fields but defines no import, device, clock or conflict semantics.
