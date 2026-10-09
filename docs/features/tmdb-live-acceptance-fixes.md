# Real TMDB Acceptance Fixes

Status: Done
Last updated: 2026-10-09
Related: none

## Goal

Make real TMDB discovery, confirmation, version grouping, and repeated scans
reliable without changing the existing user library or weakening TLS verification.

## Scope

- Default Chinese routing, late TMDB identity resolution, scrape state persistence.
- Clear review/failure feedback, handled empty searches, responsive long titles.
- Regression coverage, isolated live acceptance, scoped browser CA diagnosis.

## Acceptance criteria

- [x] Chinese entry points load without redirect loops on loopback hosts.
- [x] Pre-scanned versions confirmed with the same identity share one Film and retain both identities.
- [x] Unchanged scans and restart preserve success, review, and failure bookkeeping.
- [x] Review is distinguished from failure; empty searches show a handled explanation.
- [x] Long titles stay inside their cards on desktop and mobile.
- [x] Isolated live acceptance uses real TMDB and verifies TLS.

## Decisions

- Preserve merged Film IDs as aliases and keep historical records.
- Keep each edition's write target stable even when the primary edition changes.
- Metadata snapshots for a newly grouped edition preserve the existing canonical Film.
- Reject incompatible known identities before NFO/artwork writes.
- Scanner observations do not clear command-owned scrape bookkeeping.
- Deterministic regression fixtures supplement, rather than replace, live TMDB acceptance.

## Slices

### Slice 1 — P1 routing and identity

Status: Done

- Verification: production routing regression; canonical runtime and scraper tests.

### Slice 2 — Persistence and UI

Status: Done

- Verification: scan/restart regression; UI error, review, and layout regressions.

### Slice 3 — Live acceptance

Status: Done

- Verification: isolated database/media; real search, details, artwork, repeat and restart;
  screenshots; CA trust diagnosis; local checks and PR checks.

## Verification evidence

- Baseline on main `2088ed0`: `/library` redirects to itself when standalone binds
  `127.0.0.1`; the locale rewrite changes its hostname to `localhost`.
- Backend `.venv/bin/python -X utf8 -m unittest discover -s . -p 'test_*.py' -q`
  with isolated `SQLITE_DB_PATH` — 271 passed.
- Backend `.venv/bin/python -m unittest discover -s ../scripts -p 'test_*.py' -q`
  — 13 passed; `.venv/bin/python -m compileall -q app` passed.
- Frontend `npm run test:unit`, `npm run lint`, `npm run typecheck`, `npm run build`,
  `npm audit --audit-level=high` — 69 unit tests passed; checks passed; 0 vulnerabilities.
- Playwright `test -g 'Chinese entry points'`, directly against the normal production
  application — passed on `127.0.0.1` and `localhost`.
- Isolated live acceptance: Le Samourai 5511, Crash 884/1640, Blade Runner 78
  (two pre-scanned editions), Matrix 603, and an empty-result control. All confirmed
  requests succeeded; candidate posters returned 200; empty scraping returned 409
  with actionable English/Chinese feedback and no unhandled browser exception.
- Final library: 6 Films / 7 editions; 6 valid NFOs and 12 valid artwork images.
  Repeat scan added 0; per-edition scrape bookkeeping remained unchanged for
  success/review/failure; full backend/frontend restart preserved library/workflows/settings.
- Desktop 1440 and mobile 390 title bounds passed. SQLite integrity and foreign
  keys passed. Original 24 user files remained unchanged; no saved TMDB secret.
- Local code review covered identity conflicts, aliases, edition targeting,
  projection refresh, metadata snapshots, persistence, and handled UI failures.
- Sanitized report and screenshots: `/tmp/5x49-tmdb-fix-verified-f3atlpf9/acceptance-evidence.zip`.
  PR checks and merge are tracked in the delivery task/PR.

## Remaining risks

- Chromium needs a writable NSS trust database to load the existing environment
  CA in this sandbox. A scoped filesystem grant resolved previews without disabling
  TLS; the original trust database was restored after acceptance. This is an
  execution-environment constraint, not an application TLS workaround.
