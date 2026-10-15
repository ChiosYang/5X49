# AI Film Finder phase one

Status: Blocked
Last updated: 2026-10-15
Related: Ask MVP; Factual Explore
Engineering implementation and offline acceptance are complete. Evaluation
compatibility, audited reconciliation and a targeted review-hold release
entrypoint are implemented. The single conservative-continuation addition awaits independent review. Parent
review, authorization and a fresh passing canary remain required for live
acceptance.

## Goal

Interpret a Chinese/English question on Explore, let the user edit and confirm
the entire plan, then show owned Films with verifiable local match reasons.

## Scope

- Reuse Ask and factual Explore, preserving genre/person role/country/decade,
  watched state and title/year sorting.
- Add exact effective duration and Film personal overall stars (1–5), with
  unknowns excluded only when the corresponding condition is active.
- Provider disclosure/consent, bounded validation, timeout, manual fallback,
  cancellation and stale-response protection; no inferred Analysis V2 edges.
- 58 bilingual acceptance cases and offline fixture evaluation. A separate
  live evaluation entrypoint must require explicit authorization and budget.

## Decisions

- Duration uses positive primary-edition video seconds, then positive Film
  runtime minutes. Inclusive/exclusive minute bounds compare exact seconds.
- Rating is FilmProfileState.rating; external or per-Viewing scores never fill it.
- A model receives only the question and static schema. No library/path/note
  context is attached. Unsupported/ambiguous requests must not become queries.
- Zero results offer condition removal, followed by another review/confirmation.
- Single configured model, one provider request, no retries or model routing.
- Evaluation-only provider/model remains deepseek/deepseek-v4.1-flash on
  OpenRouter decart/fp4, with the exact official canonical slug pinned.
  Cumulative limits, request reservations and reconciliation apply across
  retries; accounting recovery never grants permission for further inference.

## Acceptance criteria

- [x] Review/edit/confirm/cancel/return and zero-result relaxation are explicit.
- [x] Exact numeric bounds, null semantics and facts match confirmed conditions.
- [x] Unsupported/negated/similar/taste requests never silently broaden results.
- [x] Privacy, malicious output and interface failure cases fail closed.
- [x] Complete backend/frontend checks and real-backend responsive UI E2E pass.
- [x] Draft PR [#28](https://github.com/ChiosYang/5X49/pull/28) is delivered for independent parent review; follow-up fixes remain draft.
- [ ] Live supported parsing accuracy >=95% (independent review/authorization and a fresh passing canary are still required).

## Slices

1. Acceptance corpus and backend contract/query — complete.
2. Explore integration and interaction safety — complete.
3. Evaluation guards and offline verification — complete; draft PR delivered; independent-review follow-up and complete offline replay verified.
4. Live synthetic evaluation — blocked pending independent review and a fresh
   passing canary. Strict JSON and the full bilingual live gates remain unaccepted.

## Verification evidence

- Resumed 2026-10-15: 58/58 offline corpus; 12 budget/evaluation tests; full 438-test backend run (3 skipped); 95 frontend unit tests; lint/typecheck/build; all 95 real-backend UI E2E pass, including 21 Ask flows.
- Details and exact commands: [quality evidence](../quality/ask-phase-one.md).
- Compatibility review: [technical status](../quality/ask-phase-one-cloud-20261015.md).
- Evaluation/reconciliation/review-release/diagnostics: 71 focused Ask tests passed, covering
  SDK parsing, exact identity verification, audited/idempotent accounting
  recovery, precise review/CI binding, preservation of other unknowns and
  sanitized transport errors that survive settlement failures, and a singleton
  conservative continuation that retains unknown cost/full exposure and cannot
  exempt subsequent failures.
- Self-review fixed atomic query snapshots, person-choice/editor race, stale responses and the zero-unsupported-failure evaluation gate. No live model quality is claimed.

## Remaining risks

- Full live quality/usefulness, strict JSON and usage-cost corroboration remain
  unverified. The fixed alias resolves to a dated canonical slug; identity
  verification and audited reconciliation are implemented, but independent
  parent review/authorization must precede another model request. The original
  canary's completion receipt and strict JSON result remain unvalidated.


## Independent review corrections

- Recognize explicit English quantity syntax (articles, full cardinal vocabulary and compounds, common fractions, decimal and abbreviated units) while retaining real OR/ambiguity guards. A 19-quantity/four-comparison backend matrix covers 76 unchanged provider payloads; six added fixture expressions have real-backend UI coverage.
- Bind each interpretation and retry to current consent and the actual provider target.
- Scope Explore recovery to the source normalized fact query and history entry.
- Preserve existing local changes and saved test evidence through execution-environment outages.

- Initial source recovery gates composer readiness; first history-scope discovery never clears initial interaction state. Nonempty questions retain consent controls. Deterministic blocked-hydration E2E covers the Linux-discovered first-input race.
