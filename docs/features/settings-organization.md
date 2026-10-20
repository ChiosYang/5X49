# Settings and maintenance organization

Status: In Review
Last updated: 2026-10-20
Base: main bd1a092a48709dd83835f50c56d19c2d1c296fa2 (PR #35)

## Goal

One Settings area with the eight categories in the user's order. Desktop uses
an internal left navigation and topic groups on the right. Mobile uses a category
picker with normal URL/history navigation. No Settings/Maintenance top tabs, new
global navigation, More maintenance entry or roadmap placeholders.

## Complete migration map

| Category / canonical section | Existing function | Destination / retained behavior |
| --- | --- | --- |
| 1. General / `general` | Interface language | Direct language control; existing save/error behavior and locale navigation. Remove the unimplemented roadmap. |
| 2. Library / `library` | Ordered media roots, status, remove, first-root ordering | Existing input icons, Add/Save/Discard, validation and explicit save. |
| | Watch library, automatically organize root files | Scan and organization rules; existing autosave and risk information. |
| | Artwork language, confirmation before scraping | Metadata and artwork; existing autosave and confirmation semantics. |
| | Automatic video checks enabled | Automatic control only; write only `enabled`, preserve hidden schedule/budget/defaults. |
| 3. Service connections / `connections` | AI model selection/search, API connection test, base URL and presets | AI group; existing explicit base-URL save and model autosave. No new AI call on entry. |
| | TMDB credential source/configuration, save and test | TMDB group; environment override and masked secret behavior retained. |
| 4. Library maintenance / `library-maintenance` | Scan all directories, coverage/history/errors | Existing MediaScanResults component; still disabled while directory draft/save is pending. |
| | Bulk scrape, progress/error/last run, metadata review queue | Explicit existing operation and link to Library metadata review. |
| | Refresh external scores, progress/error/last run | Explicit existing operation. |
| | Missing editions, search/show more, scan again, confirmed removal | Reuse LibraryOfflineCare; retain impact/confirmation and record-only deletion behavior. |
| | Root-video candidates, organizing state | Existing Library inbox review destination and runtime facts. |
| | Recent workflows, cancellation/retry, Activity destination | Existing workflow APIs and controls; actions remain explicit. |
| 5. Video checks / `video-checks` | Queue library check, pause/resume, cancel queue | Existing controls moved out of Library settings. |
| | Filter, paging, quick/deep results, version evidence, detail errors | Reuse VideoHealthMaintenance, retaining loading/error/empty states. |
| | Per-file cancel/retry, notification receipt, open Film | Existing actions and navigation; no automatic queue on entry. |
| 6. System diagnostics / `diagnostics` | Database/schema/read models, media permission, backup-space estimate, TMDB configuration | Existing read-only local diagnostics and refresh. |
| | TMDB/poster connectivity probes | Existing explicit probe and disclosure of its network request. |
| | Watcher, scan, metadata, score, organizer running/error/last-run state | Runtime group; consolidate the old management overview here. |
| | Complete projection consistency command | Existing CLI instruction, clearly an instruction rather than a browser action. |
| 7. Backup and recovery / `backup` | One-click sanitized database backup, status, retry same request, download/redownload | Reuse MaintenanceBackup and its idempotency/timeouts/recovery receipts. Generation still requires the existing explicit action. |
| | Downloaded ZIP restore instructions | Existing RESTORE.txt/offline CLI guidance; no new browser restore/upload action. |
| | Full database backup, verification manifest, Docker invocation, offline restore | Existing CLI commands and safeguards; explicitly includes configuration and may include credentials. |
| | Portable personal-record export | Existing CLI instruction and no-import limitation. |
| 8. Data cleanup / `cleanup` | Clear all library data | Existing LibraryDangerZone; preserve impact, typed phrase, confirmation and active/unavailable workflow blocks. |

The former management diagram's status and action affordances are represented
by these topic groups and existing Library review destinations. Its auxiliary
concept-study routes remain available; they are not production navigation.
Identity Review stays in Library More. Library/Explore presentation and global
transparent navigation remain intact.

## Navigation and compatibility

- Canonical URLs remain `/settings?section=<category>`, so categories support
  refresh, Back and Forward. Settings-local drafts survive category navigation.
  Maintenance and cleanup confirmation flows unmount when leaving their category,
  releasing modal focus/background/scroll isolation even on browser Back.
- Video result filter, offset and selected inspection are encoded in `health_*`
  query parameters. Film return context permits only the Video checks settings
  category, alongside the existing local list destinations.
- `/settings?section=integrations` resolves to `connections`.
- `/settings?section=maintenance` and `/admin/health` resolve to `diagnostics`.
- Existing danger anchors resolve to `cleanup`; backup/restore anchors resolve
  to `backup`. The Library automatic-check anchor remains in `library`.
- `/library/manage` resolves to Library maintenance; `#video-health` resolves to
  Video checks, backup anchors to Backup and recovery, and old metadata/root
  review anchors retain their Library review destinations.
- Internal production links use canonical destinations; legacy entry points
  do not render the old combined management/diagnostics page.

## Invariants

- Page entry never starts a scan, scrape, AI operation, backup generation or
  configuration update. Existing pending backup receipt recovery is retained.
- Directory changes require Save. Scan remains blocked until pending directory
  changes are saved or discarded, even across categories.
- Toggle/save semantics, permissions, confirmation and backend behavior remain.
- Hidden video scheduling fields, budget and runtime-statistics prose stay hidden.
- Necessary state, errors, action impact, privacy and recovery boundaries remain.
- No backend feature expansion, real media/configuration changes or deployment.

## Verification plan

- Unit checks for canonical category order and legacy route/anchor mapping.
- en/zh at 1440/390/320px: all categories, secondary groups, mobile picker,
  keyboard/focus, strict overflow checks after fonts and animations settle.
- Back/Forward/refresh, legacy links, locale navigation and review/Film context.
- Read-only entry, loading/failure/retry, roots and service drafts/saves, autosave
  failure, maintenance jobs, video results/retry, backup/download and danger guards.
- Required lint/typecheck/unit/production build and full isolated E2E, followed
  by screenshot review/Library upload, draft PR, exact-head CI and independent review.

## Progress

Migration inventory and implementation complete. Typecheck, lint and all 100
unit tests passed. Existing backup backend tests passed (11 tests). Production
webpack builds passed in the local isolated runner (the existing Windows
Turbopack IPC limitation remains; CI uses its normal build command).

The full 150-case Windows E2E run passed 139 cases, failed two stale Chinese copy
assertions and the existing Windows backup-generation case; its eight dependent
backup cases did not run. The copy assertions confused the newly approved category
label with the former decorative eyebrow. Updated those assertions; the final
build passed all 23 organization/full-route-copy cases, including both locales,
all eight categories at 1440/390/320px, keyboard/history/legacy entry, drafts,
read-only entry, diagnostic errors, cleanup guards, video context/retry, a real
synthetic scan, and intercepted bulk/retry/cancel operations. No real AI or
external provider calls were made. Earlier focused Library/video/root cases
also passed. The Windows backup failure displayed an honest generation error;
the UI handler and backend are unchanged. Complete Linux CI, including all nine
backup cases, and independent review remain merge requirements.

Final modal-history hardening build passed lint/typecheck/build and all 16
organization cases: 14 passed in the complete run, then both expanded diagnostic/
cleanup history cases passed after correcting the test's mobile navigation helper.
Browser Back releases confirmation focus/background/scroll isolation; Forward
returns to an unopened confirmation flow. The application bundle was unchanged
between those two runs.

Visually reviewed all 48 category screenshots in six contact sheets and inspected
representative pages at full resolution, including the final build in real Chrome.
No horizontal overflow at 320px; labels, errors, action impact and privacy/recovery
boundaries remain. The page retains automatic-organization and scrape-confirmation
explanations, scan-coverage limits, video-check limits/version evidence, provider
probe disclosure, backup scope/privacy/download truth, and irreversible cleanup
confirmation because they affect safe use.

## Confirmed Library screenshot uploads

| View | Library file ID |
| --- | --- |
| General, en 1440 | `libfile_97428948d3cc81919d4fedc19b19e103` |
| Library, zh 320 | `libfile_452fedddee588191a33fa45e777c0934` |
| Connections, en 390 | `libfile_42e6cda6c29081918b6d4e50fadab854` |
| Library maintenance, en 1440 | `libfile_0fe2002846f481918af055d81bf9aba3` |
| Video checks, en 320 | `libfile_5d3b4ced3a6c819194a0f16c77938d3d` |
| Diagnostics, zh 390 | `libfile_447a4f3ffd488191b7d57718f4a13410` |
| Backup/recovery, zh 390 | `libfile_1e9fa29942208191920dda04c43ea23b` |
| Cleanup, en 320 | `libfile_6dfff187efa48191823552aced95b418` |
