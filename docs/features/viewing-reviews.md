# Per-viewing ratings and impressions

Status: Done
Last updated: 2026-10-12
Related: User-authorized sequential plan, item 3

## Goal and scope

Each Viewing retains an optional rating and impression. Diary and Film detail
show and edit these values while preserving date precision and Film-level
personal data. Large titles, unboxed navigation and font hierarchy are retained.

No changes to metadata manual protection, conservative identity rules, NFO
writing, filters, backup UI or multiple roots. No real library or deployment.

## Confirmed behavior

- Viewing and Film reviews are independent; neither direction synchronizes.
  A Film rated 3 remains at 3 when two Viewings receive ratings of 4 and 5.
- Schema v9 adds nullable fields without assigning historical Film reviews to
  any Viewing. Existing Film ratings and notes remain unchanged.
- Rating is an optional integer 1–5; notes allow 10,000 Unicode characters and
  reject NUL. Omission preserves, null clears, whitespace-only notes clear.
  Review-only edits preserve the exact timestamp and precision.
- Quick watched-today creates an empty review; the expanded form records a date
  and review together. Same-date records remain distinct. External sources stay
  read-only. Watched off/on restores the same manual record, including unknown
  date, rating and notes; it never creates an implicit diary row.
- PATCH/DELETE require the revision captured when opening the form. Missing or
  stale revisions return 409 and require reloading.
- POST/PATCH use durable retry receipts, required for review writes. Viewing,
  event and receipt commit atomically. Identical retries return the saved result;
  changed payloads or subsequently edited/deleted results return 409. No retry
  can recreate a deleted row or authorize undoing a newer edit.
- The editor freezes its original revision and stays mounted across grouping or
  detail-list changes. Uncertain requests retain body/key in session storage and
  resume after navigation/reload. Ordinary close is disabled until resolution;
  normal unsaved cancel, close and back discard drafts. Late responses clear
  only their own request. Failed conflict reloads retain the draft.
- Successful writes with failed reads offer refresh without replaying the write.
- Export v1 includes reviews and validates older rows omitting them. Operational
  retry receipts are not exported. No new import workflow is introduced.

## Acceptance criteria and slices

- [x] Storage, migration, validation and exports preserve historical values.
- [x] Create/edit/clear, independence, source guards, precision, restart,
  transactional failure, concurrent stale forms and duplicate requests.
- [x] Diary/detail presentation, cancellation, navigation, safe undo, failed
  writes/reads, stable editors and request recovery.
- [x] Full tests/build/E2E, independent review and responsive screenshot checks.
- [x] Three requested screenshots saved to Library; confirmed IDs in the task.

## Verification evidence

Base main: `29941e0768aac1e387b1176cb06ce0e9eac4377f`.
Branch: `ai/viewing-reviews`; isolated repository and synthetic data only.

- `python -X utf8 -m unittest discover -s . -p 'test_*.py' -v`: 335 passed,
  two Windows platform skips (symlinks and POSIX read-only permission semantics).
  Log: task workspace `evidence/backend-final-suite.log`.
- `python -X utf8 -m unittest test_viewing_reviews test_diary test_api_routes
  test_database_migrations -q`: 53 passed.
- `npm run test:unit`: 84 passed. `npm run lint`, `npm run typecheck`: passed.
- `npm run test:e2e`: production build and all 36 browser tests passed. The
  runner uses synthetic SQLite/media, loopback traffic and deterministic
  provider fixtures, and restarts the real backend process.
- After final request-cleanup fix, `npm run test:e2e -- viewing-reviews.spec.ts`:
  production rebuild and five feature tests passed.
- Independent review: all findings fixed and rechecked, no remaining blockers.
  Reviewer separately ran five viewing-write unit tests and diff checks.
- Desktop 1440px, narrow 390px Chinese diary and narrow editor screenshots
  inspected; no horizontal overflow. Files are in ignored `e2e-artifacts/` and
  saved to Library. `git diff --check` passed.

Checks use a dedicated workspace TMP/TEMP and existing Chromium. Docker/WSL
were not installed. Containers were not tested because Docker is unavailable;
this change does not modify container configuration.

## Delivery and remaining limits

Implementation/local verification complete. Parent task monitors the draft PR's
CI and performs the authorized merge after required checks and protections pass.
No deployment is included.

Navigation recovery requires browser session storage. If disabled, the mounted
form retains its retry key but recovery after reload is unavailable.
