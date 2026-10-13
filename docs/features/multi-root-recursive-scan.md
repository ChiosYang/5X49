# Multiple media roots and recursive discovery

Status: Done
Last updated: 2026-10-13
Related: foundational capability 6 of 6; baseline PR #23

## Goal and scope

Discover supported local editions across ordered media roots and every nested
directory. Preserve existing single-root configuration, Film/LibraryItem IDs,
manual metadata/history, Film reviews, Viewing records/reviews and preferred
editions across repeated scans and restarts. Configuration, current access and
historical scan coverage are separate user-visible states.

No real media, production migration, deployment, release, Docker installation,
or deep-reset repair is included. Tests use owned synthetic files/databases;
new fixtures do not depend on `clear_all_data`.

## Baseline and approved decisions

- Verified remote main: `b3d1a980d7f4422c34c3973206118f031e1f29dd`.
  Task branch: `ai/multi-root-recursive-scan`; no extra worktree created.
- Parent relayed the user's approval of option A on 2026-10-13: ordered
  `media_dirs`, canonical deduplication, reject parent/child overlap, remove root
  without deleting its records. Legacy writes replace only the first root.
- Saving up to 32 absolute host roots is independent of scanning and allows
  offline paths. Empty list disables access. Configuration read errors fail
  closed. A chosen root alias is canonicalized once when saved; links/junctions
  inside roots and subsequently replaced roots/ancestors are not traversed.
- Full scan includes direct-root files and all non-hidden nested directories,
  retaining per-video NFO and multipart rules. Watchers use the same tree bounds.
- A failure in any root suppresses missing reconciliation for the entire run.
  Cancellation before the missing transaction commits rolls it back. Positive
  observations may persist. Even full coverage requires explicit successful
  enumeration proving absence under a still-accessible configured root.
- Removing/offlining a root never proves its editions deleted. Queued work,
  media serving, scraping, organizer sidecars, restores and identity decisions
  revalidate current roots. Existing absolute locators never fall back to a
  same-named folder in a different root.
- Same-Film missing-edition reconnection remains conservative; cross-Film
  reassignment with manual corrections remains blocked. No automatic content
  merge across films was added.
- Artwork uses stable root IDs and full relative paths. Legacy media URLs use
  the first root. Root organizer UI remains first-root; automatic watchers use
  their own root. Each Docker root needs a separately configured mount.
- Database backups continue excluding the entire Setting table, including
  media root configuration and scan receipts. Restore requires reconfiguration.

## Slices and acceptance

- [x] Ordered configuration, compatibility, deduplication/overlap and removal.
- [x] Recursive discovery and watching, direct-root editions and distinct artwork.
- [x] Shared boundaries for current/queued reads and filesystem operations.
- [x] Conservative missing decisions and persisted complete/partial/interrupted
      receipts with per-root counts, errors and skipped-link counts.
- [x] English/Chinese settings and management UI, preserving existing typography,
      large headings and transparent navigation.
- [x] Synthetic identity/manual metadata/review/Viewing/filter/backup regressions.
- [x] Independent source review and fixes.
- [x] Final full backend suite, frontend units/lint/typecheck, production build
      and complete real-API browser E2E.
- [x] Desktop and narrow-screen pixel inspection; Library screenshot delivery
      or precise local-only limitation.

Local implementation and acceptance are complete. Draft PR delivery is tracked
in the task; the parent owns Linux CI verification and merge.

## Verification evidence

- Locked dependencies: `uv sync --project backend --frozen`; `npm ci`.
- `python -m unittest discover -p 'test_*.py' -q`: 374 tests, 371 passed,
  3 skipped on Windows (two real symlink cases require host privileges; the
  POSIX permission case is not applicable). Native Windows junction, cross-root
  same-Film reconnect/revocation and pending-watcher revocation cases passed.
  Log: `backend/data/task6-full-final.log` (local ignored evidence).
- `python -m compileall -q app`: passed.
- `npm run test:unit`: 89/89 passed. `npm run lint` and `npm run typecheck`
  passed. Logs: `frontend/e2e-artifacts/task6-{unit,lint,typecheck}.log`.
- Production Next build and full `npm run test:e2e`: 61/61 passed in the final
  run (`frontend/e2e-artifacts/task6-final-e2e.log`). Older synthetic fixtures now
  explicitly configure their roots. New multi-root tests cover settings UI, overlap rejection,
  nested/direct files, offline/removal/restart, review retention and filters.
- Actual Chromium screenshots visually inspected at 1440px desktop and 390px
  narrow width: large headings, typography and transparent navigation retained;
  no new content overflow. Final files under `frontend/e2e-artifacts/`:
  `media-roots-desktop-en.png`, `media-roots-offline-narrow-zh.png`, and
  `media-roots-manage-desktop-zh.png`.
- Current Library skill's prepared-upload helper was used for the ordered
  three-screenshot batch. It returned `Library prepare_uploads is not available`.
  No fallback upload was attempted, no Library identity was confirmed, and local
  evidence remains available. Result: `task6-library-result.json` in that folder.
- Independent reviewer found and then verified fixes for root-link resolution,
  organizer/sidecar boundaries, dangling backup target links, root-level artwork
  selection, fail-open settings errors, offline same-name folder fallback and
  incomplete-root status. Final source review reported no blocking findings.
  Independently ran 20 new tests (19 pass, 1 host symlink skip) and diff checking.
  Final incremental reviews also approved the watcher revocation guard, actual
  junction coverage, API errors, UI timeout/coverage labels and updated docs.
- Windows tests use canonical short task-owned TEMP/TMP, cleared provider keys,
  disabled dotenv/watching and isolated DB/manifests. Loopback/process permissions
  were approved for test execution. Initial sandbox and 8.3 temp alias failures
  were environmental; no system security setting was changed.

## Remaining risks and limits

- Library upload is blocked as recorded above; screenshots are local only.
- Linux native filesystem behavior will be verified by repository CI; local
  Windows tests also reject both Windows and POSIX traversal grammars.
- Host cannot create real symlinks; deterministic link boundary tests and native
  Windows junction creation/traversal rejection both passed.
- Path validation and subsequent OS access are not atomic against adversarial
  concurrent filesystem replacement. No cross-platform handle-based sandbox is
  claimed. Large/network libraries and Docker runtime are not benchmarked/tested.
- Existing deep-reset FK RESTRICT issue remains outside this task.
- Parent owns checking CI and merging the draft PR. No release/deploy authorized.
