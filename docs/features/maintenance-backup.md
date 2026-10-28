# Maintenance database backup download

Status: Implemented; draft review / CI pending
Last updated: 2026-10-12
Related: sequential improvement 5; baseline cc26174 / PR #22

## Goal and approved scope

One click on the maintenance page generates and downloads a restorable library
database package. The user approved excluding configuration, artwork/media/NFO and
external operation manifests, and keeping only the latest successful ZIP for 24
hours. Film facts, manual corrections/history, identities, viewing dates/reviews
and overall Film reviews remain. The large title, typography and navigation style
are retained. No real database, reset, restore, deployment or release is involved.

## Contract and decisions

- Reuse SQLite online backup and the existing v1 restore manifest; portable
  business JSON exports are not described as database backups.
- Pin one read transaction for integrity, counts and the snapshot. Sanitize only
  a private copy, VACUUM away stale pages, then create and verify a fresh manifest.
- Remove Setting; clean diagnostics and credential-shaped automatic fields. Fail
  closed if doing so would change protected user content. Arbitrary secrets typed
  into natural language are not semantically detectable. Derived caches are cleared
  for normal startup rebuild, avoiding stale hashes after diagnostic cleanup.
- Refuse snapshots containing active tasks; do not edit/replay queued jobs during
  recovery. Expire file-organization undo because external manifests are excluded.
- Separate last attempt, last successful generation, artifact availability and
  browser-reported download trigger. No claim of verified saving to user disk.
- Store durable receipts outside the source DB. Cross-process OS locks serialize
  generation and release on death. Startup/status reconciles interrupted work.
- Keep an old success after new failure. Enforce 24-hour expiry on access; sweep
  every 60 seconds while online, reconcile after restart, retry Windows open-file
  cleanup. Never sweep unrelated CLI backups. Backup storage failure affects this
  feature, not application startup.

## Verification slices

- [x] Synthetic API/service generation, downloads, idempotency, cross-process lock,
  interruption/restart, failed replacement, expiry/missing/corrupt files, concurrent
  WAL writes and credential canaries.
- [x] Existing offline CLI restore into a fresh synthetic environment, retaining
  merged aliases, manual metadata/edit history, Film reviews and four Viewing date
  precisions/reviews, with unchanged source and foreign-key checks.
- [x] Full backend/frontend checks and production E2E.
- [x] Actual restored application startup and no task execution via browser archive.
- [x] Desktop 1440px / narrow 390px Chinese pixel acceptance, without horizontal
  overflow; large title, fonts and transparent navigation preserved.
- [ ] Library screenshot delivery: the current required upload helper reports
  `Library prepare_uploads is not available`. Screenshots and the failure report
  are preserved locally; no alternate upload or invented file ID.
- [x] Final independent review by another reviewer after fixes.

## Current evidence and remaining risks

Targeted backend suite: 56 passed. Full backend: 351 tests, 2 existing skips.
Frontend: 89 unit tests, lint and typecheck passed. Production build passed.
Final complete E2E: 56/56 passed (4.4 minutes), including 9 backup-specific cases
and actual browser ZIP recovery/application startup. The installed Chromium
151.0.7922.34 was selected through the existing `E2E_CHROMIUM_PATH` override;
CI must still verify its own Linux/Playwright environment. A preceding interrupted
run and a subsequently fixed late-message race were retained as local evidence.

The independent reviewer identified projection hash, startup failure isolation,
overbroad text sanitization, pending download association and unbounded revalidation
issues. All were fixed and the final independent code review has no remaining
blocking findings. A follow-up review also confirmed the request-owned notice fix
after E2E exposed a late receipt overwriting download feedback. Independent review
does not substitute for the runtime checks or pixel review.

The pre-existing merged-alias deep-reset DELETE/RESTRICT defect is outside scope.
Backup/restore fixtures use fresh databases and never depend on clear_all_data.

## Backup test worker completion (2026-10-28)

A terminal receipt reports the package outcome, while the generator can still
own `generation.lock` during staging cleanup. A different request correctly
receives `backup_busy` in that window. The fixture previously returned on the
receipt alone, so a sequential replacement or cleanup assertion could race the
worker's `finally` block.

The fixture now tracks and joins the actual worker within its original 15-second
deadline, and joins workers before removing their temporary directory. Event-gated
regressions hold both successful and failed staging cleanup: same-ID replay stays
valid, different-ID generation remains busy, and the helper must wait for cleanup
and lease release before the next generation. Separate checks cover a worker
deadline failure, lock release on exceptions, and a timed-out contender preserving
the current owner's lock. Product locking, API behavior and existing assertions
are unchanged; no timing sleep, deadline increase or request retry was added.

Local controlled validation: the new event-gated test fails in both success and
failure cases when run with the original helper; all 14 backup tests pass with
the fix. Thirty repetitions each of the original replacement test, gated worker
test and failed-generation cleanup test pass (90 test executions).
