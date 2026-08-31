# Viewing Diary MVP

Status: In Progress
Last updated: 2026-08-31
Related: Product Roadmap — Viewing Diary

## Goal

Allow a local profile to record, browse, edit, and remove multiple independent
viewing occasions for the same film while keeping the existing quick watched
toggle and Watch History summary coherent.

## Scope

- Canonical Viewing CRUD for exact dates, years, timestamps, and unknown dates.
- A paginated global Diary timeline and per-film viewing history.
- Read-only handling for non-manual external viewing sources.
- Derived `watched`, `manual_watched`, and latest `watched_at` profile state.
- Diary, film-detail, Watch History, navigation, API, and bilingual UI updates.

## Non-goals

- Per-viewing ratings, notes, calendar views, statistics, import merging, or
  multi-profile support.
- Schema migrations or changes to media files and user databases.

## Existing behavior

The quick watched toggle maintains one `manual` Viewing per film. Watch History
shows only the latest confirmed Viewing per film. The existing Viewing table
already supports multiple rows and date precision, but it has no public CRUD or
Diary experience.

## Acceptance criteria

- [x] Multiple viewings for one film remain independent, including duplicate dates.
- [x] Date, year, timezone-aware timestamp, and unknown precision are validated.
- [x] Manual and Diary records are editable; external sources are read-only.
- [x] Deleting the manual record never deletes Diary or external records.
- [x] Watch History remains one latest entry per film and is profile-scoped.
- [x] Viewing, Activity Event, and affected read models commit atomically.
- [x] Diary works in Chinese and English at desktop and narrow viewports.
- [x] Local backend and frontend verification passes.
- [ ] GitHub Actions passes after the feature is authorized for merge and push.

## Decisions

- POST always creates a new confirmed `diary` Viewing; duplicate days are valid.
- DELETE is an idempotent soft delete and emits one Activity Event.
- The quick toggle controls only its singleton `manual` Viewing.
- A film watched only through Diary remains visually watched; its quick action
  opens the filtered Diary instead of creating another manual record.
- Watch History is a read-only summary. Viewing management belongs to Diary.

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
  read-only Watch History, and derived watched-button behavior.
- Likely affected areas: routes, hooks, API helpers, shared types/components,
  navigation, messages, and frontend tests.
- Dependencies: Slice 1 API.
- Verification: unit, lint, typecheck, build, and browser smoke.

### Slice 3 — Handoff

Status: In Progress

- Intended behavior: synchronize Domain Model and Roadmap, record actual evidence,
  and leave a clean reviewable feature branch.
- Dependencies: Slices 1 and 2.
- Verification: diff review and clean worktree after the planned commits.

## Verification evidence

- `uv run python -X utf8 -m unittest test_viewing_diary.py test_api_routes.py test_canonical_runtime.py test_event_sourced_commands.py -q` — 43 tests passed.
- `$diaryTestModules = Get-ChildItem -File -Filter 'test_*.py' | Where-Object { $_.Name -ne 'test_agent.py' } | ForEach-Object { $_.BaseName }; uv run python -X utf8 -m unittest $diaryTestModules -q` — 188 tests passed, 1 skipped.
- `uv run python -m compileall -q app` — passed.
- `npm run test:unit` — 13 tests passed.
- `npm run lint` — passed.
- `npm run typecheck` — passed after correcting the Next parallel-slot layout contract found by generated development types.
- `npm run build` — passed; the localized Diary route is included in the production route manifest.
- Isolated browser smoke on ports 8765/5550 — Chinese and English Diary, exact/year/unknown creation, update, delete, external read-only behavior, latest-only Watch History, Activity events, derived watched actions, and 375px overflow checks passed.
- The isolated database, media directory, services, browser tab, and runtime files were removed after the smoke test; the active application database and media were not used.

## Remaining risks

- GitHub Actions cannot run until the user authorizes merge and push. The feature
  remains `In Progress` until both repository CI jobs pass on `main`.
- Live multi-profile behavior is outside the MVP; the current product still has
  one LocalProfile.
