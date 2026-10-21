# Explore unified search

Status: In Progress
Last updated: 2026-10-21
Related: PR41 Collection hierarchy; PR28 remains independently held

## Goal

Explore starts with one ordinary search input followed by local Collection shelves.
Keywords, people and collections use existing local discovery. Complete supported
requests run factual filters directly, with removable explanations. No Ask workspace,
manual fallback form, mode selection or routine confirmation precedes results.

## Decisions

- Reuse main's Ask v1 facts, identities, roles and strict Explore query service.
  PR28 `ceb202b8578c7ac1d98d8a35ac0f29a41fba457a` is read-only reference material:
  preserve its draft, conflicts, 52-case live-quality gate and budget/review holds.
  Its advanced duration/rating model contract, evaluation/accounting modules and
  old standalone/manual UI are not imported or enabled. Strict duplicate-key JSON
  validation and conservative intent guards are adapted and independently retested.
- Local rules must consume the complete request. Unsupported similarity, mood,
  themes, negation, multiple values and advanced filters never become partial results.
  AI is submission-only, at most once, without retries, with schema/confidence,
  literal grounding and local vocabulary/entity validation. Models receive only the
  submitted text and a static schema; no library, paths or personal viewing data.
- Store original input and validated conditions in bounded local URLs. Refresh,
  Back, filtering, pagination and mutation refresh only query local data. Preserve
  legacy Explore queries, stable collections, global Library search and Return.
- Jev is deferred: official Choice is a finite routing primitive, with separate
  credentials/calibration. No new supplier dependency or live call is introduced.
  [Choice](https://docs.typesafe.ai/primitives/choice),
  [limits](https://docs.typesafe.ai/model-jaggedness/jev-1.13).
  Offline/mock results cannot establish Chinese accuracy or latency.
- Existing authorized isolated worktree is reused. Auto-review rejected switching
  the primary checkout; that action did not execute. User untracked files remain.

## Acceptance criteria

- [ ] One input on the Collection homepage; local typing suggestions, no AI on typing.
- [ ] Submit routes simple keywords locally; complete rules execute without a model.
- [ ] Ambiguity alone prompts a choice; unsupported/error/no-key keeps input and honest keyword fallback.
- [ ] Ask menu/workspace/manual form removed; old Ask routes redirect to Explore.
- [ ] Cancel, newer submission/navigation, IME, direct/reload/Back and mutation races are covered.
- [ ] Existing Collection/precise filters/global search and 41-to-40/Return regressions pass.
- [ ] English/Chinese, keyboard and 320px visuals checked; full required tests pass.
- [ ] Draft PR, matching CI and independent review complete before normal merge.

## Slices

1. Conservative local router, shared validated interpreter and restored local query contract.
2. Shared input, unified result URL, local suggestions, explain/correct chips and Ask redirects.
3. Offline/mocked backend and browser acceptance; full suites, visuals, PR/CI/review.

## Verification evidence

- Backend focused discovery/Ask/Explore/API group: 71 passed, real providers disabled.
- Frontend unit: 130 passed with canonical Windows TEMP/TMP; lint and typecheck passed.
- First complete unified browser group: 18 passed in a production build with real
  routes/SQLite and mocked provider transport. Includes both locales, 1440/320px,
  IME, ordinary suggestions, direct local rules, corrected chips, pointer Return,
  unsupported/no-key/timeout, one inference per submit and no inference on restore,
  cancel/old-response/newer-RSC races, and 41-to-40 replacement preserving draft/history.
- Pointer Return exposed existing title z40 covering the z-sticky control after a
  list scroll. The control now uses the existing navigation layer; no hero restyle.
- Extended unified/Collection/precise-filter browser suite: 77 passed, including
  bilingual same-name choice, delayed save during newer viewing navigation and
  detail-write Back cache revalidation. Original PR40/41 regression cases all pass.
- English/Chinese home, results, unsupported and ambiguity captures inspected
  internally at 1440/320px. Existing controls/tokens/grid are retained. Mobile input
  uses the ordinary TextInput spacing and a concise placeholder; the two secondary
  homepage entries share the existing small button size. Screenshots stay local.
- Full suites are pending.
  No real AI call or evaluation-ledger operation has run.

## Remaining risks

Live interpretation quality is unverified; PR28's independent acceptance remains held.
