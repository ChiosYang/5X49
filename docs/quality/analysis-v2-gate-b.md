# Analysis V2 Gate B quality summary

- Evidence date: 2026-08-26
- Database target: schema/data v10
- Dataset contract: `analysis-eval.v1`
- Dataset size: 36 public cases
- Dataset language split: 12 / 12 / 12
- Draft dataset hash prefix: `94eb0d52459a58a7`
- Policy: `gate-b-policy.v1`
- Human review contract: `analysis-eval-human-review.v1`
- Evidence policy: `evidence-http.v1`
- Tool status: **Passed**
- Live status: **Blocked**
- Human status: **Blocked**
- Gate B conclusion: **Blocked**

This Git-safe summary contains only contract versions, truncated hashes,
threshold comparisons, equality statements, durations, and pass/fail/blocked
results. It does not contain film titles, relationship text, URLs, raw model
input/output, provider errors, page bodies, paths, credentials, exact live cost,
or complete internal identifiers. Raw rehearsal files remain in the ignored
Gate B run directory.

| Check group | Result | Git-safe evidence |
| --- | --- | --- |
| Dataset shape and privacy | Passed | 36/36; fixed language and tag quota booleans |
| Draft/adjudicated boundary | Blocked as designed | 36/36 remain draft with zero annotators |
| Direction and qualifier matching | Passed | Canonical match/hash equality only |
| Deterministic scorer thresholds | Passed | Boundary pass/fail outcomes only |
| Runtime persistence and replay | Passed | New-row equality and cache outcome only |
| User rejected protection | Passed | Review-field equality; zero reactivation |
| Revoked Evidence protection | Passed | Link-state equality; zero reactivation |
| Unresolved reference review | Passed | Review existence and idempotence only |
| Verified backup and restore | Passed | W4 digest and migration-journal equality |
| Privacy canaries | Passed | Zero detected leaks across report and database |
| Live model evidence | Blocked | Key, exact model, pricing, and adjudication absent |
| Human helpfulness and novel predictions | Blocked | Live output and complete review absent |

Offline rehearsal `w4-s4-offline-20260826-07` completed in under 30 seconds.
It created a new isolated v10 database, exercised the production persistence
boundary with deterministic validated output, restored a verified post-run
backup, and returned exit code 3 with `tool_status=passed`,
`live_status=blocked`, `human_status=blocked`, and `overall_status=blocked`.
The application database hash was unchanged in the automated rehearsal test.

The focused Gate B suite passed 6 tests in 15.789 seconds. Complete backend
discovery excluding credential-dependent `test_agent.py` passed 198 tests in
143.480 seconds. `python -m compileall -q app` passed.

W3 rehearsal `w4-s4-gate-b-20260826-01` passed at schema v10 with the source
fingerprint prefix unchanged. Gate A rehearsal using the same run ID passed all
local upgrade, consistency, runtime, restore, and privacy phases; its strict
result remains Blocked because Docker evidence is absent. `git diff --check`
passed with only repository checkout line-ending warnings.

Gate B cannot pass until the user adjudicates all cases before viewing model
output, supplies an exact OpenRouter model and matching pricing manifest,
authorizes and completes the live run, and scores every successful case and
novel prediction. Gate A remains independently Blocked, so a future Gate B pass
alone will not authorize Graph UI.
