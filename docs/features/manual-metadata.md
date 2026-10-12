# Manual film metadata

Status: Done
Last updated: 2026-10-12
Related: Sequential product plan, item 2; identity-review.md

## Goal and scope

Edit title, original title, release year and synopsis in the 5X49 database.
The existing automatic Film values and source records remain intact. A separate
Film-level overlay supplies corrected values to library, detail, graph, missing
items, diary display and Cinema DNA projections. The editor shows each field's
manual/automatic status and current automatic value. Existing page typography,
large titles and navigation are retained.

Personal rating/notes, Viewing records, provider identities, NFO writeback,
later plan items, deployment and global design changes are outside this scope.
The existing scraper's explicit NFO options remain separate from manual edits.

## Decisions and contract

- User approved an empty manual year as protected unknown (`null`). A rescan or
  scrape may update the automatic year but cannot fill this protected value.
- User approved blocking edition reassignment to another Film whenever the
  source Film has any protected field, including null. All overrides must be
  explicitly reset before the existing conservative identity flow may retry.
  Overrides are never implicitly transferred or merged.
- Reset removes protection only for that field and reveals the latest automatic
  value. It is staged until Save; Cancel/Escape/back do not write. A stale editor
  must explicitly reload and review the current values before another save.
- PATCH accepts only changed fields, a revision token and an idempotency key.
  Identity, personal and unknown fields are rejected. Text is trimmed; title is
  required (1–300 characters), original title is optional (up to 300), synopsis
  optional (up to 10000). Blank optional text becomes protected null. Years are
  strict integers 1870–2100 or null; strings, booleans and fractions are rejected.
- The revision covers automatic/manual values, source summaries, editions,
  identities and Film lifecycle. SQLite `BEGIN IMMEDIATE` serializes writes;
  override, receipt, audit event and projections commit atomically. Stale writes
  and conflicting reuse of a key return 409; busy database returns 503.
- An identical uncertain retry uses the same key and payload. A stored receipt
  returns current state without reapplying an old change. Each receipt retains
  before/after overrides and the automatic values/source summaries at edit time.
- Automatic observation/operation paths read raw Film data. Display overlays
  never become new automatic observations or operation undo snapshots.
- Historical scalar fields without provenance are labelled stored automatic
  library data rather than guessing an NFO/TMDB owner. Source title histories
  remain in the existing provenance model.
- Migration v8 adds overrides/receipts. Existing portable exports include an
  optional manual_overrides section; older v1 payloads remain valid. This does
  not introduce the separately planned backup download UI.

## Acceptance criteria

- [x] First edit, partial update, cancel/back, duplicate submission and retry.
- [x] Per-field reset with visible current automatic value; protected blank year.
- [x] Stale and concurrent edits reject lost updates; failures roll back.
- [x] Rescan/scrape/restart preserve manual values and source data.
- [x] Diary/profile records and identity decisions remain unchanged.
- [x] Complete backend/frontend checks, production build and browser E2E.
- [x] Final independent review and desktop/narrow screenshots saved to Library.

## Verification evidence

- Base main: `705b19d916b6d931ba60e9fa10445ae4bd0ef9b1`.
- All tests use owned synthetic media and isolated task-local databases; no real
  media library, credentials or environment files were used.
- Focused backend suite: 42 tests passed (`test_film_metadata`,
  `test_identity_review`, `test_metadata_scraper`).
- Full frontend unit suite: 82 passed; `npm run lint` and
  `npm run typecheck` passed.
- Full backend: `.venv/Scripts/python.exe -m unittest discover -s . -p
  'test_*.py' -q` ran 327 tests, OK (2 platform-conditional skips).
- Full browser E2E: 31 passed, including real scan/scrape and backend process
  restart, NFO hashes, diary/profile/identity snapshots, LAN HTTP-compatible
  request keys, graph cache refresh, stalled read cancellation and responsive UI.
- `npm run test:e2e` built Next production and ran all 31 browser checks.
  After the final Unicode validation/capture changes,
  `npm run test:e2e -- film-metadata.spec.ts` rebuilt production and passed all
  5 feature checks; lint/typecheck passed again.
- Independent review passed with no remaining blocking findings after fixes
  for automatic command-context contamination, stalled read cancellation, LAN
  HTTP request-key generation and stale graph caches. `git diff --check` passed.
- Reviewed desktop, narrow and narrow save-controls screenshots were saved as
  Library files. Confirmation IDs are retained in the task handoff rather than
  publishing account-specific Library identifiers in the repository.

## Open questions and remaining risks

No unresolved product decisions or code-review blockers. The draft PR is handed
to the parent task for CI and merge; no release or deployment is included.
