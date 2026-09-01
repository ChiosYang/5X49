# Library Care and Management Constellation

Status: Complete
Last updated: 2026-09-01
Related: `GET /library/missing`, `/[locale]/library`, `/[locale]/library/manage`

## Goal

Keep everyday Film maintenance inside the cinematic Library experience while
retaining the constellation as an optional, advanced system-status view.

## Behavior contract

- The main navigation has no Management destination.
- `/library` accepts `view=metadata|inbox|offline`; an absent or invalid value
  renders all Films, and poster sort/filter parameters survive view changes.
- Care tabs appear only when they contain items or are currently active.
- Metadata reviews, organization previews, and missing-record cleanup keep their
  existing API, confirmation-token, and workflow semantics.
- Settings owns advanced diagnostics and the localized typed clear-data gate.
- `/library/manage` remains available as a deterministic constellation with
  safe runtime commands, workflow controls, and navigation to care views.
- Old `#metadata-reviews` and `#root-video-reviews` bookmarks redirect to the
  corresponding Library view.

## Decisions

- Prioritize metadata reviews, then stable organization candidates, then
  offline editions. Waiting files are visible but never counted as actionable.
- Load Films as primary page data and isolate organization/missing summary
  failures so the poster grid remains usable.
- Keep queue item selection client-local; only the top-level care view appears
  in the URL.
- Keep missing cleanup batch-only and move clear-all-data exclusively into the
  Settings danger zone.
- Remove the persistent constellation dock. Keep a compact command trigger and
  `Cmd/Ctrl+K` on the advanced page.

## Slices

### Slice 1 — Library entry and care state

Status: Complete

- Added deterministic view parsing, URL generation, counts, priority, and
  partial-failure state.
- Replaced root-only counts with complete organization candidates and missing
  summaries while preserving the original poster browsing controls.
- Added the primary scan action, More menu, conditional tabs, and understated
  recommendation status.

### Slice 2 — Library care views

Status: Complete

- Added a two-column metadata review experience with stable failure-first order
  and automatic progression.
- Reused file identity search, read-only target preview, conflict display, and
  confirmation tokens; stable files sort before passive waiting files.
- Added searchable, 50-item offline batches with rescan and explicit batch
  cleanup confirmation.

### Slice 3 — Settings and destructive maintenance

Status: Complete

- Added an advanced Library System Status link under Library settings.
- Added an anchored danger zone with impact counts, active-workflow blocking,
  localized exact-phrase confirmation, and cache refresh after completion.
- Removed clear-data execution from the constellation.

### Slice 4 — Advanced system status

Status: Complete

- Retitled the constellation for advanced diagnostics and retained stable
  topology, keyboard navigation, zoom, responsive inspectors, and workflows.
- Removed embedded queue editing and the bottom dock; exception actions now
  navigate to Library care views.
- Kept scan, metadata fetch, score refresh, workflow cancel/retry, Settings, and
  Activity commands in the compact searchable palette.

## Verification evidence

- `npm run test:unit`: 34 tests passed, including Library view parsing, query
  preservation, conditional navigation, recommendation priority, waiting-only
  state, partial failures, constellation layout, action destinations, and queue
  ordering.
- `npm run typecheck`: passed.
- `npm run lint`: passed with one pre-existing warning in Explore
  (`ExploreViews.tsx`, unused `onRemove`); no errors.
- `npm run build`: passed with all Library, Settings, Activity, Management, and
  prototype routes compiled.
- `uv run python -m unittest test_management_routes.py -q`: 3 tests passed.
- Browser verification covered explicit Chinese and English routes, clean
  hydration, pristine Library presentation, direct empty care views, preserved
  sort/filter queries, advanced Settings disclosure, typed danger confirmation,
  system-status navigation, palette navigation, and both legacy hash redirects.
- Browser responsive checks at 1280px, 900px, and 390px found no horizontal
  document overflow; the 390px palette remained within the viewport.

## Remaining risks

- The local fixture contained no active metadata, organization, or missing-item
  queue. Empty/completed states and API-level behavior were verified, while a
  live non-empty end-to-end confirmation remains to be exercised with suitable
  media fixtures.
- Destructive cleanup and clear-data dialogs were inspected without executing
  them against the local Library. Backend cleanup behavior remains covered by
  the focused route tests.
- The worktree contains unrelated Explore and Canonical changes that were not
  reset or reformatted.
