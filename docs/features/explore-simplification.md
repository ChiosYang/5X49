# Explore directory simplification

Status: In Progress
Last updated: 2026-10-22
Related: PR42 unified search; PR41 Collection hierarchy

## Goal

Explore opens directly on the complete paginated Collection catalog, below one
ordinary search input. Existing directory cards, category controls, spacing and
tokens are reused. The extra homepage sentence and search privacy hint are removed
in both locales, along with the All Collections entry button and manual Combined
filters workspace.

## Decisions

- The canonical directory is /explore with category/offset state. The old
  /explore/collections directory URL redirects there, retaining category/page.
- /explore/filter and historical root fact parameters redirect without mounting a
  manual editor. Only raw q is retained as a unified search, never an automatically
  synthesized plan from retired filter parameters.
- Collection identity remains in its stable detail path. Unified structured
  execution, removable condition explanations, viewing/sort/page controls and
  strict factual query services remain. The backend/model contract is unchanged.
- Existing graph links lead into unified search rather than generate retired
  manual-filter URLs. Clearing a search returns to the last catalog category/page.
- A completed submitted draft is released when its result URL commits, so
  cached Back/Forward restores each query. A newer edit or submission retains
  ownership while an older response is pending.
- No new worktree is created. The existing authorized clean isolated checkout is
  reused, with one branch based on freshly fetched main 800d5329d78486675d351a46088c5cfaf3922b78.
- PR28, Jev, real-model quality acceptance and budget holds remain untouched.

## Search capability boundary

Local keywords search Film titles, people and Collection labels; leading find/找
commands keep original input but use the remaining keyword. Complete rules can
combine one genre, one Person with any/director/actor role, one production country,
one full decade, watched/unwatched and title/year sorting. Examples include
unwatched Japanese drama films from the 1990s and 由是枝裕和执导的电影, subject to
eligible local metadata and exact identity resolution.

Unsupported similarity, mood/plot/theme, language, producer/writer roles, precise
years, ratings/runtime, negation/OR and multi-value requests must not run partial
conditions. Missing or duplicate identities require correction/choice. AI is
submission-only through the existing bounded interpreter and never receives the
library. Real model quality/Chinese accuracy/latency have not been certified by
mock tests, and no paid calls are authorized in this task.

Code: backend/app/services/discovery_search.py, backend/app/services/ask.py,
backend/app/contracts/ask.py and frontend/src/app/[locale]/explore.

## Acceptance criteria

- [x] Default Explore shows the full paginated catalog, with no All Collections entry button.
- [x] Manual Combined filters controls/components are gone from home, search and detail.
- [x] Retired URLs redirect without exposing the editor; typed q remains searchable.
- [x] Requested English/Chinese copy is absent; input error descriptions remain accessible.
- [x] Search correction, Collection identity, refresh, Back/Return and scroll/history remain correct.
- [ ] Desktop and 320px rendering is inspected, alongside unit/static/build/backend/E2E checks.
- [ ] Draft PR and exact-head CI/independent review precede a normal merge.

## Verification

- Frontend unit: 132 passed. Lint, typecheck and production build passed before
  the final submitted-query history regression; final-head checks run again.
- Targeted browser runs: Collection hierarchy 31 passed; simplified directory and
  unified search 39 passed. Manual-form-only tests are retired; mutation, stale
  response, pagination, history and Return regressions now exercise the retained
  Collection/search workflows. Extra full-suite coverage includes empty submit
  followed by Back, alongside the clear-button and consecutive-query regressions.
- Generated nine owned local test films with 30 distinct two-film director sets
  to verify the complete catalog across its 24-entry page boundary, preserving
  production duplicate-set suppression.
- Actual screenshots inspected in English and Chinese: desktop 1920/1440 and
  narrow 390/320, home, Collection detail, interpreted conditions and input error.
  Automated responsive checks also cover 1024/768. No screenshot upload is needed.
- A restricted-process backend test run stalled and was stopped by its verified
  task process identity; the byte-verified short-path snapshot is being rerun with
  local test-process support. Local Compose tooling tests require a Docker CLI
  that is unavailable on this Windows host; CI verifies those safe defaults.
  Full backend/browser CI and independent review remain
  required before merge. No real provider, user media or credentials are used.
