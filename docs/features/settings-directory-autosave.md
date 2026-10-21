# Compact settings and media-directory autosave

Status: In Progress
Last updated: 2026-10-21
Base: main de1b09a42fed11361895802febabef3ef8250896 (PR #36)

## Goal and scope

- Remove visible Not Watching text without changing watcher behavior.
- Use compact language choices while retaining explicit zh/en semantics, keyboard
  activation, selected state and the existing language save/navigation behavior.
- Put an accessible, tooltip-equipped add icon beside Media directories. Remove
  the directory Add and Save buttons. Keep existing per-path status/remove icons.
- Shorten automatic root-organization scope/risk wording, and add one accurate
  sentence describing automatic video checks after verifying its scheduler.
- Move the existing explicit API connection test to an accessible icon beside
  AI Model; remove its separate heading and visible Test API Key label.
- Base URL uses the same completion/serialization rules; remove Save and provider
  presets. Write only its dedicated endpoint, preserve other AI drafts/settings,
  and never start connection testing or model refresh as a save side effect.

## Directory completion and persistence contract

- Adding an empty row creates only a draft. Typing never sends a write.
- Blur or Enter commits a complete, syntactically valid list. The backend remains
  authoritative for host-path normalization, duplicate roots and overlap checks.
- Removal and Use as first commit their resulting valid list immediately.
- One request runs at a time. Completed newer edits are coalesced; further typing
  invalidates an older queued snapshot. A response can clear only its own draft
  version, and never overwrites newer input with an older normalized response.
- A failed request retains the latest draft, exposes a retry action, and does not
  unlock scanning. Discard remains available while no save is in flight.
- Drafts and save state survive category navigation through the existing Settings
  session. Direct scans and the three scan-workflow retries stay blocked until
  successful persistence or discarding back to confirmed configuration.
- The global background-workflow Retry UI/handler and central scan/retry hooks
  share that guard. A pending save remains guarded after leaving Settings; an
  abandoned, unsent draft releases its guard. Other retries and cancellation
  remain available, and guard ownership cannot clear another session's blocker.
- The ordinary Library scan icon reflects the same guard. The empty-Library
  first-scan form checks it before its legacy directory write, so a pending
  settings save cannot race that write even if form submission is attempted.
- Saving roots does not scan files. No backend contract, real media/configuration,
  AI call, deployment or additional global navigation is part of this change.

## Verification plan

- Controller unit tests with deferred responses: empty/incomplete input, explicit
  completion, sequential/coalesced writes, stale success/failure, normalization,
  retry and edits while a write is in flight.
- en/zh desktop and 390/320px: compact language choices, add tooltip/keyboard,
  no Not Watching or Add/Save buttons, new/edit/remove/reorder and reload.
- Isolated synthetic roots: server duplicate/overlap validation, failed saves,
  retry, fast input, cross-category draft retention and all scan guards.
- Required lint/typecheck/unit/build, focused and full real API E2E, visual QA,
  draft PR, exact-head CI and independent review before authorized normal merge.

## Evidence and remaining work

- Frontend unit suite: 113 passed, including ten completion-controller tests and
  two guard ownership/lifecycle tests. Lint and TypeScript checks passed.
- Production webpack build passed. Windows full real API browser run: 155 passed,
  one backup-download timeout and eight subsequent serial backup cases not run.
  This is not a complete local suite pass. Linux CI must run all 164 cases,
  including the nine backup cases, before merge.
- Final focused verification covers the completed Settings controls plus the
  added Library/first-scan guard, blur saves and preservation of unsent key input.
  All 24 Settings autosave/Library cases passed on the final implementation.
  Exact-head CI evidence is recorded in the PR.
- Visual QA: General, Library and Connections in en/zh at 1440, 390 and 320px;
  narrow pending-scan and failed-URL retry states. Reviewed the 18 normal layout
  screenshots and four state screenshots, and inspected the production app in
  real Chrome. No horizontal overflow, missing labels or unreachable controls.
- Screenshot filenames use `autosave-<locale>-<width>-<section>.png` plus
  `autosave-<locale>-320-pending-scan-guards.png` and
  `autosave-<locale>-320-url-retry.png` under the ignored E2E artifact directory.
  The requested Library archive failed during preparation; no new Library IDs
  were confirmed. Keep this separate from successful screenshot generation/QA.
- Independent review and final CI are required before the authorized normal
  merge. No deployment, real provider request or user-media/configuration write
  was performed. The test harness uses its own synthetic media and SQLite.

## Retained information and boundaries

Directory labels, accessible state tooltips, incomplete/overlap/error messages,
saving/retry feedback and the scan blocker remain necessary. Automatic root
organization still states root scope, high confidence and review for the rest.
Automatic video-check wording reflects idle-gated new/changed checks and bounded
stat sampling over existing DB-known assets, not repeated decoding of every file.
TMDB key scope/source and its explicit Save/Test actions remain unchanged. Only
the requested Base URL controls autosave; its dedicated endpoint never writes a
model/key field or starts model refresh/connection testing.
