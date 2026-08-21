# Shared UI Primitives Extraction

Status: Done
Last updated: 2026-08-21
Related: `DESIGN.md`, `frontend/src/styles/tokens.css`

## Goal

Reduce duplicated frontend presentation and interaction code by extracting the
first-priority shared UI and domain components without changing existing user
flows, API calls, routes, or response handling.

## Scope

- Add shared Button, Dialog, form-control, and async-feedback primitives.
- Extract shared Activity operation details and TMDB metadata candidate picker.
- Migrate the existing settings, management, activity, file browser, Librarian,
  artwork, movie refresh, and root organization call sites where the behavior is
  already equivalent.
- Use the existing 5X49 semantic design tokens and utilities.
- Measure affected production TS/TSX physical lines before and after the change.

## Non-goals

- Redesigning pages or intentionally changing visual hierarchy.
- Changing hooks, backend APIs, routes, mutations, or public response shapes.
- Creating a generic Card component or merging distinct Film and Library cards.
- Adding a UI dependency or a component showcase page.

## Existing behavior

- Settings primitives mix setting-specific layout with controls also consumed by
  Library Management.
- Modal shells independently implement scrim, stacking, close behavior, and
  accessibility details.
- Activity detail renderers and metadata candidate selection are duplicated in
  two call sites each.
- The selected affected production files contain 3,468 physical lines at the
  pre-change `HEAD` baseline, excluding new shared component files and this
  document.

## Acceptance criteria

- [x] Existing settings, management, activity, artwork, file-browser, Librarian,
  movie refresh, and root-organization user flows keep their current behavior.
- [x] Shared components consume semantic color, shape, motion, focus, glass, and
  z-index tokens instead of adding page-specific hard-coded equivalents.
- [x] Dialogs expose consistent modal semantics, Escape handling, backdrop
  handling, scroll locking, and focus restoration without changing close rules.
- [x] Activity details and metadata candidates have one shared implementation
  each.
- [x] Frontend lint, typecheck, and production build pass.
- [x] The final report records gross removed lines, added lines, and net physical
  line change for affected production TS/TSX.

## Decisions

- Keep setting information architecture components under `components/settings`;
  move only genuinely reusable controls into `components/ui`.
- Keep request and mutation ownership in callers. Shared components receive
  state and callbacks and do not call backend APIs.
- Preserve current copy at each call site; generic components do not own product
  translations.
- Use existing `clsx` and `tailwind-merge` dependencies through a small `cn`
  helper rather than concatenating conflicting Tailwind classes manually.

## Open questions

- None blocking.

## Slices

### Slice 1 — UI primitives

Status: Complete

- Intended behavior: provide shared controls and dialog infrastructure with the
  existing visual tokens.
- Likely affected areas: `frontend/src/components/ui/`, settings primitives,
  settings and modal call sites.
- Dependencies: current design tokens.
- Verification: lint, typecheck, build, and focused code review of keyboard and
  disabled/busy behavior.

### Slice 2 — Shared domain presentation

Status: Complete

- Intended behavior: render Activity operation details and metadata candidates
  from one implementation without moving mutations out of callers.
- Likely affected areas: Activity clients, Movie refresh, root organization, and
  new `components/activity` and `components/metadata` modules.
- Dependencies: Slice 1 controls where useful.
- Verification: typecheck and comparison of callbacks, busy states, limits, and
  technical-mode output.

### Slice 3 — Migration and measurement

Status: Complete

- Intended behavior: finish call-site migration, verify behavior, and record the
  production line-count delta.
- Likely affected areas: all migrated frontend modules and this feature document.
- Dependencies: Slices 1–2.
- Verification: `npm run lint`, `npm run typecheck`, `npm run build`, diff review,
  and a HEAD-versus-worktree physical-line calculation.

## Verification evidence

- `npm run lint` — passed on 2026-08-21.
- `npm run typecheck` — passed on 2026-08-21.
- `npm run build` — passed on 2026-08-21; all application routes compiled and
  static page generation completed.
- Browser smoke on `http://127.0.0.1:5549` — English Library Settings,
  Library Management, Activity, movie Activity dialog, Artwork dialog, and
  Librarian Console opened and closed successfully; Chinese Library Settings
  rendered; Activity details expanded; no browser console errors were recorded.
- Browser smoke at 375 x 812 — the Chinese Library Settings page and directory
  dialog had no document- or dialog-level horizontal overflow; the temporary
  viewport override was reset afterward.
- HEAD-versus-worktree production TS/TSX physical-line calculation — the 13
  migrated existing files changed from 3,468 to 2,959 lines (509 fewer, 14.7%).
  Seven new shared modules contain 662 lines, so the complete production diff is
  1,096 added / 943 deleted, a net increase of 153 physical lines.

## Remaining risks

- TMDB candidate selection was not mutated during the read-only browser smoke;
  the current demo library had no root-video candidates. Its callback, busy, and
  type contracts were covered by lint, typecheck, build, and code review.
- The current Library navigation performed a full detail-page transition rather
  than activating the existing intercepted-detail route, so the full-screen
  `MovieDetailOverlay` path was not reached in the browser smoke. Its Escape and
  scroll-lock behavior now delegates to the same verified Dialog implementation.
