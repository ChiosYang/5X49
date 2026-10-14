# Manual match refresh race

Status: In Progress
Last updated: 2026-10-14
Related: main push CI run 38361005723

## Goal

Keep Film detail controls locked from manual-match submission through read refresh
and canonical Film navigation, even when library events update the same URL by RSC.

## Scope

- Preserve the current detail's busy state across canonical Film identity changes.
- Reject duplicate confirmation clicks, allow retry after failure, and prevent a
  late response from navigating after the user leaves the detail.
- Preserve the existing cinematic styling and matched toolbar disclosure.

## Acceptance criteria

- [x] Event-driven RSC can replace Film data while confirmation is in flight
  without unlocking controls or permitting another confirmation.
- [x] The lock spans cache refresh and navigation commit.
- [x] Confirmation failure is retryable; a read refresh failure does not resubmit.
- [x] Leaving during either the POST response or read refresh discards local
  pending state and ignores late canonical navigation.
- [x] Full E2E is complete: 70/70 passed, including all five new regressions.
- [ ] PR CI results are recorded in the coordinating task.
- [ ] Independent review is completed before the coordinating task merges.

## Decisions

- Key the controls by the requested route Film ID. Canonical data may change
  within that route; navigating to another route must create a fresh instance.
- Use an immediate ref guard for confirmation and explicit pending state through
  the write and cache reads, then React transition state through RSC navigation.
- Retain the submitting metadata control while pending so a background refresh
  cannot replace it with an enabled matched toolbar before completion.
- Synchronize profile labels by both Film ID and profile timestamp.
- Ignore confirmation continuations after the controls have unmounted.
- Gate real POST responses, browser reads, and RSC separately. All regression
  data uses the owned temporary SQLite/media harness; no new fixed sleeps.
- Keep the PR draft for the independent review requested by the coordinating task.

## Verification evidence

- Base: main `03a415d1388ae313d48df6206d620b9dd6a5468d`; clean existing checkout.
- Reproduction on the unchanged production implementation: with the successful
  POST response held, a real library event refresh rendered the canonical Film
  title under the original URL, while Favorite became enabled. The busy
  assertion failed; the trace and output are preserved in the execution task.
- `npm run test:e2e`: 70/70 passed in 3.4 minutes, with long Windows TEMP/TMP
  paths. Includes five new matching regressions, the unchanged original
  cinematic-matching test, and the production deep-reset regression.
- `npm run lint`, `npm run typecheck`, `npm run build`: passed.
- `npm audit --audit-level=high`: zero vulnerabilities.
- All business/process unit tests: 85/85 passed. Full `npm run test:unit`:
  86/89 passed on Windows; three existing Next ESLint root-dir tests fail with
  Windows drive-path handling. Linux PR CI remains required.
- `uv run python -X utf8 -m unittest discover -s . -p 'test_*.py' -q`:
  386 tests, OK (3 skipped), with an isolated synthetic database and canonical
  long TEMP/TMP paths. Short Windows paths initially caused two boundary errors.
- `uv run python -m compileall -q app`: passed.
- RC tooling tests: 11 tests, OK (1 skipped); deployment healthcheck unit tests:
  2/2 passed. Full scripts discovery could not complete its two Compose tests
  because Docker is not installed on this host; PR CI runs them on Linux.
- First full E2E attempt: 49 passed, 1 failed, 19 not run. The earlier scan test
  compared a Windows short temporary path with its canonical long form. The
  full suite then passed with long TEMP/TMP paths, retaining every assertion.

## Remaining risks

- Awaiting PR checks and the coordinating task's independent review. Neither is
  claimed complete. The local diff review found no blocking issues.
- After merge, verify the remote main commit and its **push** workflow by SHA
  through the workflow-runs API; commit-workflow lookup filters PR events.
- No release or deployment is part of this change.
