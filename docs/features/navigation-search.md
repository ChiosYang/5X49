# Navigation search

Status: Done
Last updated: 2026-10-20
Related: user-approved navigation search interaction

## Goal

Open a lightweight search field from the navigation icon and show keyword
results in Library without a separate Search page.

## Scope

- Expand left in 200 ms on desktop; preserve the transparent navigation,
  centered logo and existing page title. Use the full navigation row on narrow
  screens, temporarily replacing the menu, logo and status controls.
- Focus the field on opening. Escape and the close button cancel the draft,
  collapse the field and restore focus to the search icon.
- Submit only on confirmation, respecting IME composition and reduced motion.
- Start a fresh full-library query without inheriting old filters or pagination.
  Display the keyword and count; reuse Library filtering and pagination.
- Keep committed keywords consistent after repeated submissions and browser
  Back/Forward. Menu search opens the same field.
- Redirect old locale-aware `/search?q=...&page=...` links to Library; retain
  only normalized keywords and explicit valid pagination.

## Non-goals

- No new AI calls, backend API changes, Explore/Ask changes or deployment.

## Existing behavior

Library already supports bounded keyword reads, intersecting filters and page
links. The old Search page duplicated those reads. Navigation linked to that
page from both its icon and menu.

## Acceptance criteria

- [x] Desktop and mobile controls remain usable with long input and status icons.
- [x] Opening and editing do not navigate; close restores focus and cancels edits.
- [x] Fresh queries reset hidden filters and old pages; results show keyword/count.
- [x] Menu, IME, repeated operations, history and reduced motion behave correctly.
- [x] Legacy language-aware links remain safe and preserve explicit pagination.
- [x] Empty/error states remain distinct and recoverable.
- [x] Unit, E2E, lint, typecheck, build and independent review pass.

## Decisions

- At widths below 1024 px, use the full row to keep the field clear of the logo
  and both status icons. The desktop input is capped by available half-screen
  width and a 20 rem maximum.
- URL state is authoritative. Navigation commits remount the field's draft;
  cancelling restores the current Library keyword.
- Compatibility routes use the existing locale-aware redirect helper and
  construct an internal Library URL from an allowlist of parameters.

## Slices

### Navigation and result routing

Status: Done

- Affected areas: navigation components, Library result summary, legacy route.
- Verification: focused unit tests and real-backend browser acceptance.

### Verification and delivery

Status: Done

- Verification: repository checks, browser screenshots, independent review,
  draft PR and CI results.

## Verification evidence

- `npm run test:unit` — 94 passed (task-local Windows temp directory).
- `npm run lint` and `npm run typecheck` — passed.
- Production `next build`, invoked by the E2E harness — passed.
- `npm run test:e2e -- navigation-search.spec.ts library-filters.spec.ts zy-video-health.spec.ts` — 30 passed.
- Full local E2E run exercised 107 tests; 105 passed, then the two discovered IME/history synchronization cases were corrected and passed in the focused rerun.
- Independent read-only review — no blocking findings after the narrow-screen, out-of-range pagination and IME fixes.
- Real Chrome acceptance — desktop 1920 px and mobile 390 px; expansion, keyword/count results, repeated open, Escape focus restoration and browser Back/Forward verified.
- Browser coverage also checks 320, 768 and 1024 px, long input, empty/error results, language compatibility and reduced motion.
- Screenshot and 4.4-second video artifacts are retained outside source control; GitHub CI status is tracked on the PR.

## Remaining risks

- No known product blockers. Full GitHub CI must pass before the parent thread merges.
