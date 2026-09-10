# Cinema DNA V1

Status: Done
Last updated: 2026-09-10
Related: Product Roadmap — W9 Cinema DNA V1

## Goal

Explain a local profile's viewing exposure and explicit rating preferences in
Diary, with contributing Films and Viewings available for inspection.

## Scope and decisions

- Contract `cinema-dna.v1`; all-time active Films with confirmed, undeleted
  Viewings, including Films outside the visible Library.
- Genre, Person, Country and release-year Decade reuse Explore factual selection.
- Exposure is distinct category Films / all distinct watched Films. Multi-label
  percentages can sum above 100%; missing/conflicted facts remain in the denominator.
- Preference is the unweighted arithmetic mean of Film-level personal 1–5 ratings.
  At least 10 globally rated watched Films and 3 category Films are required.
  Below either threshold the preference value is null and excluded from ranking.
- Rewatching changes record counts only; unknown dates remain eligible. No recency
  weight, favorite bonus, external score, notes, inference or provider calls.
- Exposure sorts by count then stable key; preference by exact mean, rated count,
  then stable key. Display averages with one decimal place.
- Dedicated rebuildable Schema v5 projection, refreshed in the domain transaction.
- `/diary?view=dna` contains summary, metric/dimension selection and contributors.
  A Film filter retains the existing full-timeline behavior.

## Acceptance criteria

- [x] Formula boundaries, coverage partitions and profile isolation pass.
- [x] Media removal preserves history; Viewing/rating/fact mutations refresh atomically.
- [x] v4 upgrade, rebuild, restore and portable-export boundaries pass.
- [x] Three read-only APIs use bounded pagination and at most 10 SQL reads per request.
- [x] Bilingual desktop/375px Diary experience and history restoration pass.
- [x] Backend and frontend required checks pass and final diff is reviewed.

## Slices

1. Projection, shared factual selection and deterministic read API — Complete.
2. Diary DNA interface, contribution lists and cache invalidation — Complete.
3. Isolated verification, regression review and documentation — Complete.

## Verification evidence

- Worktree was clean before fast-forwarding main to `5e4fd20` and creating
  `feat/cinema-dna-v1` in the existing checkout.

- `uv run python -X utf8 -m unittest discover -s . -p 'test_*.py' -q` —
  219 tests run: 218 passed, 1 skipped. Includes formula boundaries, exact-mean ordering,
  duplicate Viewings/editions, profile isolation, historical Films, selected
  factual mutations, rollback, v4→v5 backup/upgrade, rebuild and verified restore.
- `uv run python -m compileall -q app` — passed.
- `npm run test:unit` — 39 passed; DNA query/history state and cache-family rules included.
- `npm run lint`, `npm run typecheck`, `npm run build` — passed on the final frontend.
- The deterministic 200/1,000-Film tests measured 3 SQL statements per API call,
  including BEGIN and readiness lookup (maximum 10). At 1,000 Films, observed
  single-query durations were 8.9/9.9/89.6 ms for overview/facets/contributors in
  the final full-suite run; timings are informational, not cross-machine gates.
- Isolated production browser smoke used ports 8765/5550, a 58-Film fixture and a
  copied standalone frontend build. Its backend rewrite targeted only the isolated
  service; production repository configuration was unchanged. The helper used
  hostname `localhost` to keep Next's normalized local middleware rewrites internal.
- English/Chinese desktop and 375x812 checks passed. Mobile navigation fits all
  three Diary entries; document width was 365 with a 375px viewport. Country
  localization and conflict coverage were visible without hydration errors.
- Confirmed exposure/preference switching, category selection, 55-Film contributor
  pagination (40 then 15), refresh/back/forward URL restoration, historical-Film
  Diary links and unknown-date records. Adding one Viewing changed the record
  count 58→59 while watched Film count stayed 58, including cache refresh.
- A fixture with 9 rated Films displayed the exact one-more-rating notice in
  both languages and no preference ranking. Source and per-Film ratings remained
  inspectable through exposure. Native Return activated a focused metric button;
  Tab moved focus between controls. Reduced-motion emulation preserved the
  interface with the existing global reduced-motion styles.
- Final application tab console inspection found no errors or warnings. After
  correcting the isolated helper to bind all service engines to its fixture,
  `/health`, `/workflows?limit=8` and Cinema DNA returned successful responses;
  a fresh bilingual mobile replay confirmed the 15-row contributor second page
  without backend error logs.
- Final review covered privacy fields, historical-Film independence, shared
  Explore semantics, SQL bounds, same-transaction refresh and API/Skill alignment.
- `git diff --check` — passed.
- Implementation commit `555298ff2110` was fast-forward merged into `main` and
  pushed on 2026-09-10. GitHub Actions
  [CI run 34435205359](https://github.com/ChiosYang/5X49/actions/runs/34435205359)
  passed both Backend and Frontend jobs against that exact commit.

## Remaining risks

- Representative real-library usefulness and Alpha comprehension are unverified.
- Gate B remains separate; no inferred Graph visibility is changed.
- This handoff merges source code; a production release was not requested.
