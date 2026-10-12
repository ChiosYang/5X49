# Deterministic Library filtering

Status: Blocked
Last updated: 2026-10-12
Related: User-authorized sequential plan, item 4; draft PR #22

## Goal and scope

Combine duration, rating and release-year ranges with existing Library search,
watched state, favorites and sorting. Preserve large titles, unboxed navigation,
fonts, existing maintenance views and deterministic pagination. Synthetic data
only; no backup-download work, multiple roots, deployment or real media changes.

## Contract and decisions

- Conditions intersect before SQL counts, sorting and pagination. Watched status
  and favorites can be active together. Legacy favorite links remain supported.
- Inclusive optional lower/upper bounds. Duration is integer minutes 1–10000;
  year is an integer 1870–2100. Reversed/invalid ranges are explicit errors.
- Unknown values remain eligible without that range and are excluded with it.
  Duration uses positive primary-edition measured seconds, then positive Film
  runtime; compare exact seconds and share this expression with duration sorting.
- User confirmed Film personal overall rating, integer stars 1–5. No external
  score or Viewing aggregation/fallback. Unrated Films fail active rating ranges.
- Year reads the effective projected metadata, including manual corrections and
  protected null. Filtering never writes metadata or removes protection.
- Applied state lives in the URL. A native GET form applies drafts together and
  cancels superseded document navigation. Sort, paging, care links and detail
  return preserve the complete condition set. Apply/sort changes reset the page.
- `page` always remembers the Film grid page; `metadata_page` separately selects
  the metadata-review queue page. Maintenance pagination preserves the applied
  Film conditions, and every maintenance return (including empty/completed
  metadata, inbox and offline states) restores those conditions and Film page.
  Maintenance queues remain library-wide, independent of the Film filters.
- Clear all removes search, watched, favorite and ranges, preserves sorting and
  starts at page one. Search hands its query to the Library for refinement.
- Invalid URL ranges show a correction message without an unfiltered grid.

## Acceptance and verification

- [x] Base main verified: b87737d567e97997567aa608d85de89037b1ac57.
- [x] Isolated checkout, branch ai/deterministic-library-filters, synthetic tests.
- [x] Duration/year/search/watched/favorite SQL intersection and URL state.
- [x] Confirm and implement rating semantics.
- [x] Full backend/frontend checks, production build, complete E2E.
- [x] Implementation-following diff review and desktop/narrow pixel review.
- [ ] Confirmed Library screenshot IDs (upload capability unavailable).
- [x] Commit, push and draft PR #22 for parent-task CI verification and merge.

## Verification evidence

- Implementation commit: `89a40b2650aa61f23cbe332d876effb7ed9d8ba2`.
- Draft PR: https://github.com/ChiosYang/5X49/pull/22. Parent owns CI verification
  and merge; no release or deployment was performed.
- `python -X utf8 -m unittest discover -s . -p 'test_*.py' -q`: 340 tests,
  2 Windows platform skips (symlinks and POSIX permission semantics), no failures.
- `npm run test:unit`: 89 passed.
- `npm run lint` and `npm run typecheck`: passed.
- Production `next build`, executed by `npm run test:e2e`: passed.
- `npm run test:e2e`: 47 passed, including eleven new filter scenarios. Coverage
  includes every condition together, boundaries/unknowns, personal-rating source
  isolation, empty/clear/invalid ranges, pagination, search handoff, reload,
  detail return, browser back, repeated submits, SSE reconciliation and a delayed
  superseded document response. Four follow-up browser cases exercise metadata
  previous/next/reload/history at desktop and narrow sizes, every empty care
  return, and a real completed offline cleanup. Film page 2 and every applied
  condition/sort survive these round trips. Existing metadata/identity/Viewing
  suites pass. An interrupted run was discarded after the host disconnected;
  no task processes remained, and the complete fresh rerun passed.
- `git diff --check`: passed. The implementation author's post-implementation review covered
  source separation, manual metadata protection, URL propagation, SQL ordering,
  local profile reconciliation, response compatibility and test isolation.
  Parent-task independent review found missing condition propagation in
  maintenance paging and empty/completed return links. The follow-up fixes those
  paths and adds browser round trips; final parent re-review remains required.
- Inspected actual 1440px desktop and 390px Chinese screenshot pixels: original
  title/font/navigation presentation preserved, all ranges readable, no horizontal
  overflow. Also inspected the final desktop/narrow metadata-review paging
  screenshots. Screenshots contain only synthetic fixtures.

## Remaining limits

- Implementation and local verification are complete. Library retention is
  blocked: the current helper reports `Library prepare_uploads is not available`.
  No Library IDs were issued. One authorized retry failed before transfer with
  the same capability error; the parent declined switching to direct writes.
- Windows requires the canonical long TEMP path for existing ESLint glob tests;
  SQLite/loopback tests need execution outside the restrictive sandbox.
- The local task browser tool currently fails to initialize with a missing
  Windows platform directory (HRESULT 0x80070003). UI checks used installed local
  Chromium with the repository's `E2E_CHROMIUM_PATH` override and fresh contexts.
- Parent-task message tool reported that the app-server was unavailable; the
  parent retrieved progress and relayed the user's explicit rating decision.
- Full E2E exposed a pre-existing bulk-reset foreign-key ordering problem with
  merged Film/GraphEntity aliases. Test-only teardown unlinks these synthetic
  aliases before clearing. Production reset behavior is outside this feature;
  its existing merge-alias reset limitation remains for a separate fix.
