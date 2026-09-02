# Factual Explore and Explore Lens

Status: Done
Last updated: 2026-09-02
Related: Product Roadmap — Factual Explore

## Goal

Let a user move from trusted local Genre, Person, Country and Decade facts to a
strict, explainable and shareable Film set without model inference or silently
relaxed constraints.

## Scope

- Schema v4 disposable synchronous Explore Film/facet projections.
- Coverage that separates eligible, conflicted and missing facts.
- Strict same-dimension OR, cross-dimension AND, and watched-state AND queries.
- Paginated facets and Film results with stable URL serialization.
- Bilingual `/explore` UI and Film Graph Person/Genre entry links.
- Fixed-read `/explore/context` clues with exact AND/OR impact counts and safe,
  deterministic preview Films.
- Progressive Lens Deck, human-readable Query Ribbon, one contextual Lens and
  one shared Fact Finder instead of four simultaneous filter panels.

## Non-goals

- Theme, Movement, Visual Style, Micro Genre or inferred Graph edges.
- Similarity, automatic constraint relaxation, natural-language Ask or LLM use.
- Anonymous event persistence/upload or mutation of local media/user data.

## Existing behavior

Fresh Canonical v3 already had deterministic Library/Detail/Search/Graph read
models and Resolver-selected factual metadata. Explore adds a separate
rebuildable query surface; Canonical rows remain the sole source of truth.

## Acceptance criteria

- [x] Only visible Library Films receive Explore Film rows.
- [x] Genre, Person and Country use Resolver-selected accepted factual state;
  conflicts are countable but never eligible.
- [x] Decades are deterministically derived from release year.
- [x] Viewing/domain mutations refresh projections transactionally.
- [x] API semantics and pagination are strict and reproducible.
- [x] URL parsing, normalization and serialization are stable.
- [x] The bilingual UI shows coverage, facets, active constraints, results and
  strict zero-result state without copying the full Library on first entry.
- [x] Person and Genre Graph nodes link to Explore; other Concepts remain read-only.
- [x] Context clue totals match strict Film queries without facet-level N+1 reads.
- [x] Filter, view and sort changes preserve the viewport; only result pagination
  focuses and scrolls the result stage after new data arrives.
- [x] Country localization remains deterministic during SSR/hydration.
- [x] Explore Lens isolated bilingual desktop/375px browser smoke and final
  complete-suite review pass.

## Decisions

- `factual-explore.v1` never falls back to Canonical live joins.
- Person memberships merge Director and Actor roles for one Film/person pair.
- Owned count equals visible local Film count for the facet.
- Decade payload says `release-year-decade.v1`; it does not claim an external source.
- Valid but unavailable filters remain visible and contribute an empty set.
- Country labels render their stable ISO code during SSR/hydration, then localize
  with the browser's `Intl.DisplayNames` after hydration so different ICU/CLDR
  versions cannot produce a React text mismatch.
- The current Lens is presentation state, not query state. The URL continues to
  contain only strict facts, viewing state, sort, direction and pagination.
- Context clues are factual navigation, not recommendations. They use fixed
  synchronous read-model queries and never invoke similarity or a model.

## Open questions

- Engineering scope and the four-dimension Beta contract are frozen. PR #4 was
  merged into `main` as `07d89530f110` after its required CI passed.
- Representative real-library coverage, external Alpha comprehension and
  repeat-use evidence remain product-gate work; this engineering handoff does
  not claim those results.

## Slices

### Slice 1 — Schema v4 and Explore projection

Status: Complete

- Added additive read-model DDL, immutable migration registration and projection states.
- Added same-transaction refresh, conflict eligibility and deterministic rebuild hashing.
- Verification: migration, schema, projection and focused Explore tests passed locally.

### Slice 2 — Strict query API

Status: Complete

- Added overview, facet pagination/search and Film filtering endpoints.
- Added malformed/unresolved behavior, stable sorting and public payload boundaries.
- Verification: route contracts and focused query tests passed locally.

### Slice 3 — Bilingual Explore page

Status: Complete

- Added locale-aware page, facets, Person roles, localized Country/Decade labels,
  active chips, watched/sort controls, strict zero state and result pagination.
- Verification: frontend unit, lint and typecheck passed for changed code.

### Slice 4 — Graph links and responsive verification

Status: Complete

- Person and Genre nodes use stable Explore links in SVG and relation list.
- Isolated browser smoke covered English/Chinese desktop, 375px layout, strict
  filtering, history/refresh behavior, conflict handling and Graph link targets.

### Slice 5 — Handoff, roadmap and CI

Status: Done

- API, backend Skill, database lifecycle, Domain Model and roadmap are synchronized.
- Local production build, complete backend suite and final diff review passed.
- PR and post-merge `main` Backend/Frontend CI passed.

### Slice 6 — Explore Lens interaction model

Status: Complete

- Replaced the four always-open facet tables with a four-door Lens Deck and one
  global Fact Finder.
- Added an explicit Query Ribbon, optimistic result stage, contextual six-clue
  Lens panel and mobile bottom sheet.
- Added exact remaining/additional counts and deterministic representative Film
  artwork through `GET /explore/context`, without Schema v5.
- Filter, viewing and sort navigation use history push with `scroll:false`;
  pagination alone restores focus and scroll position at the result heading.
- Verification: focused backend context/API tests, frontend unit/lint/typecheck,
  production build and isolated responsive browser smoke pass locally.

## Verification evidence

- `uv run python -m app.evaluation.factual_explore --run-id
  w7-engineering-20260901-01 --seed 549 --count 200 --scale-count 1000` —
  Passed against commit `d6d594208210`. All four dimension partitions, strict
  AND/OR and Viewing semantics, fail-closed unresolved/conflicted filters,
  deterministic rebuild, public payload privacy and the 10-statement context
  ceiling passed. The 1,000-Film context used 9 SQL statements; timings are
  informational. Git-safe evidence is recorded in
  `docs/quality/factual-explore.md`; raw artifacts remain ignored.
- `uv run python -X utf8 -m unittest test_factual_explore_evaluation.py
  test_explore_query.py test_api_routes.py -q` — 36 tests passed, including
  deterministic evaluation, failure exit, privacy summary, contextual AND/OR
  counts, fixed statement count and route validation.
- `uv run python -X utf8 -m unittest discover -s . -p "test_*.py" -q` —
  208 tests passed, 1 skipped.
- `uv run python -m compileall -q app` — passed.
- `npm run test:unit` — 34 tests passed, including Explore URL,
  hydration-safe localization and Graph-target coverage.
- `npm run lint` — passed with no errors or warnings.
- `npm run typecheck` — passed.
- `npm run build` — passed; Next.js emitted the locale-aware `/[locale]/explore` route.
- GitHub Actions CI on PR #4 — Backend and Frontend checks passed against final
  PR HEAD `1192f79d5e4b`. PR #4 was merged as `07d89530f110`; post-merge
  [main CI run 33580430791](https://github.com/ChiosYang/5X49/actions/runs/33580430791)
  also passed its Backend and Frontend jobs.
- Original Factual Explore isolated browser smoke — verified four-dimension coverage and top facets,
  Genre OR plus cross-dimension AND, watched/unwatched, Person search and role
  labels, canonical URL/history/refresh behavior, unresolved conflict handling,
  strict zero results, Chinese localization and no horizontal overflow at
  375x812. The isolated database, media fixtures and logs were removed after
  the run without accessing the active database or media.
- Explore Lens isolated browser smoke — verified the four-door landing with no
  inputs or Film wall, contextual AND remaining counts, same-dimension OR added
  counts, human-readable Query Ribbon, Fact Finder `/` focus/search/role labels,
  search text exclusion from the URL, strict zero result, watched state,
  stepwise history, Graph Person lens selection and filter scroll preservation.
  English/Chinese desktop and 375x812 had no horizontal overflow or hydration
  mismatch; the mobile Sheet restored focus on Escape and reduced-motion opened
  without transform/transition. A final fresh tab produced no console errors.
  Its isolated database, media directory, copied frontend build, logs and server
  processes were removed after the run.
- W7 closure browser replay — used the deterministic 200-Film behavior fixture
  with an isolated SQLite database and media directory. Chinese/English desktop
  and 375x812 mobile flows passed without horizontal overflow. A 100-Film Genre
  result advanced from `1–40 / 100` to `41–80 / 100`; completion focused the
  result heading and returning to page one preserved its result-stage scroll
  position. Viewing and sort changes preserved their control-stage position,
  and browser back/forward plus refresh restored the URL state. The operator
  separately confirmed Chrome Tab/Enter navigation for the SVG Genre and Person
  links after the in-app browser keyboard dispatcher proved unsuitable for that
  input replay.
- `git diff --check` — passed; only the repository's existing LF-to-CRLF notices
  were emitted.

## Remaining risks

- The engineering fixtures are deterministic and synthetic. Representative
  real-library coverage/correctness, Alpha comprehension and repeat-use evidence
  are intentionally unverified product gates.
