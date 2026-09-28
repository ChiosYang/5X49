# Ask MVP

Status: Done
Last updated: 2026-09-28
Related: Product roadmap W10; Product Spec JTBD-6

## Goal

Turn a film-finding question into reviewable constraints, run a strict local
query, and explain each result using the facts that actually matched.

## Scope

- Chinese/English Ask page with natural-language interpretation and a no-key form.
- One Genre, Person (any/director/actor), Country and release Decade per query,
  plus watched/unwatched state and title/year sorting. Dimensions combine with AND.
- Preview before querying; explicit selection for ambiguous/fuzzy Person names.
- Reuse factual Explore projections and query results; role constraints must be
  enforced before counting and pagination.
- One bounded provider call for interpretation; local resolution, querying,
  pagination and result explanations require no model calls.

## Non-goals

- Ask chat history, recommendations based on taste, arbitrary SQL/tools, writes,
  inferred Graph edges, free-form date/runtime/rating filters or boolean expressions.
- Live model quality claims; the user previously selected code and offline acceptance.

## Decisions

- User confirms interpreted conditions before search. Unsupported or unresolved
  conditions cannot silently disappear or fall back to a broader query.
- Provider input contains the typed question and a static schema only, never
  library records, paths, notes, settings or secrets. Obvious pasted credentials
  and absolute paths are rejected before any provider call.
- Questions and provider responses are not persisted or logged. Provider errors
  are bounded public codes. Interpretation has a timeout, output limit and no retries.
- A structured form stays usable without a provider key or after provider failure.
- Ask result cards are read-only and keep their matched-fact explanations visible.
- Work in the existing checkout on `ai/ask-mvp`; no additional worktree.

## Acceptance criteria

- [x] Natural-language integration validates a bounded plan with a review step
  (provider fixtures; live interpretation quality remains outside this acceptance).
- [x] No-key and failure states retain a complete local form path.
- [x] Unknown/ambiguous entities require correction or explicit choice.
- [x] Role, factual eligibility, view, sorting and pagination are strict.
- [x] Result explanations are traceable to returned local facts.
- [x] Read-only/privacy and provider-failure regression tests pass.
- [x] Frontend unit/lint/typecheck/build and bilingual responsive browser checks pass.
- [x] API and external-agent documentation reflect the implemented contract.

## Slices

1. Typed plan, provider boundary and local resolution — Complete.
2. Strict query and explanation behavior — Complete.
3. Bilingual Ask UI and no-key form — Complete.
4. Offline verification and documentation — Complete.

## Verification evidence

- Backend, from `backend/`:
  `uv run --no-sync python -X utf8 -m unittest test_ask -q` — 14 passed.
  Final regression command:
  `uv run --no-sync python -X utf8 -m unittest test_ask test_explore_query test_factual_explore_evaluation test_projections test_api_routes -q`
  — 54 passed. `UV_CACHE_DIR` used a disposable cache under the system temp folder.
- Backend coverage includes strict AND/role/view constraints before counts and
  pagination, sorting, unknown/ambiguous/stale selections, zero results without
  relaxation, incomplete/invalid provider output, timeout/busy/failure handling,
  confirmation validation, projection failure, local queries without a model,
  bounded provider requests, privacy rejection and unchanged database file hashes.
- Frontend, from `frontend/`: `npm run lint`,
  `npm run typecheck -- --incremental false`, `npm run test:unit` (44 passed),
  and `npm run build` — all passed. Production output includes `/[locale]/ask`.
- Browser acceptance used a disposable SQLite database and synthetic films,
  with both no-key mode and a deterministic interpreter fixture. No live model
  calls or real library writes were made. Verified Chinese/English preview before
  explicit confirmation, country/decade/unwatched filtering, director versus actor,
  explicit person selection, zero results, unsupported input, and timeout followed
  by usable local form controls.
- Browser checks at 390 x 844 and 1280 x 900 found no horizontal overflow.
  Result explanations remain visible and result cards expose no profile mutation
  buttons. Preview processes and browser tab were closed after verification.
- Local browser evidence:
  `C:/Users/Administrator/Documents/AgentLogs/5x49-ask-mobile.png` and
  `C:/Users/Administrator/Documents/AgentLogs/5x49-ask-desktop.png`.
- `git -c core.safecrlf=false diff --check` — passed.
- `python -X utf8 C:\Users\Administrator\.codex\skills\.system\skill-creator\scripts\quick_validate.py D:\Projects\5X49\skills\5x49-backend`
  — Skill is valid. The API reference and repository-shipped agent Skill describe
  all four Ask endpoints, confirmation and error behavior.
- Final code review covered provider validation/privacy, person identity and role
  filtering, read-only cards, error handling and the existing Explore contract.

## Remaining risks

- Actual provider interpretation quality and representative real-library usefulness
  require separate live/user evidence. Natural-language correctness cannot be
  inferred from fixture acceptance; the explicit condition preview is required.
- Gate B remains independent and blocked by the previously recorded missing
  usable OpenRouter key and failed evidence-network preflight. The user chose
  code and offline acceptance first; this task did not rerun live acceptance.
- This document records implementation and offline acceptance. Deployment and
  live-model acceptance are separate from the Git integration workflow.
