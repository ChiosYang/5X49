# Canonical Migration Gate A quality summary

- Evidence date: 2026-08-24
- Report schema: 1
- Gate implementation commit: `70f525a`
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
| Curated acceptance database and media-root rehearsal | Passed locally, non-gating | Normal product scan, scrape, organizer, personal-state, restore, and privacy paths |
| Naturally aged real-library rehearsal | Blocked | Private real-world input not supplied |
| Docker config/build/upgrade/read-source/restore/browser matrix | Blocked | Docker CLI unavailable |

Automated backend verification completed in under one minute with 127 passing
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

Person/Credit/Concept implementation remains later W3 work.
Assertion/Evidence/AnalysisRun persistence, deduplication, rejected-state
protection, and evaluation are W4/Gate B evidence, not Gate A implementation
checks.
