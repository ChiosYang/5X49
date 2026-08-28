# Fresh Canonical Stabilization

Status: Complete
Last updated: 2026-08-28
Related: `docs/product-roadmap.md` Fresh Canonical stabilization

## Goal

Establish a repeatable local release gate for the Fresh Canonical product loop:
fresh startup, generated-media import, deterministic reads, personal state,
workflows, bounded restore, destructive clear, and bilingual browser behavior.

## Scope

- Run only against generated media and isolated SQLite databases below
  `backend/data/stabilization/`.
- Require deterministic offline backend and bilingual browser evidence.
- Use recorded TMDB and deterministic Analysis fixtures for mandatory checks.
- Record Docker and live external-service status without making either part of
  the local conclusion.

## Non-goals

- Migrating or copying the active database.
- Reading or changing the user's configured media directory.
- Passing Gate B or enabling inferred Graph edges.
- Requiring Docker, live TMDB, or live OpenRouter evidence.

## Acceptance criteria

- [x] The active database and SQLite sidecars are unchanged by rehearsal.
- [x] Fresh Schema v3, deterministic scans, projections, state, restore, and
  dangerous-clear checks pass in isolated databases.
- [x] Generated valid videos are readable by FFprobe.
- [x] English, Chinese, desktop, and approximately 375px browser checks pass.
- [x] Reports and public operational payloads contain no secrets or private
  paths.
- [x] Strict local conclusion is `passed`; Docker and live integrations remain
  independently reported.

## Decisions

- Local deterministic evidence is the blocking product gate.
- Recorded external fixtures are mandatory; live network smoke is advisory.
- Raw artifacts remain Git ignored. Only a redacted quality summary is tracked.
- A failed check requires a fresh run ID after the fix; partial reruns cannot
  conclude the gate.

## Slices

### Slice 1 — Harness and isolation

Status: Complete

- Add the versioned report contract, CLI, run-directory guardrails, active
  database snapshots, browser evidence template, and strict conclusion.

### Slice 2 — Canonical lifecycle rehearsal

Status: Complete

- Generate normal and mixed media, exercise fresh startup, idempotent scanning,
  read models, profile state, snapshots, clear semantics, and privacy checks.

### Slice 3 — Browser evidence

Status: Complete

- Verify bilingual desktop and narrow-viewport product flows against the
  isolated rehearsal database.

### Slice 4 — Handoff

Status: Complete

- Run complete regression suites, conclude the local gate, and publish only the
  redacted quality summary.

## Verification evidence

- Strict local run `local-gate-20260828-05` concluded `passed` with report
  contract `fresh-canonical-stabilization-report.v1`.
- Every deterministic backend check passed, including active-database
  immutability, valid generated video, lifecycle, directory/file relink,
  Viewing semantics, projections, workflows, snapshots, dangerous clear and
  privacy scanning.
- English and Chinese desktop and 375px browser checks passed for Library,
  detail navigation, multi-edition display, artwork, Management anchors,
  profile state, Watch History, Search, Activity, Settings and Factual Graph.
- Backend regression suite passed with 157 tests and one environment-specific
  skip. Frontend unit, lint, typecheck and production build checks passed.
- Evidence fingerprints are published in
  `docs/quality/fresh-canonical-stabilization.md`; raw artifacts remain ignored.

## Remaining risks

- Docker is unavailable on the current host and remains outside the local gate.
- Live TMDB/OpenRouter smoke was not run; deterministic recorded transports are
  covered, while real services can still fail independently.
- Gate B remains blocked and inferred Graph edges remain hidden.
