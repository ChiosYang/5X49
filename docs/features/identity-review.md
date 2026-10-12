# Identity conflicts and file reconnection review

Status: Done
Last updated: 2026-10-12
Related: foundational capability 1 of 6

## Goal and scope

Provide a public identity-review queue, evidence comparison, and the conservative
manual decisions approved by the user: keep independent editions, or reconnect a
missing edition within the same Film. Preserve existing large headings, fonts and
global navigation. All implementation verification uses isolated synthetic data.

Metadata editing, per-viewing ratings/notes, range filters, backup UI, multiple
media roots and nested directory discovery belong to later work. Cross-Film
merge/split, provider conflict adjudication and personal-data transfers remain
inspection-only, as agreed by the user through the parent task.

## Existing behavior and actual review types

IdentityReview is separate from TMDB scrape needs_review, AnalysisResolutionReview,
StructuredMetadataReview and Viewing.review_status. These queues are not combined.

| Reason | Trigger |
| --- | --- |
| identity_conflict | Incoming exact identities disagree with existing Film ownership |
| relink_identity_conflict | A file candidate conflicts with the incoming Film identity |
| relink_live_copy_conflict | A matching file's original locator still exists |
| relink_file_disappeared | A queued observation cannot be read or fully hashed |
| relink_full_hash_no_match | No candidate matches the complete hash |
| relink_full_hash_duplicate | Several candidates match the complete hash |

Existing-item identity conflicts previously raised without a review. Scans now
preserve existing identity/metadata, record stable evidence, and update only
observed availability/last-seen facts. They do not incorrectly mark the observed
item missing. Normal rescans retain an open review's resolution status.

The old automatic `_merge_empty_film` combines favorites, selects a rating,
concatenates notes and transfers Viewings. Manual decisions never invoke it.

## Approved behavior contract

### Inspection and retained evidence

- GET list/detail endpoints provide deterministic pagination, conflict reasons,
  safe Film/edition previews, observed provider IDs and candidate state.
- Schema v7 adds nullable candidate_snapshot and decision JSON columns. New
  snapshots retain at most 50 candidate IDs and state hashes, normalized provider
  IDs, source evidence and a truncation flag. They contain no paths, note text,
  raw fingerprints or source documents. Candidate hashes are sealed after the
  transaction finishes syncing identities/assets.
- Historical reviews remain unchanged and explicitly lack evidence. Unknown,
  truncated, missing or changed evidence cannot authorize an action.
- Candidate status compares database facts; inspection does not claim to have
  checked current files. GETs invoke no provider, scan, write or file probe.
- Personal-data previews show Viewing counts and rating/notes/favorite flags;
  they do not include private note text.

### Keep independent editions

Preview checks the current source file under the configured media root.
Confirmation marks only this review dismissed and clears its review-required
resolution marker. All Film/edition IDs, provider identities, assets, profile
state and Viewings remain in place. Files are neither deleted nor moved.

### Reconnect within the same Film

The selected target must be a captured candidate in the same Film and profile.
Both editions must have exactly one main video and no multipart assets. The
source file must still match its evidence, the target's old path must be absent,
and both stored complete hashes must match the current source's complete hash.
Sample fingerprints alone never authorize reconnection. Locators copied to the
target must be inside the configured root or valid local artwork application URLs.

Confirmation preserves the target LibraryItem ID and redirects its active assets
and locator history to the new file. The source discovery and its original assets
remain as retired history. Shared NFO/artwork references are reused, avoiding
unique-key collisions. Previous target locators/assets remain historical.
Ratings, favorites, notes, metadata and Viewing ownership remain on the same
Film. If its preferred-edition pointer selected the discovery, the pointer follows
the preserved target ID; the confirmation explains this effect.

Prior undo snapshots for these two editions are listed in preview and marked
expired in the same transaction. Their before/after history and manifest
references remain intact. Old tokens cannot undo a file organization after that
file has been reconnected; undo restore obtains its write lock before reading.

### Transaction, retries and concurrent scans

Preview returns explicit effects and a confirmation token covering database
revision, action, target, complete live-file observation and configured root.
Confirm rechecks these under BEGIN IMMEDIATE, then records the decision, edition
changes and bounded user IdentityReviewDecided event in one transaction. Event
failure rolls everything back. The existing synchronous projection hooks observe
canonical changes in that transaction.

The decision persists a request hash and caller idempotency key. An identical
retry returns its original result/event ID; changed reuse or another decision on
the closed review returns 409. Scan observation and missing-file writes acquire
the same SQLite write lock before reading ownership, preventing stale scan writes
from resurrecting a retired discovery. Ignore, preferred-edition, cleanup and
undo commands also serialize their ownership checks. Unchanged rescans retain complete hashes
for sampled large files and do not reopen/recreate decided work.

### Browser behavior

The library links to a separate English/Chinese identity-review page. The dialog
supports candidate comparison, preview, return to comparison, close/Escape, error
retry and confirmation. It scrolls within the viewport on mobile. Confirmation
has an in-flight guard; a lost response can be retried with the same payload/key.
Changed evidence is displayed explicitly and cannot silently approve old choices.

## Acceptance and slices

- [x] Public queue, bounded evidence and additive migration compatibility.
- [x] User-approved conservative decisions with explicit effects.
- [x] Atomic rollback, stale/candidate/file guards, idempotency and scan concurrency.
- [x] Unchanged rescan suppression and personal-data/asset retention.
- [x] Browser errors, duplicate submissions, return/close and responsive layout.
- [x] Final independent review; draft PR delivery for parent CI/merge coordination.

## Verification evidence

- Full backend: `.venv/Scripts/python.exe -m unittest discover -p 'test*.py' -q`:
  313 discovered, 311 passed, 2 platform skips (Windows symlink privileges and
  POSIX read-only acceptance); no failures. Includes all 20 new identity tests.
  Earlier 74-test runs were focused regressions, not the full suite.
- Frontend: `npm run lint`, `npm run typecheck`: passed. `npm run test:unit`: all
  76 passed with loopback enabled and a canonical task-owned Windows TEMP path.
- Full browser: `npm run test:e2e`: all 26 passed (21 existing + 5 new) against an
  isolated generated database/media root. The runner builds the production app.
  Existing RSC refresh checks wait for the response and rendered version instead
  of stream closure, retaining the state and duplicate-write assertions.
- Screenshots: `frontend/e2e-artifacts/identity-review-mobile.png`,
  `identity-review-desktop-zh.png`, `identity-reconnect-confirm.png` (task artifacts,
  not committed). E2E controller paths are restricted to its owned temporary root.
- Independent review found and drove regressions for shared assets, conflicting
  scan availability, artwork URLs, large-file hashes, scan/confirm races, and
  initial evidence becoming stale after same-Film provider sync, and old undo
  tokens after reconnection. Final independent review and `git diff --check` passed.
- Hosted CI and the two platform-specific tests still require confirmation on
  the draft PR before merge. Local checks do not claim hosted CI completion.

## Remaining limitations

- Cross-Film resolution and historical/incomplete/stale evidence are inspection-only.
- Reconnect deliberately rejects multipart editions and missing complete hashes.
- Full hashing reads the source file during preview and confirmation; confirmation
  holds the SQLite writer lock while validating, so concurrent writers can wait.
- External processes can still modify media after validation. No filesystem write
  or destructive database deletion occurs in these decisions.
- No real library, Docker/WSL installation, release or deployment was used.
