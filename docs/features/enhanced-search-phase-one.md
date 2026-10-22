# Enhanced Explore search — phase one

Status: Done
Last updated: 2026-10-22
Related: unified-explore-search.md; factual-explore.md

## Goal

Find local Films by reliable multilingual names and complete, bounded factual
requests through the existing Explore input and Film cards.

## Scope

- Active FilmTitle names and source-backed Person aliases, normalized with NFKC,
  whitespace folding and case folding; stable Film/Person identities and exact
  title priority. No translation, transliteration or guessed identity merging.
- Versioned plans for actor/director conjunctions, year/runtime ranges,
  country/genre alternatives, explicit exclusions and viewing state.
- Local EN/ZH rules, complete-plan validation, ambiguity choices and removable
  conditions. Existing URLs, Collection identity, global search and navigation stay
  compatible. Restoring or editing a plan never invokes a model.

## Non-goals

- Semantic retrieval, similar films, subjective mood/theme matching (phase two).
- Automatic bulk metadata fetching, new credentials, model downloads, paid calls,
  PR28 integration or relaxing its independent live-quality/budget hold.
- Ask workspace or a replacement manual filtering form.

## Existing behavior

FilmTitle already retains source-backed localized/alternative names, but search
indexes scalar title/original_title only. Person has a single name. Discovery v1
supports one value per facet and delegates strict Film membership to Explore.
SQLite read models and the existing provider boundary are sufficient; no new
service or dependency is needed.

## Acceptance criteria

- [ ] Reliable names return one row per Film/Person; exact title precedes broad
  matches, literal wildcards and slash titles remain literal.
- [ ] Every accepted hard condition is applied before count/sort/pagination;
  missing/conflicted facts fail active positive and negative conditions.
- [ ] EN/ZH local requests work without a key, ambiguous identities require a
  choice, unknown or unsupported requirements never execute a partial plan.
- [ ] Old URL/API behavior and mutation/history/Return/cancel races stay covered.
- [ ] Migration/rebuild/reset/backup behavior and bounded SQL costs are verified.
- [ ] Expected-ID offline evaluation, relevant/full suites, desktop/320px visual
  checks and independent review pass on the final head.

## Decisions

- Add source-backed Person aliases only when a credit carries a stable external
  identity. Existing TMDB credit name/original_name can be retained without extra
  requests. Existing single-Film refresh/scrape is the controlled replenishment
  channel; this change never starts it automatically.
- Extend Discovery with a versioned plan, retaining Ask v1 and restored v1 URLs.
- Use existing SQLite projections and strict eligible facts, never generated SQL.
- Advanced provider output is validated and grounded locally. Offline/mock
  evidence is separate from real-model quality acceptance; no live call is part
  of this task's authorized verification.

## Open questions

- Real provider quality, cost and any semantic-model resources require a separate
  explicit plan and authorization before trials. No such trial is run here.

## Slices

### Slice 1 — reliable names

Status: Implemented; full-suite verification pending

- Alias persistence/provenance, projection refresh and exact-first retrieval.
- Verify Unicode, supersession, homonyms, stable IDs and schema lifecycle.

### Slice 2 — complete factual requests

Status: Implemented; full-suite verification pending

- Bounded v2 contract, local parser, strict entity resolution and SQL executor.
- Verify hard-condition completeness, missing values, conflicts and privacy.

### Slice 3 — results and delivery

Status: In Progress

- Existing result cards, lightweight corrections and compatible restored state.
- Offline expected-ID evaluation; unit/backend/E2E/build and visual verification;
  draft PR, exact-head CI and independent review before normal merge.

## Verification evidence

- Baseline main: 3c9045b34cdc5ccac84984731c91e8290414be57 (PR44 merged and verified).
- Backend focused alias/projection/Ask regression: 25 passed. Extended contract,
  migration and source suite: 67 passed. Final core regression after Unicode
  privacy/range corrections: 45 passed.
- Existing v4/v6/v8 migration, Cinema DNA and Viewing upgrade regressions: 20
  passed with v11 migration expectations. Full-suite rerun is still pending.
- Frontend lint/typecheck passed; 138 unit tests passed. Production build passed
  through the isolated E2E runner.
- Related EN/ZH Explore, Collection and enhanced-search E2E: 79 passed, including
  14 new cases. Desktop/320px renderings inspected, including localized genre
  chips. Existing navigation, IME, saving races and last-page tests are retained.
- Offline synthetic 12-case expected-ID evaluation: recall@40 1.0, top-1 1.0,
  zero unexpected IDs; median 53.05ms, p95 95.99ms on the three-Film fixture.
  These timings do not establish large-library or real-model performance.
- SQL materialization remains 40/page; a 200-Film fixture checks <=12 SELECTs,
  count-before-page and last-page clamping.
- Pre-review full local baseline: 465 backend tests (3 Windows host skips), full
  E2E 270 passed. These precede the four P2 corrections and are not the final gate.
- Review fixes: intersect every year clause; protect supported clause boundaries;
  serialize pending condition/identity edits; retain aliases by response locale
  while retracting same-locale withdrawals and changed source identities.
- The same locale-scoped retention applies to localized/alternative Film titles;
  current canonical/original title selection keeps its existing behavior.
- The old component was reproduced in a real browser: rapid two-person choices
  lost clause 0, and rapid JP/FR removals revived JP. A task-only old-component
  test was removed and the fixed source restored with a byte-hash check.
- Fixed-component enhanced E2E: 16 passed, including two real ambiguities and
  delayed chip navigation. Parser/alias/schema/Library review regression: 40 passed;
  fresh full verification and exact-head independent re-review remain pending.
- Final reviewed head d12a5319dbf4f5fb142d4bb77b295c1eaa5cfa52 passed full
  local backend 468/3 Windows skips and E2E 272. CI39721297391 passed backend
  468/1 skip, tooling 15, frontend 138/audit/lint/type/build and E2E 272.
  Independent native review /root/review_enhanced_search_phase_one cleared all
  P1/P2. Merged normally at fb745f2cb3173d062aca170b3450ceb474d8a1f1; remote
  inclusion and tree equality verified. No real model calls.

## Remaining risks

- Canonical alias migration and projection refresh must remain consistent.
- A grammar must preserve full person/title literals and reject unsupported or
  unconsumed clauses rather than broadening a request.
- Production v2 is the explicit local EN/ZH grammar, not unrestricted natural
  language understanding. Expanded provider transport is offline/mock only;
  v1's guarded fallback remains unchanged. Real quality/budget gates are intact.
