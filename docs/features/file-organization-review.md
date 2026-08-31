# File Organization Review

Status: Complete
Last updated: 2026-08-31
Related: `docs/product-spec.md` sections 3–7

## Goal

Replace the prototype Librarian Agent console with a reviewable, bilingual file
organization flow whose preview matches the file move that will actually run.

## Scope

- Review direct media-root videos and legacy `media/inbox` videos together.
- Preview the selected TMDB identity, target directory, video name, sidecars,
  conflicts, and metadata follow-up before a manual move.
- Require a fresh confirmation token for each manual organization Workflow.
- Keep explicitly enabled high-confidence root automation unchanged.
- Retire the Librarian Agent API, UI, tools, test script, and dependencies.

## Non-goals

- Batch confirmation or a separate organization page.
- AI-based filename identification.
- Automatic migration or deletion of legacy inbox files.
- Removing generated NFO or artwork when restoring a file location.

## Existing behavior

The root organizer already uses TMDB confidence thresholds, durable Workflows,
controlled file manifests, Activity Events, and bounded file-location restore.
The separate Librarian Agent instead streams framework-oriented logs and can
move inbox files directly from an LLM tool call without a user preview.

## Acceptance criteria

- [x] The management UI contains no Librarian Agent or reasoning console.
- [x] Root and legacy inbox videos appear in one queue without absolute paths.
- [x] Manual organization cannot run before a current, conflict-free preview.
- [x] Preserved and standardized video/sidecar naming match the preview.
- [x] Source or target drift after preview fails before any file is moved.
- [x] Advanced auto organization still processes direct-root videos only.
- [x] File-location restore remains available from Activity.
- [x] Agent-only dependencies and documentation are removed.

## Decisions

- Manual organization is item-by-item; no batch API is introduced.
- `preserve_stem` is the manual default; `title_year` is an explicit toggle.
- Manual target collisions block confirmation and never expose overwrite.
- The legacy inbox is review-only and is not added to automatic organization.
- Restore copy describes its bounded file-location behavior accurately.

## Open questions

- None.

## Slices

### Slice 1 — Safe organization contract

Status: Complete

- Intended behavior: unified discovery, exact preview, drift-resistant confirm.
- Likely affected areas: metadata organizer, API contracts, Workflow actor.
- Dependencies: existing TMDB client and operation manifests.
- Verification: focused organizer, route, Workflow, and restore unit tests.

### Slice 2 — Review workspace

Status: Complete

- Intended behavior: cinematic review rows with source, match, target, conflicts,
  naming choice, and one-item confirmation.
- Likely affected areas: management client, review queue, translations and types.
- Dependencies: Slice 1 API.
- Verification: frontend unit/static checks and disposable-library browser review.

### Slice 3 — Agent retirement and documentation

Status: Complete

- Intended behavior: remove the unused console stack and stale guidance.
- Likely affected areas: API router, backend dependencies, API/Skill docs.
- Dependencies: Slices 1–2.
- Verification: lock validation, route contract, repository search and full checks.

## Verification evidence

- `uv lock --check` — passed; 36 packages resolved.
- `uv run python -m unittest test_root_video_organizer.py test_api_routes.py
  test_event_sourced_commands.py test_workflows.py -q` — 37 tests passed.
- `npm run test:unit` — 10 tests passed, including title/year versus TMDB ID
  parsing coverage.
- `npm run lint` — passed.
- `npm run typecheck` — passed.
- `npm run build` — passed with all locale routes generated.
- Project Skill validation — `5x49-api-docs`, `5x49-backend`, and
  `5x49-review` all passed `quick_validate.py`.
- Disposable-library browser review — passed in Chinese and English for root
  and legacy-inbox labels, long filenames, preserved and standardized names,
  qualified subtitle suffixes, conflict-disabled confirmation, settings risk
  copy, desktop layout, and a 390 px mobile viewport. TMDB responses were fixed
  test fixtures; no real media library or external account was used.

## Remaining risks

- File-location restore intentionally leaves generated NFO and artwork in the
  organized folder; the UI describes this as restoring file locations rather
  than a complete rollback.
- Browser verification used deterministic TMDB candidate and preview fixtures;
  live TMDB behavior remains dependent on a valid deployment API key.
