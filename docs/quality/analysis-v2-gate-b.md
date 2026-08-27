# Analysis V2 Gate B quality summary

- Evidence date: 2026-08-27
- Database target: `fresh-canonical-v1` / version 3
- Dataset contract: `analysis-eval.v1`
- Dataset size: 36 public cases
- Dataset language split: 12 / 12 / 12
- Frozen dataset hash prefix: `fbfc9a1a481aef30`
- Policy: `gate-b-policy.v2`
- Human review contract: `analysis-eval-human-review.v1`
- Evidence policy: `evidence-http.v1`
- Dataset adjudication: **Passed**
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

Fresh Canonical offline rehearsal `fresh-canonical-v1-20260826-01` created an
isolated epoch-v1 database and returned `tool_status=passed`,
`live_status=blocked`, `human_status=blocked`, and `overall_status=blocked` with
the frozen dataset hash prefix unchanged at `fbfc9a1a481aef30`.

| Check group | Result | Git-safe evidence |
| --- | --- | --- |
| Dataset shape and privacy | Passed | 36/36; fixed language and tag quota booleans |
| Predicate relationship coverage | Passed | Actual accepted/required edge quotas satisfied independently of tags |
| Draft/adjudicated boundary | Passed | 36/36 adjudicated before live output; one anonymous annotator |
| Concept alias matching | Passed | Bounded aliases resolve to one gold target and one seeded Concept |
| Direction and qualifier matching | Passed | Canonical match/hash equality only |
| Identity metadata consistency | Passed in pilot | Zero resolved contradictions; conflict review equality only |
| Assertion and qualifier bounds | Passed in pilot | p95 at the fixed cap; zero qualifier-policy violations |
| Deterministic scorer thresholds | Passed | Boundary pass/fail outcomes only |
| Runtime persistence and replay | Passed | New-row equality and cache outcome only |
| User rejected protection | Passed | Review-field equality; zero reactivation |
| Revoked Evidence protection | Passed | Link-state equality; zero reactivation |
| Unresolved reference review | Passed | Review existence and idempotence only |
| Verified backup and restore | Passed | W4 digest and migration-journal equality |
| Privacy canaries | Passed | Zero detected leaks across report and database |
| Live model evidence | Blocked | Bounded pilot exists; strict Evidence preflight and full run absent |
| Human helpfulness and novel predictions | Blocked | Live output and complete review absent |

Offline rehearsal `w4-s4-adjudicated-20260826-03` completed in under 30 seconds.
It created a new isolated Fresh Canonical database, exercised the production persistence
boundary with deterministic validated output, restored a verified post-run
backup, and returned exit code 3 with `tool_status=passed`,
`live_status=blocked`, `human_status=blocked`, and `overall_status=blocked`.
The application database hash was unchanged in the automated rehearsal test.

The focused corrective Gate B, Analysis runtime and Evidence suite passed its
recorded checks. Policy-v2 offline rehearsal
`w4-s4-policy-v2-rehearsal-20260826-01` returned `tool_status=passed` and the
required strict Blocked statuses.

After the durable Workflow and deterministic Critic cutover, offline rehearsal
`architecture-phase5-20260827-01` again returned `tool_status=passed` with
live/human/overall strictly blocked and the same frozen dataset hash prefix.
Production and evaluator now share `genealogy-v2.v3`, `analysis-resolver.v3`,
`analysis-policy-critic.v1` and the same Analysis Workflow entrypoint.

The ignored diagnostic run `w4-s4-pilot-v2-20260826-02` used the pinned free
model with low reasoning and a bounded output budget. It completed 6/6 cases.
Aggregate checks recorded resolution accuracy and required recall above policy
thresholds, zero resolved identity contradictions, complete identity-conflict
and unresolved-reference review capture, zero qualifier-policy and semantic
duplicate violations, an Assertion p95 at the contract cap, equal restore
digest, and zero privacy leaks. Display-edge precision, helpfulness, and novel
predictions remain unaccepted until human review. This pilot is intentionally
marked diagnostic and cannot be concluded as strict live evidence.

The Fresh Canonical cutover reruns the complete backend suite and Gate B offline
rehearsal; current evidence is recorded in the fresh-baseline Feature Document.

Gate B cannot pass until strict public Evidence retrieval passes preflight, the
full 36-case live run is completed, and every successful case and novel
prediction is scored afterward. The configured model and matching pricing
manifest are no longer blockers. A future Gate B pass is necessary but not
sufficient for Graph UI; the UI still requires its own product, accessibility
and performance acceptance.
