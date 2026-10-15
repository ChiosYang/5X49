# AI Film Finder phase one

Status: Blocked
Last updated: 2026-10-15
Related: Ask MVP; Factual Explore
Engineering implementation and offline acceptance are complete. Live model acceptance is blocked only by the missing exported evaluation credential.

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
- No live requests, credential changes, metadata/media writes or scraping in
  this task. Evaluation-only provider/model is deepseek/deepseek-v4.1-flash on OpenRouter decart/fp4; cumulative task budget is US$1, already authorized. No global model or credential configuration was changed.

## Acceptance criteria

- [x] Review/edit/confirm/cancel/return and zero-result relaxation are explicit.
- [x] Exact numeric bounds, null semantics and facts match confirmed conditions.
- [x] Unsupported/negated/similar/taste requests never silently broaden results.
- [x] Privacy, malicious output and interface failure cases fail closed.
- [x] Complete backend/frontend checks and real-backend responsive UI E2E pass.
- [x] Draft PR [#28](https://github.com/ChiosYang/5X49/pull/28) is delivered for independent parent review; follow-up fixes remain draft.
- [ ] Live supported parsing accuracy >=95% (blocked by missing exported credential; cumulative US$1 authorization already received).

## Slices

1. Acceptance corpus and backend contract/query — complete.
2. Explore integration and interaction safety — complete.
3. Evaluation guards and offline verification — complete; draft PR delivered; independent-review follow-up and complete offline replay verified.
4. Live synthetic evaluation — blocked: exported OPENROUTER_API_KEY missing; 0 requests, US$0 spent.

## Verification evidence

- Resumed 2026-10-15: 58/58 offline corpus; 12 budget/evaluation tests; full 438-test backend run (3 skipped); 95 frontend unit tests; lint/typecheck/build; all 95 real-backend UI E2E pass, including 21 Ask flows.
- Details and exact commands: [quality evidence](../quality/ask-phase-one.md).
- Self-review fixed atomic query snapshots, person-choice/editor race, stale responses and the zero-unsupported-failure evaluation gate. No live model quality is claimed.

## Remaining risks

- Real provider/model quality, usefulness and cost await an existing safely configured credential. No real inference has run or been billed.


## Independent review corrections

- Recognize explicit English quantity syntax (articles, full cardinal vocabulary and compounds, common fractions, decimal and abbreviated units) while retaining real OR/ambiguity guards. A 19-quantity/four-comparison backend matrix covers 76 unchanged provider payloads; six added fixture expressions have real-backend UI coverage.
- Bind each interpretation and retry to current consent and the actual provider target.
- Scope Explore recovery to the source normalized fact query and history entry.
- Preserve all existing local changes and saved test evidence through the Windows
  execution-environment outage; resumed work never reads or transfers credentials.

- Initial source recovery gates composer readiness; first history-scope discovery never clears initial interaction state. Nonempty questions retain consent controls. Deterministic blocked-hydration E2E covers the Linux-discovered first-input race.
