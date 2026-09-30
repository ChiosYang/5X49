# RC / Beta readiness decision

Evidence date: 2026-10-01 (Asia/Shanghai)
Tested source: `ai/rc-stabilization`, based on `fbccc54`; registry publication separate

**W11 local engineering acceptance: Passed. W12 preparation: complete.
Public Beta opening: pending; no recruitment or release performed.**

This decision applies to the tested source candidate and local ARM64 images.
It does not certify mutable published `latest` tags or imply external user or
live-model results. Detailed evidence is in
[the feature record](features/rc-stabilization.md).

## Evidence matrix

| Area | Result | Evidence / practical boundary |
| --- | --- | --- |
| Supported schema upgrade | Passed | v1–v4 → v5, canonical Film/rating/notes/Viewing preservation, backup verification and repeat startup |
| Migration interruption | Passed | Failed DDL and failed applied-journal writes roll back together and can retry |
| Backup / restore preview | Passed | WAL-aware online backup; manifest/hash/size/count checks; preview does not replace the target |
| Full restore | Passed | Isolated container round trip restores original personal state and eight projection families |
| Low disk / busy database | Passed, injected faults | Backup/restore refusal, mid-copy ENOSPC cleanup, stopped-writer and pending-WAL checks; no physical host disk exhaustion attempted |
| Diagnostics / rebuild | Passed | Verify is read-only, missing/stale/corrupt states fail; rebuild can repair corrupt read models |
| No-key / read-only media | Passed | Real lifecycle + POSIX read-only test, and container read-only mount; scan, local queries and restart persistence |
| External provider failures | Passed, deterministic transports | Ask/TMDB/Analysis failure tests, bounded errors, no silent query relaxation; live-provider availability/quality not asserted |
| Backend regression | Passed | 263 unittest tests; module compilation |
| Frontend regression | Passed | 44 unit tests, lint, typecheck, production build |
| Dependency audit | Passed at evidence time | Next.js / eslint-config-next 16.3.8, compatible transitive updates; npm audit 0 findings |
| Current-source containers | Passed | Both Dockerfiles built; isolated Linux ARM64 install/proxy/scan/restart/recovery |
| Browser smoke | Passed, sampled | English Ask; Chinese Diary/detail; 390px overflow checks and clean sampled console |
| Install/privacy/diagnostics guidance | Prepared | [Operator runbook](rc-operations.md), existing README/Docker guide, known boundaries below |
| W13–W14 tracking | Prepared, unmeasured | [Consent, cohort, denominators and follow-up plan](beta-validation.md); no telemetry or scheduled outreach added |

The initially reproduced migration/restore/projection defects and frontend
critical/high dependency findings are fixed in this candidate. No unresolved
blocker/high defect was found within the executed matrix; this is a scoped
review conclusion, not a guarantee that the whole product is defect-free.

## Remaining release and product gates

| Gate | Status | Evidence needed to close |
| --- | --- | --- |
| B — AI relationship quality | Blocked | Exact-model 36-case live run, usable public Evidence, complete human review, strict conclusion; inferred edges stay hidden |
| C — Alpha activation | Unmeasured | At least 3 independent imports, 2 users explaining source/relationship semantics, redacted issue records |
| D — Product signal | Unmeasured | Actual repeat Explore/Diary/Ask behavior and user explanations of the product's value |
| E — Beta Ready | Candidate engineering criteria met; release decision pending | Identify/verify the exact build distributed from the reviewed source; review outstanding C/D evidence before opening recruitment |
| W13–W14 retention | Not started | Consented cohort and elapsed individual observation windows; never infer retention from fixtures |

## Known boundaries and operator actions

- Single-user trusted-host/network deployment only; the backend does not have
  an account authentication boundary. Do not equate CORS with access control.
- Historical pre-epoch databases are unsupported. Preserve them with the older
  compatible application; do not bypass the epoch check.
- Restore requires every writer stopped throughout replacement. Hash and busy
  checks detect tested changes but cannot lock out arbitrary future processes.
  Checkpoint pending WAL offline before calculating a new confirmation hash.
- Database recovery does not restore arbitrary media/NFO/artwork mutations.
  Read-only media permits scanning; organization/enrichment writes need writable
  storage and their own operation-preview/recovery contract.
- Full backups contain private data and can include credentials. Portable
  exports contain personal records. Share neither in public diagnostics.
- Default Compose uses published `latest` tags and fixed single-instance names.
  Current checkout tests do not prove those tags contain this candidate. For
  acceptance record exact image IDs/digests and use isolated project/resources.
- ARM64 was exercised locally. AMD64, Windows, NAS permissions, prolonged soak,
  power-loss durability and large real libraries require environment/user
  evidence beyond this run. Do not silently relabel them as passed.
- Real Ask interpretation and Analysis Evidence quality are separate from the
  offline failure tests. Missing keys preserve local paths but do not validate
  external integrations.

## Handoff decision

The tested source meets the engineering criteria for controlled evaluation.
Use the operator runbook for installation/recovery and the Beta protocol for
real-user evidence. Keep Public Beta recruitment closed until the release
owner reviews the exact distributed build and outstanding product gates. No
new feature expansion is needed to finish those checks.
