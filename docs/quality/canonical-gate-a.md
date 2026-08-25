# Canonical Migration Gate A quality summary

- Evidence date: 2026-08-25
- Report schema: 1
- Gate implementation commit: `70f525a`
- Current migration target: schema/data v10
- Development-copy source fingerprint: `b7a2da987e309d52`
- Curated-acceptance source fingerprint: `978d1a20ee62b4ac`
- Gate conclusion: **Blocked**
- Gate A passed: **No**

This file is the Git-safe summary. Raw reports, databases, manifests, caches,
logs, exact counts, media paths, titles, and full identifiers remain under the
Git-ignored `backend/data/gate-a/` review area.

| Check group | Result | Evidence scope |
| --- | --- | --- |
| CLI contract and refusal paths | Passed | Synthetic fixture tests |
| Supported legacy upgrades and repeat execution | Passed | Versioned fixtures; counts compared for equality only |
| Backup, mutation, byte restore, and remigration | Passed | Isolated fixture copies |
| Runtime reconcile, clear/restore, relink, and hashing | Passed | Generated normal-profile plus isolated mini-library |
| Canonical/Legacy consistency and privacy canaries | Passed | Fixtures and generated mini-library |
| Development database copy rehearsal | Passed locally, blocked as evidence | Byte-identical clone; non-gating only |
| Curated acceptance database and media-root rehearsal | Passed locally through v10, non-gating | Normal product scan, scrape, structured metadata, factual Genre Assertions, personal-state, restore, privacy, and predicate-registry preservation paths |
| Naturally aged real-library rehearsal | Blocked | Private real-world input not supplied |
| Docker config/build/upgrade/read-source/restore/browser matrix | Blocked | Docker CLI unavailable |

Automated backend verification completed in under one minute with 135 passing
tests and reported only synthetic test totals. Compose files parsed, the Docker
script passed PowerShell syntax validation, and frontend lint, type checking,
and production build completed successfully. No real-library record count is
stored here.

The local report can become `passed` only for an offline input that is not the
live application database or its byte-identical development clone, includes a
real media root, and passes every phase. The overall conclusion can become
`passed` only when the Docker report also contains every required phase and
isolation check. Missing evidence is never downgraded to a warning.

The development-copy rehearsal reached schema v5, repeated with no additional
migration or backup, produced zero Library/user-state Shadow differences after
the compatibility projection calibration, restored the source backup exactly,
and left the source hash/size/sidecars unchanged. Runtime reconcile remained
blocked because that non-gating copy had no media input; its byte-identical
development fingerprint also prevents promotion to real-library evidence.

The generated runtime evidence includes platform-ID rename relink, missing and
restore, two LibraryItems sharing one Film, the 12 MiB foreground sampling
budget, deduped collision work, and complete-hash disambiguation.

The final curated acceptance run `acceptance-final-20260824-1810` passed every
local phase with no failed check and left its fixed input fingerprint unchanged.
An earlier run correctly rejected a media-root layout containing root videos and
a merged edition folder; after the generated media was returned to one
top-level movie folder per LibraryItem and reconciled through the application,
ordinary clear/restore passed. The same failure also exposed raw internal Job
paths at the HTTP/SSE projection boundary; public Job payload, result, progress,
error, and dedupe fields are now sanitized while stored worker data remains
available for execution and retry. This evidence remains curated and does not
replace a naturally aged private library copy.

The W3 regression run `w3-20260825-02` upgraded the same fixed offline input to
v7 without modifying it and passed every structured-metadata upgrade, backfill,
consistency, runtime, lifecycle, and privacy check. Backfill, second NFO
reconcile, and recorded TMDB refresh were count-idempotent; source precedence
and provenance preservation passed. This evidence is tracked in
`docs/quality/structured-metadata-w3.md` and does not change the input's
curated/non-gating Gate A classification.

The independent Gate A regression `structured-metadata-v7-20260825` also
reached v7 with every local phase passed, restored its verified backup, kept
Canonical/Legacy shadow differences at zero, and left the source unchanged.
Its overall result remains `Blocked` because Docker evidence is still absent.

The post-Schema-v8 Gate A regression `w4-v8-20260825-02` upgraded only its
isolated work copy to v8 and passed every local phase. Deep clear removed all W4
domain rows while retaining exactly the nine versioned predicate reference
rows and the migration journal. Restore/remigration, Shadow equality, runtime
reconcile, relink, privacy canaries, and source immutability remained green.
The overall result is still `Blocked` because Docker evidence is absent and the
curated input does not replace a naturally aged private library.

The post-v9 Gate A regression `w4-s2-v9-20260825-01` applied the factual Genre
Assertion backfill only to its isolated work copy. Every local phase passed;
migration rerun, restore/remigration, runtime reconcile, Shadow equality,
deep-clear predicate preservation, privacy canaries, and source immutability
remained green. The strict result remains `Blocked` because Docker evidence is
absent and the curated input is not a naturally aged private library.

The post-v9 backend regression discovered every test module except
credential-dependent `test_agent.py`; all 176 tests passed after factual Genre
Assertion synchronization was added. This is regression
evidence only and does not replace either missing strict Gate input class.

The post-v10 Gate A regression `w4-s3-v10-20260825-01` upgraded only its
isolated work copy and passed every local phase. Migration idempotence,
restore/remigration, reconcile, clear/restore, Shadow equality, deep-clear
predicate preservation, privacy, and input immutability stayed green. Its
strict overall status remains `Blocked` because Docker evidence is absent.

The post-v10 backend regression discovered every test module except
credential-dependent `test_agent.py`; all 190 tests passed after Analysis V2
runtime persistence and the bounded Legacy transition were added. This remains
regression evidence rather than missing strict Gate input or Docker evidence.

Person/Credit/Concept schema, deterministic backfill, and runtime synchronization
are complete in W3 through version 7. Assertion/Evidence/AnalysisRun schema and
contracts are present in version 8, and factual Genre Assertions in version 9.
Analysis runtime persistence, resolution, Evidence, and Legacy transition are
complete through W4 Slice 3. Evaluation remains W4 Slice 4/Gate B evidence and
is not a Gate A implementation check.
