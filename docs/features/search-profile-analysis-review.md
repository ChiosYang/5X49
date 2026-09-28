# Search, personal records and Analysis review

Status: Done
Last updated: 2026-09-28
Related: Product roadmap — Analysis V2 quality and personal viewing loop

## Goal

Connect Library keyword search and personal rating/notes entry, then provide
reviewable Analysis decisions and corrections with verified quality boundaries.

## Scope

- Bilingual, locale-aware keyword search using the existing Library query.
- Film-level personal ratings and notes, including clearing values and refreshing Diary/DNA.
- User acceptance/rejection and bounded correction of Analysis relationships.
- Deterministic regression checks, Gate B preflight/rehearsal and honest live/human status.

## Non-goals

- Ask, global Graph, media mutation, or unrestricted model-driven editing.
- Releasing inferred Graph edges before the independent Gate B passes.

## Acceptance criteria

- [x] Search is reachable, query-driven, and handles empty/no-result/error states.
- [x] Ratings/notes can be saved and cleared without changing watched/favorite state.
- [x] Analysis decisions and corrections validate identity/type/direction and survive replay.
- [x] Review writes are transactional, bounded, and observable without private content.
- [x] Frontend unit/lint/typecheck/build and relevant backend regressions pass.
- [x] Quality reports distinguish deterministic, live-provider and human evidence.

## Decisions

- Work sequentially in the existing checkout on `ai/search-profile-review`.
- Reuse existing profile state, projections, controls, and local event patterns.
- Keep Graph visibility factual until Gate B is independently concluded Passed.
- User confirmed that this delivery completes code and offline validation only;
  live model execution and human quality review remain a separate blocked gate.
- Corrections reject the old relation and accept an existing-entity replacement
  in one transaction. They do not transfer rationale or Evidence.
- Revisions and SQLite write serialization protect against stale decisions.
- Reference resolution never verifies Evidence; reopening a queue item does not
  undo a previously curated relationship. Review that relationship separately.
- Search matches normalized titles, genres, countries and directors; SQL wildcard
  characters are treated literally. Provider/Ask search is outside this slice.

## Slices

1. Search and personal record entry — Complete.
2. Analysis review/correction API and UI — Complete.
3. Regression, browser verification and offline quality evidence — Complete.

## Verification evidence

- Baseline preceding this task: frontend unit 39 passed; focused Graph, export,
  Diary and Cinema DNA backend suite 30 passed.
- `npm run lint` — passed.
- `npm run typecheck -- --incremental false` — passed. The default incremental
  command could not overwrite the existing `tsconfig.tsbuildinfo` under sandbox permissions.
- `npm run test:unit` — 42 passed.
- `npm run build` — passed on final frontend code. Required elevated execution
  to write the pre-existing `.next` cache after the sandbox attempt failed.
- With `UV_CACHE_DIR` set to a writable temporary directory:
  `uv run --no-sync python -X utf8 -m unittest test_analysis_review test_analysis_runtime test_analysis_critic test_analysis_evidence test_gate_b_evaluation test_graph_query test_projections test_api_routes test_diary test_cinema_dna -q`
  — 89 passed. Includes 12 new review/profile regressions. Gate B tests required
  elevated execution for their dedicated isolated run directories; the earlier
  sandbox run had only two directory-permission errors.
- `uv run --no-sync python -X utf8 -m unittest test_database_restore test_portability -q`
  — 6 passed.
- `python -X utf8 <skill-creator>/scripts/quick_validate.py skills/5x49-backend`
  — valid. This is the repository-shipped API guide; no local skill deployment
  or MCP configuration was changed.
- `git diff --check` — passed.
- `uv run --no-sync python -X utf8 -m app.evaluation.gate_b rehearse --dataset fixtures/analysis_v2/gate-b-v1.json --run-dir data/analysis-v2/gate-b/runs/search-profile-review-final-20260928`
  — tool status passed; live, human and overall status blocked (expected nonzero
  result). The first sandbox attempt for the earlier run could not create its
  dedicated directory; the isolated rehearsals completed with elevated execution.
- Browser verification used disposable, synthetic data and provider fixtures on
  backend port 18549 and frontend port 15549. Verified Chinese and English search,
  initial/no-result/clear states, personal rating/note save and clear, relation
  acceptance/correction, dismiss/reopen, persistence after navigation, and
  keyboard operation. Checked 390px and 1280px layouts; no horizontal overflow
  was observed. Existing route error boundaries remain responsible for fetch failures.
- Screenshots: `C:/Users/Administrator/Documents/AgentLogs/5x49-review-mobile.png`
  and `C:/Users/Administrator/Documents/AgentLogs/5x49-review-desktop.png`.
  Temporary browser tab and both preview servers were closed after verification.

## Remaining risks

- Gate B still lacks strict live Evidence and complete human review. The
  application-configured OpenRouter key was absent; production Evidence
  preflight returned `evidence_network_boundary_blocked` on this host.
- No live model calls, provider spending or production deployment were performed.
  Application database and media were not modified.
- Target lookup uses existing active entities only and returns at most 30
  matches; users must refine the query for larger result sets.
