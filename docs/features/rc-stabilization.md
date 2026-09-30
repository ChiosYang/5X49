# W11 RC stabilization and W12 readiness

Status: Done
Last updated: 2026-10-01
Related: Product roadmap W11/W12; Product Spec Gates C, D and E

## Goal

Verify supported upgrades, backup/restore and core failure paths with isolated
data, fix release-blocking defects, and make the remaining Beta decisions
reviewable. Engineering acceptance does not establish real-user activation or
retention, live-model quality, or deployment acceptance.

## Scope

- Same-epoch schema upgrades, failure rollback, verified backup and offline restore.
- Projection verification/rebuild and bounded, read-only diagnostic guidance.
- No-key, read-only media, low-disk and provider-failure behavior.
- Backend/frontend regression and current-source installation checks where available.
- Installation, privacy, known issues and W13–W14 cohort validation preparation.
- Remediate critical/high frontend dependency findings discovered during
  container installation; keep Next.js and its ESLint configuration aligned.

## Non-goals

- Production database/media changes, historical pre-epoch conversion, publication
  or external recruitment messages.
- Claiming Gate B or user-validation gates passed using deterministic fixtures.

## Decisions

- Work sequentially in the existing checkout on `ai/rc-stabilization`.
- Use disposable databases, media fixtures and explicit environment overrides;
  never load or change real application data or credentials for acceptance.
- Preserve public API shapes. Prefer existing lifecycle services and unittest.
- Freeze feature expansion while release evidence is gathered.

## Acceptance criteria

- [x] Supported upgrades preserve canonical data and repeat startup is stable.
- [x] Failed migrations cannot leave committed schema changes with an unapplied journal.
- [x] Backup verification/restore reject stale, corrupt, busy and low-space inputs safely.
- [x] Projection repair and diagnostic checks have reproducible evidence.
- [x] No-key, read-only media and external-provider failures preserve local use/data.
- [x] Relevant regression, frontend checks and code review complete.
- [x] Operator runbook and known issues identify actual support/recovery boundaries.
- [x] Beta gate and cohort tracking distinguish passed, blocked and unmeasured evidence.

## Slices

1. Inspect lifecycle contracts and reproduce uncovered safety failures — Complete.
2. Fix defects and add focused recovery/failure regression coverage — Complete.
3. Run isolated acceptance and review the final diff — Complete.
4. Record release decision, operator guidance and product-validation plan — Complete.

`Done` covers the engineering work and validation preparation above, not
Public Beta recruitment, publication, real-user evidence or Gate B.

## Defects fixed

- SQLite legacy transaction mode left DDL committed on migration failure. The
  applied journal was also committed separately. A real transaction now includes
  DDL/data and the final journal write; failure leaves retryable state.
- Restore accepted a backup modified after verification and could overwrite a
  changed target. It now compares the prepared copy with the original manifest,
  rechecks target state, refuses unconfirmed WAL and probes offline access.
- Restore lacked destination-space preflight and bounded mid-copy storage
  failure handling. The original target and safety backup remain recoverable.
- Projection `verify` silently bootstrapped/repaired stale state; `rebuild` was
  blocked by the same corrupt projections it should repair. Verification now
  opens read-only and rebuild bypasses only startup projection verification.
- Next.js 16.1.6 was affected by published critical/high advisories. Upgrade to
  16.3.8 with matching ESLint config and compatible transitive fixes; final npm
  audit is clean. CI now rejects high/critical dependency audit findings.
  References: [AVIF optimization advisory](https://github.com/vercel/next.js/security/advisories/GHSA-2xp9-vwfh-vxw4)
  and [Windows server advisory](https://github.com/vercel/next.js/security/advisories/GHSA-p293-qw3h-jr36).

An operator-facing `python -m app.backup` command reuses the existing verified
online backup service without booting the application. REST routes and public
response shapes are unchanged.

## Verification evidence

- Baseline: `main` at `fbccc54`; clean checkout before this task.
- `docker info --format '{{.ServerVersion}}'` — blocked: Docker daemon is not
  reachable at the configured OrbStack socket, including outside the sandbox.
  Resolved by starting the installed OrbStack with user approval; Docker 28.5.2
  then became available.
- `uv run --locked python -X utf8 -m unittest discover -s . -p 'test_*.py' -q`
  from `backend/` — **263 passed**, 23.8 seconds. Environment overrides isolated
  `SQLITE_DB_PATH`, `MEDIA_DIR`, `OPERATION_MANIFEST_DIR`, disabled watching and
  cleared provider keys; caches were placed under `/private/tmp`.
- `uv run --locked python -m compileall -q app` — passed.
- New coverage: v1/v2/v3/v4 → v5 facts and verified pre-upgrade backups; failed
  DDL and final journal writes; low-space refusal; manifest drift; target drift;
  busy writer; WAL backup/restore boundary; interrupted copy and cleanup; backup
  CLI privacy; read-only verify and repair of corrupt projections.
- `test_rc_acceptance` runs the real application lifespan in a separate process
  with synthetic POSIX read-only NFO/media. It checks repeated scans, local
  profile/Viewing/DNA/Ask operations and restart persistence with no provider key.
- Existing deterministic suites exercise Ask timeout/invalid output/busy states,
  TMDB 429/5xx/timeouts, Analysis rollback, Workflow retries and projection failures.
- Frontend after dependency patches: `npm run test:unit` — **44 passed**;
  `npm run lint`, `npm run typecheck -- --incremental false`, `npm run build`
  — passed. `npm audit --cache /private/tmp/5x49-rc-npm-cache` — **0 vulnerabilities**.
  Initial typecheck found stale `.next` references to the removed watch-history
  route; the old generated cache was moved to temporary storage and regenerated.
- Both repository Dockerfiles built successfully from the final candidate in
  isolated contexts containing source/lockfiles, no local env/data. Linux ARM64
  images: backend `892980dc5bd8`, frontend `c4d6880593cf`.
- Isolated Compose project `5x49-rc-20261001`, loopback ports 18549/15549,
  disposable database and read-only generated media: frontend API proxy, fresh
  scan/reconcile, profile/Viewing/DNA/Ask, and 10 localized core page responses passed.
- Container offline backup → verify → mutate personal state → stopped-writer
  restore → projection verify → restart: original Film identity, rating, notes
  and Viewing restored. All eight projection checks passed. Final backup CLI
  ran in the candidate container without application startup.
- Browser: English Ask no-key form, condition preview, explicit confirmation and
  fact explanations; Chinese Diary and Film detail showed the restored score and
  note. 390px layouts had no horizontal overflow; sampled pages emitted no
  console warnings/errors. Screenshot:
  `/private/tmp/5x49-rc-containers-bmqtluxw/restored-diary-mobile.jpg`.
- Final code review covered migration transaction boundaries, manifest/target
  revalidation, stopped-writer requirements, low-space behavior, verification
  side effects and dependency changes. `git diff --check` passed.
- CI YAML parsed successfully; the frontend audit step is present. Temporary
  browser tab, test containers and their network were removed after acceptance.
  Local test images, disposable backups and screenshot remain available for review.

## Remaining risks

- Registry publication was not part of this acceptance. The published `latest`
  images and AMD64/Windows/NAS environments
  were not certified by the local ARM64 container run.
- Gate B live Evidence/human scoring and real Alpha/repeated-use evidence remain
  unverified; this task cannot substitute synthetic results for them.
- See `docs/release-readiness.md` for the release decision and known boundaries.
