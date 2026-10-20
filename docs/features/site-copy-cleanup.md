# Site copy cleanup

Status: Done (implementation and local acceptance; independent review and merge delegated to parent)
Last updated: 2026-10-20
Base: `b334e0fdcff0a22a8a29f3e9c03770f0cd7ee881` (main, PR32)

## Goal and contract

Remove redundant supporting copy throughout the existing site. In particular,
Library no longer renders the English or Chinese “films matching” sentence for
any search result count, including zero. Search, filters, pagination, return
context, transparent navigation, large titles, and the recent Explore/Library
presentation remain intact. No backend, data model, information architecture,
provider calls, or destructive action behavior changes.

## Actual route inventory and decisions

All paths below are locale-aware (`en` and `zh`; Chinese also has unprefixed
canonical paths). Query views are listed because they render distinct screens.

| Route or screen | Remove | Keep and why |
| --- | --- | --- |
| `/` | Nothing; redirects to Library | Existing landing behavior |
| `/library`, `?q=…` | Matching-results sentence and its margin, both message keys | One visible responsive result count; applied search/filter chips; no-match explanation and reset link; loading/error recovery |
| `/search?q=…` | No separate UI; redirects to Library | Locale, query and explicit page compatibility |
| `/library?view=metadata` | Header subview name repeated by the selected tab | Queue count, film/year, review progress, candidate facts, confirmation and failures |
| `/library?view=inbox` | Header subview name repeated by the selected tab | Ready vs stabilizing counts, file paths, organization preview/conflicts and confirmation |
| `/library?view=offline` | Header subview name repeated by the selected tab | Missing locations, scan advice, removal scope and confirmation; meaningful empty-state explanation |
| Empty Library onboarding | Nothing | Directory labels, scan steps, container path help, scan outcomes/recovery, optional provider configuration explain actual setup |
| `/explore` and filtered/results/lens/finder views | Nothing further | Recent PR30/31 styling; AND/OR, unresolved facts, coverage, role/year facts, pagination and no-results recovery carry meaning |
| `/diary`, `?view=recent` | Personal Timeline eyebrow and prose restating the diary purpose; redundant header divider | Timeline/recent tabs, viewing dates/precision, source/read-only state, notes/ratings, empty/error states and load more |
| `/diary?view=dna` | Perspective eyebrow and generic introduction | Coverage/missing/conflicting facts, method explanation, metric labels and thresholds, contributing films and pagination |
| `/diary?film=…` | Same diary header cleanup | Film filter label, film identity, add/edit viewing and return context |
| `/library/[id]` (direct and intercepted overlay) | Personal Viewing eyebrow; fixed fictitious “ARCHIVE NO. 001” genealogy eyebrow; duplicate original title only when exactly equal to the displayed title | Distinct original title and all film facts, technical fields, editions/paths/status, personal data, viewing count (only three previewed), analysis state/evidence/source policy, editor/confirmation text |
| `/library/identity-review` | Nothing | Description explains uncertain identities; evidence/reason, total vs page, read-only restrictions, effects and expiring undo warnings are necessary |
| `/library/activity` | Audit trail eyebrow; duplicate header divider above filter divider | Entire Activity destination, event count, time/type/identity/payload, filtering, snapshot preview, restore risk and confirmation |
| `/library/manage` | Media Constellation eyebrow, generic system-view introduction, live-topology tagline, repeated Inspector eyebrow | System/service status, map mode, keyboard hint, counts, node relationships, queue completeness, operations, backup/health controls and risk/confirmation text |
| `/library/manage/concepts` | Study footer and generic “try each model” instruction | Mock-data/no-real-API warning, model comparison, scenario data and interactive tasks |
| `/library/manage/visual-concepts` | Visual interaction lab eyebrow, repeated fixed-variables badge and study/assessment footer | Existing title, model explanations, comparison criteria attached to models, task state, interactions and reset |
| `/settings` general | Generic page subtitle; section eyebrow/intro; language-control description restating its label | Settings/section titles, language labels and save feedback; roadmap unavailable-state explanation |
| `/settings?section=integrations` | Section eyebrow/intro; AI-provider panel summary; model, connection-test and endpoint descriptions restating controls | Model/service labels, provider state/errors, TMDB purpose, credentials controls, advanced endpoint context |
| `/settings?section=library` | Section eyebrow/intro; metadata-preferences and automation panel summaries | Root configuration/removal semantics, artwork language semantics, auto-scan scope, immediate organization and review-before-write warnings; danger zone unchanged |
| `/settings?section=maintenance`, `/admin/health` | Nothing | Diagnostic limitations, provider checks, backup coverage/privacy, restore procedure and commands distinguish real operational risks |
| `/ask` | ASK YOUR CINEMA eyebrow and generic flow introduction | Mode/field labels, question privacy and model-data notice, no-key/status failure, preview/confirmation, fact limitations, results and empty-state recovery |
| Shared navigation/menu | Project tagline | All destinations, controls, accessible labels and shortcuts |
| Locale route error boundary | Connection Interrupted eyebrow repeating the main error | Failure title, required-backend explanation, diagnostic command and retry |

Parallel-slot defaults/catch-all routes (`library/@detail/default`,
`@detail/[...catchAll]`, Activity and management slot clearing pages) render no
independent copy. `@detail/(.)[id]` shares MovieDetailView with the direct route.
`/api/[[...path]]`, `/media/[[...path]]`, and favicon are transport/assets, not
additional product pages.

The framework-generated not-found screen retains its necessary 404 status and
message; there is no additional authored not-found page to simplify.

## Layout and accessibility decisions

- Removing an eyebrow also removes its title's compensating top margin.
- Diary/Activity no longer stack a header divider with the next navigation/filter
  divider. Settings header height and empty setting-feedback spacing are reduced.
- Desktop's remaining film count has `role="status"`, as the mobile count already
  did; search results remain accessible without the redundant query sentence.
- Field labels, screen-reader labels, actual metadata and personal records are
  not selected for deletion by font size.
- Existing prototype pages have Chinese demo content in both locales. This task
  does not translate those studies or change their simulation behavior.

## Verification

- New `site-copy.spec.ts`: all rendered route/views in both locales at desktop
  and mobile sizes, screenshots, no overflow, transparent nav, removed copy,
  retained Ask privacy, empty-library/no-result/error recovery at 320 px.
- Updated `navigation-search.spec.ts`: nonzero and zero results have the count
  and necessary empty hint, without the matching sentence; existing IME,
  keyboard, mobile, pagination, legacy links and retry tests remain.
- `npm run test:unit`: 94/94 passed. Set `TEMP`/`TMP` to a long-form workspace
  path for existing glob tests on Windows; the default shortened user path makes
  those tests fail. Unsandboxed loopback is required by the proxy test.
- `npm run lint`, `npm run typecheck`: passed on final source. Temporary browser
  transform caches were removed before linting.
- `npm run build -- --webpack`: passed, also rebuilt by the final browser run.
  Default Turbopack first failed fetching Google fonts inside the sandbox, then
  its Windows PostCSS worker exited before IPC connected. The local-only E2E
  runner was a temporary copy of `e2e/run.mjs` changing only the build backend to
  webpack; it was deleted after verification. Production scripts are unchanged.
- Complete local real-Chrome E2E run: 103 passed, 2 failed, 8 skipped. The filter
  test attempted to interact between native navigation and hydration; it now
  waits for the touch-card control to hydrate, following the existing test's
  readiness pattern. The unchanged backup-generation E2E returned
  `backup_failed`; its serial follow-ups were skipped. No backup code was edited.
- Final `node frontend/e2e/run-copy.local.mjs library-filters.spec.ts
  site-copy.spec.ts navigation-search.spec.ts`: 33/33 passed (2.2 minutes),
  including the fixed filter case and both identical/distinct original titles.
- `.venv/Scripts/python.exe -X utf8 -m unittest test_maintenance_backup.py -q`:
  11/11 passed. This narrows but does not explain the local full-E2E backup failure.
- Real Chrome UI inspection: English `tape` no-results screen and Chinese
  Settings navigation checked through the browser interface as well as E2E.
- 95 final screenshots: 88 route/locale/viewport combinations, 6 narrow empty/error
  states, and the distinct-original-title case. Four contact sheets and eight
  representative original screenshots were visually inspected. All route checks
  fit the viewport, kept transparent navigation, and produced no unhandled page
  errors or AI requests. Existing Explore and Library tests cover 320–1920 px.
- `git diff --check`: passed. CI and independent review are tracked on the PR;
  merge is intentionally left to the parent thread.

### Representative Library uploads

| Screenshot | Confirmed Library ID |
| --- | --- |
| English desktop search for `tape` | `libfile_d485f5fb457881919e47a09847737f7e` |
| Chinese mobile search for `tape` | `libfile_e16c05c0625c8191a60a525eafa2ee04` |
| Chinese desktop Diary | `libfile_717c76d0557481919813651feca7d9ad` |
| English mobile integration settings | `libfile_b801ccb3045481919538cba601c60296` |
| Chinese desktop management | `libfile_111770a5c02081919b18182f3a7f3a15` |
| Chinese mobile Ask (privacy retained) | `libfile_3a16b436f17c8191ba0e315af3571342` |
| Chinese 320 px error/retry | `libfile_b577333b053481918745e8f7903a7032` |
| Distinct original film title retained | `libfile_8f9f783423ec819198405f2785488256` |

## Remaining questions

Kept copy about review semantics, provenance, missing metadata, destructive scope,
AI data transmission, and demo-only behavior whenever it carries product
meaning. No ambiguous copy was removed on a guess. No product decision blocks
the scoped cleanup.
