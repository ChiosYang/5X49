# Analysis V2 Persistence Slice 3 quality summary

- Evidence date: 2026-08-25
- Current migration target: schema/data v10
- Analysis schema: `analysis-output.v2`
- Prompt version: `genealogy-v2.v1`
- Resolver policy: `analysis-resolver.v1`
- Persistence policy: `analysis-persistence.v1`
- Evidence policy: `evidence-http.v1`
- Source fingerprint prefix: `978d1a20ee62b4ac`
- Slice 3 conclusion: **Complete**
- Gate B conclusion: **Pending**

This Git-safe summary stores only check results, equality statements,
versioned contract names, durations, and a truncated source fingerprint. Raw
model input/output, provider failures, page bodies, movie titles, media paths,
credentials, exact domain counts, and full identifiers are not stored here.

| Check group | Result | Stored evidence |
| --- | --- | --- |
| Directional Analysis V2 contract | Passed | Default, reverse, type, and duplicate booleans only |
| Canonical input boundary | Passed | Field allowlist and deterministic hash equality only |
| AnalysisRun lifecycle and idempotence | Passed | Status, attempt, cache, and version equality only |
| Entity resolution and non-owned TMDB Film | Passed | Resolution/review outcomes only |
| Proposed Assertion persistence | Passed | Key, provenance, and lifecycle equality only |
| User accepted/rejected protection | Passed | Review-field preservation equality only |
| Evidence network and content policy | Passed | Policy outcomes and content-hash equality only |
| Completion and failure transactions | Passed | Pre/post state equality and safe error codes only |
| Legacy compatibility projection | Passed | Shape, direction, and excluded-field booleans only |
| v9 to v10 deterministic transition | Passed | Version, idempotence, and preservation equality only |
| W3 regression | Passed | All isolated checks passed; input unchanged |
| Gate A regression | Passed locally | Local phases passed; Docker remains blocked |

The focused Slice 3, migration, Canonical, W3, TMDB, and Gate suite passed 104
tests in 77.723 seconds. Complete backend discovery excluding the
credential-dependent `test_agent.py` passed 190 tests in 123.781 seconds.
Python bytecode compilation and `git diff --check` passed.

W3 rehearsal `w4-s3-v10-20260825-01` completed in an isolated work copy and
passed at v10. Gate A rehearsal with the same run ID passed every local phase
and left the truncated input fingerprint unchanged. Its strict overall status
remains `Blocked` because Docker evidence is absent.

Automated Evidence tests use fake DNS and HTTP transports, so no external site
is a test dependency and no model-provided URL is contacted during acceptance.
The fixed adjudicated evaluation set, quality thresholds, restore evidence,
and strict Gate B matrix remain Slice 4.
