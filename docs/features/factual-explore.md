# Local Explore: Browse, Search and Filter

Status: In Progress
Last updated: 2026-10-21
Related: Product Roadmap — Factual Explore

## Goal

Let a user move from trusted local Genre, Person, Country and Decade facts to a
strict, explainable and shareable Film set without model inference or silently
relaxed constraints.

## Scope

- Concrete, nonempty local collection entry points with existing artwork and exact counts.
- Inline search across Genre, Person, Country and Decade, with optional category browsing.
- Removable filters, viewing state, sort, paginated LibraryMovieCards and detail navigation on one page.
- Explicit People All/Any combination; legacy URLs without a mode retain OR semantics.
- Strict accepted local facts, conflict exclusion, missing values and honest empty/sparse fallbacks.
- Existing design tokens, controls, bilingual labels and desktop/mobile layouts.

## Non-goals

- Theme, Movement, Visual Style, Micro Genre or inferred Graph edges.
- Similarity, automatic constraint relaxation, natural-language Ask or LLM use.
- Anonymous event persistence/upload or mutation of local media/user data.

## Existing behavior

The Schema v4 synchronous read models remain authoritative. The previous Explore
required choosing a dimension, opening a Lens panel, then using a modal Fact
Finder. The new page replaces that entry flow; historical slices below retain
the original implementation and verification record.

## Acceptance criteria

- [x] The default page shows real local collections and Film results without choosing a dimension.
- [x] Each collection count and preview match the same strict filter/view query; identical sets are deduplicated.
- [x] No collections are invented for empty, conflicted or metadata-poor Libraries.
- [x] Search spans all four categories, groups results clearly and supports independent pagination.
- [x] Search text remains presentation state; selected filters and People mode round-trip through URL/history.
- [x] New People selections default to All; old links remain Any. Missing/conflicted people fail closed in All.
- [x] Viewing, sort, pagination focus and existing detail links are preserved.
- [x] Successful card saves refresh collection previews/counts and current results without changing URL/history;
  delayed saves use the latest query and cannot refresh a page or detail overlay the user has navigated to.
- [x] Coverage, Lens and Fact Finder concepts are absent from the primary Explore UI.
- [x] Existing LibraryMovieCard, Button, TextInput, typography, colors and spacing are reused.
- [x] Full backend suite, frontend checks, related browser suites and responsive visual inspection complete.
- [ ] Independent code review and required CI complete before merge.

## Decisions

- `factual-explore.v1` never falls back to Canonical live joins.
- Person memberships merge Director and Actor roles for one Film/person pair.
- Owned count equals visible local Film count for the facet.
- Decade payload says `release-year-decade.v1`; it does not claim an external source.
- Valid but unavailable filters remain visible and contribute an empty set.
- Country labels render their stable ISO code during SSR/hydration, then localize
  with the browser's `Intl.DisplayNames` after hydration so different ICU/CLDR
  versions cannot produce a React text mismatch.
- Context clues are factual navigation, not recommendations. They use fixed
  synchronous read-model queries and never invoke similarity or a model.

- `person_match=any|all` defaults to Any in the API. Existing person URLs keep
  union semantics. Fresh UI searches serialize All when selecting a person.
- A Person means participation as Actor or Director, deduplicated by canonical
  identity. Collection labels say "Films with" rather than claiming director-only work.
- Collection generation uses at most six bulk SQL statements, round-robins
  Country/Decade/Person/Genre candidates and deduplicates identical Film sets.
  Country entry points use Unwatched from the All view; explicit views are preserved.
- Search debounces by 200ms, uses the existing paginated facet endpoint for each
  category, and isolates responses by category/query keys. Old responses cannot
  repopulate a newer search. Bilingual aliases use the bundled vocabulary.
- Filtered pages do not fetch collection suggestions. No overview/coverage or
  context-clue requests are needed by the main Explore UI.
- Mobile collection entries scroll within one row; desktop uses the existing
  grid/spacing tokens. Missing artwork uses a quiet placeholder.
- The old modal Fact Finder remains available to Ask, which already reused it.

## Open questions

- Parent task owns independent code review and the final merge gate. This task
  delivers a draft PR and does not merge before that review and all related CI pass.
- Representative real-library metadata quality remains a product gate; synthetic
  fixtures establish behavior, not recommendation quality.

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

### Slice 7 — Browse before filtering

Status: Complete (implementation and local verification; independent review pending)

- Replaced the Lens landing/sidebar/sheet with local entry points and same-page search, filters and Films.
- Added `/explore/collections`, People All semantics for Films and Context, literal/bilingual facet search.
- Added fixture coverage for exact counts, role/identity deduplication, unresolved people, races, URL history,
  viewing/sort, result pagination, and empty/sparse Libraries. No real AI or provider calls are used.
- Verification: 41 focused backend tests, complete backend suite, frontend checks,
  74 related browser tests and the final 16-case Explore suite passed.

## Verification evidence

Current browse/filter implementation (2026-10-21):

- `.venv/Scripts/python.exe -X utf8 -m unittest test_explore_query.py test_api_routes.py test_factual_explore_evaluation.py -q` — 41 passed.
- `.venv/Scripts/python.exe -X utf8 -m unittest discover -s . -p "test_*.py" -q` — 426 tests, OK with 3 skipped.
  On Windows the full suite used an identical tracked-source snapshot in an owned short temporary path,
  canonical TEMP/TMP paths and read-only Git identity. This avoided existing MAX_PATH/short-name
  fixture failures without changing application code or touching the active database/media.
- `.venv/Scripts/python.exe -m compileall -q app` — passed.
- `npm run test:unit` — 122 passed; Windows used canonical TEMP/TMP for the existing glob tests.
- `npm run lint`, `npm run typecheck`, and production `next build` through the E2E harness — passed.
- `npm run test:e2e -- explore-ui.spec.ts interactions.spec.ts navigation-search.spec.ts library-ui.spec.ts library-menus.spec.ts site-copy.spec.ts` — 74 passed.
- Final `node e2e/run.mjs explore-ui.spec.ts` — 22 passed, including independent search pagination/retry,
  delayed search responses, rapid filter navigation, People All/Any and legacy URLs, viewing/sort/history,
  result pagination/detail return, strict zero results and empty/sparse/empty-view fallbacks.
  Six mutation regressions cover desktop/mobile default collections, favorite/watched saves, current
  Unwatched result removal, one refresh per save, unchanged URL/history/viewport (within document bounds),
  and saves completing after changing filters or entering a detail page without clearing search or stealing focus.
- English/Chinese at 1920, 1024, 768, 390 and 320px — no page overflow or hydration errors.
  Internal desktop/mobile captures were inspected; screenshots remain local. Only generated local
  fixtures and mocked transports were used, with real AI/provider requests disabled.
- `git diff --check` — passed. Independent review and required PR CI remain the merge gate.

Historical implementation evidence:

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
