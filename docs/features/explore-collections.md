# Explore Collection Browsing

Status: Done
Last updated: 2026-10-21
Related: factual-explore.md; PR #40

Merged in PR41 as `e27a96c5ea6fa690a51c9ca0db1ef2cda3ef7d17`, after independent
review and CI 39580467533 (432 backend / 1 skip, RC15, frontend127, browser234).
The next [unified search](explore-unified-search.md) revision places its input
directly above the shelves; the original lightweight-entry decision is historical.
The later [Explore simplification](explore-simplification.md) moves the full
directory onto the homepage and removes manual combination editing. The separate
directory and combined-filter presentation below is historical.

## Goal

Browse a local topic, enter its collection, then choose a film. The homepage
organizes content; query editing is an explicit, separate mode.

## Scope and decisions

- `/explore`: a few factual collection shelves, a lightweight search entry,
  the collection directory and an explicit combined-filter entry. No whole-library grid.
- `/explore/collections`: paginated directory with optional director/region/decade categories.
- `/explore/collections/{kind}/{key}`: stable definition independent of temporary
  viewing/sorting/page parameters; exact director roles, any-role person collections.
- `/explore/search`: existing Library film search plus local people and collection
  lookup. Film opens detail; person opens a collection. No automatic filter chips.
- `/explore/filter`: PR40 exact combinations. Historical `/explore?...` queries keep
  their original semantics, including People Any defaults.
- Existing cards, controls, typography and tokens throughout. No hero or redesign.
- Catalog shelves require two films. Featured shelves suppress highly overlapping
  sets. Direct definitions may contain one film; empty or unavailable ones fail closed.
- Only accepted synchronous local facts. No new series inference, AI, external lists,
  schema migration, credential or media changes. Ask's shared Finder stays unchanged.
- Collection previews reuse LibraryMovieCard; directory covers reuse existing image
  handling. Mobile uses the existing two-column grid so card actions are not clipped.
- Profile and viewing commits publish an in-memory SWR revision. Each Explore
  address acknowledges its own fresh read, including cached Back entries. Managed
  filter/page reads begun after a commit do not trigger duplicate refreshes;
  pending navigation wins. Other mounted addresses conservatively validate their snapshot.
- Explore links do not prefetch the other heavy page modes. Existing Film card
  navigation, browser modifier keys, history and scroll handling remain in place.

## Acceptance criteria

- [x] Homepage, directory, search and stable collection detail implement the hierarchy.
- [x] Direct/refresh/Back/Forward restore identity, view, sort and page; home position returns.
- [x] Legacy exact filters and People All/Any semantics stay intact.
- [x] Saved state updates all Explore surfaces, including cached Back entries and delayed writes.
- [x] Last-page shrink uses replace; newer navigation/focus/history are never overwritten.
- [x] Empty/small/sparse/conflicted data yield honest, usable fallbacks and exact counts.
- [x] Bilingual desktop/mobile and keyboard behavior verified; Ask's shared UI is unchanged.
- [x] Focused/full local checks and internal visual review complete.
- [x] Required PR CI is successful before ready/merge.
- [x] Independent parent review passes before ready/merge.

## Slices

1. Additive local catalog and role-correct stable collection API, contract tests/docs.
2. Reorganize locale routes using existing controls and mutation/navigation protection.
3. Fixture browser coverage, complete checks, responsive visual review, draft PR/CI.

## Verification evidence

- `python -X utf8 -m unittest test_explore_query.py test_api_routes.py test_factual_explore_evaluation.py -q`: 47 passed.
- Full backend `unittest discover`: 432 tests, OK with 3 skipped. Used a verified
  tracked-source snapshot under an owned short Windows temporary path, canonical
  TEMP/TMP and read-only Git identity, avoiding existing fixture path limitations.
- `npm run test:unit`: 126 passed. `npm run typecheck` and `npm run lint`: passed.
- `node e2e/run.mjs explore-collections.spec.ts explore-ui.spec.ts`: production build
  and 43 browser cases passed. Includes the original precise-filter races and
  both 41-to-40 corrections, single refresh per save, cached directory/home Back,
  a save completing during a held collection Link, legacy People Any, pagination,
  independent search groups and empty/sparse local data. No real provider calls.
- English/Chinese at 1920, 1024, 768, 390 and 320px: hierarchy and keyboard checks
  pass. Internal home/directory/detail captures inspected; discovery search also
  inspected at 1440/390/320px in a separate read-only fixture browser. No horizontal
  page overflow; screenshots remain local and contain generated fixtures only.
- `node e2e/run.mjs --max-failures=2`: full production build and 222 real-API
  browser cases passed, including Explore 43 and the related Library/navigation,
  keyboard, copy, Viewing and existing Ask surfaces. All transports are isolated;
  only generated local data is used. Final lint has no warnings.
- `git diff --check`: passed. PR CI and independent review remain the merge gate.

### Review corrections

- Expanded the Film return-context allowlist to the known Explore list routes and
  canonical collection keys. External/protocol-relative URLs, control characters,
  arbitrary descendants, invalid IDs and encoded path escapes remain rejected.
- `npm run test:unit`: 127 passed; lint/typecheck and the production fixture build
  passed after the correction. Twelve Return-button cases cover collection/filter/
  search in English/Chinese at 1440/390px, preserving queries, page, scroll, focus,
  the existing push behavior and subsequent browser Back history. All 12 passed.
- The first PR CI had 221 passing browser cases and one test navigation race:
  the directory test reloaded before its Link's RSC navigation committed. The
  failure trace stayed on `/en/explore`, while the JP detail API returned two Films.
  The test now waits for the directory URL and heading before reload and still
  asserts JP exists in the directory. This case also passed after the correction.
- The final head must rerun the complete CI browser suite (now 234 cases) and pass
  independent re-review before ready/merge.
- CI `39578344452` passed against application head
  `cb6cf3bc5c8df81bbe03154b1f13988f635d58d6`: Backend 432 (1 skip), RC tooling 15,
  Frontend 127 plus audit/lint/types/build, and all 234 browser cases.
- An additional Windows full replay had 233 passes and exposed a second test-side
  navigation race: the collection history case recorded pre-navigation URLs and
  reloaded before either View or Sort committed, then Back reached `about:blank`.
  The test now waits for each committed URL and checks selected controls after
  reload. The corrected case passed three consecutive repetitions; application
  code is unchanged. The final test-only head reruns required CI before merge.

## Remaining risks

Synthetic metadata establishes correctness, not real-library editorial variety.
Independent review remains the merge gate.
