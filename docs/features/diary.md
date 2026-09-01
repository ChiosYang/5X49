# Diary MVP

Status: In Progress
Last updated: 2026-09-01
Related: Product Roadmap — Diary

## Goal

Allow a local profile to record, browse, edit, and remove multiple independent
viewing occasions for the same film while keeping the existing quick watched
toggle, full timeline and latest-per-Film view coherent.

## Scope

- Canonical Viewing CRUD for exact dates, years, timestamps, and unknown dates.
- Paginated `timeline` and `recent` Diary views plus per-film viewing history.
- Read-only handling for non-manual external viewing sources.
- Derived `watched`, `manual_watched`, and latest `watched_at` profile state.
- Diary, film-detail, navigation, API, and bilingual UI updates.

## Non-goals

- Per-viewing ratings, notes, calendar views, statistics, import merging, or
  multi-profile support.
- Schema migrations or changes to media files and user databases.

## Existing behavior

The quick watched toggle maintains one `manual` Viewing per film. Diary is the
only viewing-history surface: its timeline shows every confirmed Viewing and
its recent view selects the latest confirmed Viewing for each Film.

## Acceptance criteria

- [x] Multiple viewings for one film remain independent, including duplicate dates.
- [x] Date, year, timezone-aware timestamp, and unknown precision are validated.
- [x] Manual and Diary records are editable; external sources are read-only.
- [x] Deleting the manual record never deletes Diary or external records.
- [x] The recent view returns one latest entry per Film and is profile-scoped.
- [x] Viewing, Activity Event, and affected read models commit atomically.
- [x] Diary works in Chinese and English at desktop and narrow viewports.
- [x] Local backend and frontend verification passes.
- [x] The consolidated Diary and removed Watch History routes pass final local verification.
- [ ] GitHub Actions passes after the feature is authorized for merge and push.

## Decisions

- POST always creates a new confirmed `diary` Viewing; duplicate days are valid.
- DELETE is an idempotent soft delete and emits one Activity Event.
- The quick toggle controls only its singleton `manual` Viewing.
- A film watched only through Diary remains visually watched; its quick action
  opens the filtered Diary instead of creating another manual record.
- `GET /profile/viewings?view=timeline|recent` is the only profile viewing query.
- The former Watch History page and API are removed without compatibility routes.

## Open questions

- None for MVP.

## Slices

### Slice 1 — Canonical Viewing API

Status: Done

- Intended behavior: profile-scoped CRUD, date contracts, derived state, events,
  projections, pagination, and stable ordering.
- Likely affected areas: backend viewing/user-state services, Library API, tests,
  API documentation, and Backend Skill.
- Dependencies: existing Fresh Canonical v3 schema and projection hooks.
- Verification: focused backend tests, full unittest, and compileall.

### Slice 2 — Diary experience

Status: Done

- Intended behavior: bilingual Diary, viewing editor, film-detail section,
  timeline/recent views, and derived watched-button behavior.
- Likely affected areas: routes, hooks, API helpers, shared types/components,
  navigation, messages, and frontend tests.
- Dependencies: Slice 1 API.
- Verification: unit, lint, typecheck, build, and browser smoke.

### Slice 3 — Diary consolidation

Status: Done

- Intended behavior: rename the English product surface to Diary, merge the
  latest-per-Film summary into `view=recent`, and remove Watch History.
- Dependencies: Slices 1 and 2.
- Verification: backend/frontend regression, static symbol checks, and browser smoke.

### Slice 4 — Handoff

Status: In Progress

- Intended behavior: synchronize Domain Model and Roadmap, record actual evidence,
  and leave a clean reviewable feature branch.
- Dependencies: Slices 1–3.
- Verification: diff review and clean worktree after the planned commits.

## Verification evidence

- `uv run python -X utf8 -m unittest test_diary.py test_api_routes.py test_canonical_runtime.py test_event_sourced_commands.py -q` — 44 tests passed.
- `$diaryTestModules = Get-ChildItem -File -Filter 'test_*.py' | Where-Object { $_.Name -ne 'test_agent.py' } | ForEach-Object { $_.BaseName }; uv run python -X utf8 -m unittest $diaryTestModules -q` — 189 tests passed, 1 skipped.
- `uv run python -m compileall -q app` — passed.
- `npm run test:unit` — 14 tests passed.
- `npm run lint` — passed.
- `npm run typecheck` — passed after correcting the Next parallel-slot layout contract found by generated development types.
- `npm run build` — passed; the localized Diary route is included in the production route manifest.
- Isolated browser smoke on ports 8765/5550 — English and Chinese timeline/recent switching, URL restore, one-latest-per-Film behavior, per-Film full timeline, invalid-view fallback, removed-route 404, removed navigation item, and 375px overflow checks passed.
- The isolated database, media directory, services, browser tab, and runtime files were removed after the smoke test; the active application database and media were not used.

## Remaining risks

- GitHub Actions cannot run until the user authorizes merge and push. The feature
  remains `In Progress` until both repository CI jobs pass on `main`.
- Live multi-profile behavior is outside the MVP; the current product still has
  one LocalProfile.
