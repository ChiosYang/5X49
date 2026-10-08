# Interaction continuity and recovery

Status: Done
Last updated: 2026-10-08
Related: authorized seven-item interaction review

## Goal

Make existing import, Library, review, Diary, Ask and background-task flows usable
with keyboard/touch, explicit outcomes, and recoverable state.

## Scope and acceptance

- [x] Save and validate the current directory before scanning that exact path;
      restore the accepted scan workflow after refresh.
- [x] Expose card actions and filter/sort disclosures without hover; show mutation
      failures and retry without navigating away.
- [x] Keep every active workflow plus bounded history; distinguish cancellation
      and expose cancel/retry failures.
- [x] Default no-key Ask to its form, offer local candidates, allow one-constraint
      changes after zero results and require renewed confirmation.
- [x] Preserve safe list return destinations, focus/scroll anchors, stable card
      identity and confirmed structured Ask state without storing questions.
- [x] Inspect metadata candidates before confirming; allow skipping/revisiting
      without marking them complete; retain organization preview safeguards.
- [x] Separate Viewing write success from refresh failure, and undo only the
      newly created Viewing ID while allowing same-day rewatches.

## Decisions

- One task branch/PR; no releases, deployments or unrelated product features.
- Existing user work was already included in main before this task; workspace
  started clean. Its earlier stash backup is retained.
- Persist only bounded, session-local navigation/confirmed Ask/scan references;
  storage failures must not block use. Natural-language questions are not stored.
- Existing canonical identity and destructive-operation contracts are preserved.
- Add optional workflow active-list behavior, keeping the existing default shape.

## Slices

1. Import and workflow recovery — implemented and independently reviewed.
2. Card access and return continuity — implemented and independently reviewed.
3. Ask refinement and structured return state — implemented and independently reviewed.
4. Candidate review and Viewing receipt/undo — implemented and independently reviewed.

## Verification evidence

- Frontend: `npm run lint`, `npm run typecheck -- --incremental false`,
  `npm run test:unit` (66 passed), and `npm run build` passed.
- Backend: `UV_CACHE_DIR=/tmp/5x49-uv-cache uv run --no-sync python -X utf8
  -m unittest discover -s . -p 'test_*.py' -q` passed (265 tests);
  `uv run --no-sync python -m compileall -q app` passed.
- Release-tool unit tests: `uv run --no-sync python -m unittest discover
  -s ../scripts -p 'test_*.py' -q` passed (11 tests); no release was run.
- Independent cross-review fixed stale Library event reconciliation and localized
  return paths. Browser review fixed lost task-action focus, SWR's swallowed read
  failures, and a pre-hydration return action that could discard list filters.
- Browser: local `/usr/bin/chromium` driven with Playwright against the actual
  Next.js dev frontend and a synthetic HTTP API on `127.0.0.1:8877`. Covered
  delayed/invalid directory saves, pinned scan paths and scan refresh recovery;
  nine active tasks and failed cancellation; visible card actions, retry and
  keyboard Escape; no-key Ask, strict zero-result refinement/reconfirmation,
  local fact selection and restored structured query; metadata inspection,
  search/skip/confirmation; filtered detail return; same-day Viewing exact-ID
  undo; and successful POST followed by failed GET with GET-only recovery.
- `git diff --check` passed. Browser scripts and synthetic fixtures were temporary
  verification tools, not an installed end-to-end test suite.

## Remaining risks

Browser checks used desktop and narrow viewport emulation with synthetic data.
They do not verify a real NAS/media directory, TMDB or model-provider integration,
physical touch devices, or screen-reader behavior. No external user data was
mutated. Return/Ask state is session-local and intentionally expires or disappears
when browser storage is cleared; natural-language questions are never persisted.
