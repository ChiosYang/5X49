# Search content boundaries and model score contracts

Status: In Progress
Last updated: 2026-10-28
Related: semantic-search-integration.md

## Goal

Preserve literal lookup and strict SQL constraints while admitting bounded
content requests that use contrast, alternatives, reference qualifiers and soft
preferences. Keep unfamiliar native score scales from inheriting another
model's absolute admission thresholds.

## Behavior contract

- Local exact Film/Person bindings retain precedence and real punctuation.
  No arbitrary long sentence is truncated into a known title.
- Clause boundaries consume only complete hard conditions and a closed set of
  local-library/no-substitution controls. Every remaining requirement is kept
  as content or causes clarification. A no-relaxation instruction without an
  actual year/person/condition is incomplete, not permission to guess one.
- Soft preferences such as a non-mandatory ending or casting choice remain in
  semantic text. Guard normalization does not rewrite the model query. A new
  mandatory clause terminates that soft scope. Unsupported content exclusions,
  unknown roles/languages and ambiguous factual alternatives remain guarded.
- Protected content may use semantic `or`/contrast, but hard facet alternatives
  retain the existing v2 rules. Narrative dates do not become release facts.
- Complete language clauses around content use existing strict language SQL,
  separately from country. Unknown/conflicted language facts fail both positive
  and negative requirements. Ordinary literal/v1 behavior remains compatible.
- A parenthesized year immediately after a reference title qualifies that
  reference identity. It does not restrict release years of recommendations.
  The original reference ID is excluded before rerank and again on restore.
- A complete uncertainty declaration naming two exact local titles returns
  local choices for a reference request. It never auto-selects the only known
  alternative or accepts an injected third ID. Plain title uncertainty instead
  requests a more specific title/year, with no inferred recommendation.

## Score admission

- Existing native thresholds remain unchanged and are explicitly bound to the
  existing Nemotron rerank contract. They are legacy operating parameters, not
  probabilities or independent quality acceptance.
- Semantic display defaults to at most five admitted results (`max_results`,
  1..20); SQL filtering and reference/explicit exclusions precede this cap.
  A small list is a presentation bound, not a claim that every item is relevant.
- An unfamiliar/mismatched declared model, including Voyage, returns
  `search_rerank_uncalibrated` before provider dispatch. This is unavailable,
  not a no-match answer. The existing evaluation runtime still admits only its
  original fixed free model configuration; no paid endpoint is enabled here.
- `separated_head` is an OFFLINE proposal only. A unique adjacent gap accounting
  for more than half the score range defines a head, capped at five. Its result
  is invariant to positive affine score scaling. Flat/singleton/gradual/broad
  heads remain unresolved. It never establishes relevance or a no-answer and
  is not wired into production admission.
- Reliable Voyage relevance admission still needs independently labeled
  positive and negative development queries, followed by separate validation.
  This change does not invent such calibration or tune thresholds on seen runs.

## Restoration and visibility

The v4 policy fingerprint includes score model and result cap. Old snapshots
require explicit resubmission; GET/refresh/Back/filter edits never infer.
Reference alternatives/year survive a pending-choice snapshot. Results expose
optional `semantic.result_cap`, `rerank_model` and `admission_profile` metadata.
No credentials, paths, source observations or provider response bodies enter
URLs or error messages.

## Verification

- Current targeted parsing/integration/runtime/provider suite: 114 passed.
  Expanded targeted suite including media-path boundaries: 120 passed.
- Frontend: 148 unit tests passed; lint, typecheck and build passed. The existing
  cross-drive temporary-directory tests require a same-drive process-local temp
  path on Windows; their assertions and dependencies were unchanged.
- Pre-review full backend checkpoint: 808 tests passed, three skipped. The initial run exposed legacy
  language expectations now replaced by exact strict-language plan assertions,
  and temporary short-name aliases resolved by a canonical process-local temp path.
- Verification also found pre-existing fixture isolation gaps: edition/identity
  scan receipts used the default database, and lifecycle tests left backup/health
  workers unmocked. Fixtures now bind the shared database module to their own
  disposable engine, assert receipt persistence there, and mock both workers.
  The affected 51 tests passed. The guarded full checkpoint also passed 808
  tests, three skipped, with zero external-network or real-database connection
  attempts and an unchanged protected file hash. Current-head CI remains required.
- Module compilation passed. Scripts: 15 executed, two Docker Compose checks
  blocked by the absent Docker executable, one platform check skipped. CI must
  independently execute these environment-dependent checks.
- New synthetic tests cover mandatory-scope boundaries, punctuation, reference
  years and choices, unknown-language positive/negative SQL, actual empty SQL,
  unknown-person clarification, model/profile mismatch, bounded display,
  restoration, score ties and affine/no-answer invariants.
- Independent review regressions: mandatory conjunctions terminate soft scope
  and remaining hard intent is checked; a story cue cannot soften an unknown
  country/genre/source negation. Numeric title/year mentions are separated before
  reference classification, using real local SQL title projections in tests.
  Multiple uncertainty declarations clarify instead of overwriting choices.
- Actual diagnostic inputs/labels/results remain outside Git. Any cached
  replay is development regression, never fresh blind-quality acceptance.
- No model requests, intentional library updates or credential/config changes
  are part of the implementation. Lifecycle workers are isolated in tests; local
  verification protection is separate from search quality acceptance.

## Remaining risks

Natural-language coverage is deliberately bounded. Unconsumed requirements
still clarify. New or changed wire text without a saved exact response remains
unverified. Voyage admission is intentionally unavailable until calibration is
supported by suitable positive/negative data; the offline shortlist is not a
replacement for that evidence.
