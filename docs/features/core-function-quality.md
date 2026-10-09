# Core function quality

Status: Done
Last updated: 2026-10-09
Related: Product loop and RC stabilization

## Goal

Make everyday film operations, viewing dates, import, browsing and maintenance
reliable and understandable using isolated verification data.

## Acceptance criteria and slices

1. [x] Film and edition actions handle rejected writes; committed writes survive
   read failure with a read-only refresh retry and actionable bilingual feedback.
2. [x] All “today” viewing defaults use the browser's local calendar date, tested
   at timezone and year boundaries.
3. [x] Same-folder editions are imported deliberately; extras are excluded and
   split media are not mistaken for editions. Primary selection is stable and
   can be explicitly changed without losing Film/edition data.
4. [x] Library/search use bounded queries and rendering, preserve filters and
   navigation state, and are measured with 1,000/5,000 isolated Films.
5. [x] Mobile detail titles wrap; status copy is bilingual; navigation supports
   Escape, focus containment/restoration and excludes inactive placeholders.
6. [x] Production exposes sanitized read-only diagnostics and usable guidance
   for existing backup, verification, offline restore and export capabilities.

## Decisions

- Work sequentially on an ordinary branch from refreshed main; preserve original
  data and secrets. No release or deployment.
- Reuse existing committed-write receipts and explicit cache reads.
- Keep legacy list response shape; add a bounded page endpoint for routed UIs.
- Do not perform live restore through the running application. Explain the
  existing verified offline restore boundary and media-backup responsibilities.
- Real TMDB checks use inherited Network secret injection with TLS verification;
  do not use the E2E TMDB simulator for live acceptance.

## Verification evidence

- Backend: `uv run python -X utf8 -m unittest discover -s . -p "test_*.py" -q` — 290 tests passed, including same-folder editions, primary preference, v1–v5 upgrade preservation, bounded reads and sanitized diagnostics.
- Frontend: `npm run test:unit` — 75 passed; `npm run lint`, `npm run typecheck` and `npm run build` passed.
- `uv run python -m compileall -q app` and `uv run python -m unittest discover -s ../scripts -p 'test_*.py' -q` — passed (13 release-tooling tests).
- Normal production application, isolated SQLite/media, inherited Network secret, verified TLS: 11 browser acceptance groups passed with no page errors. Search/candidate confirmation for Le Samouraï (5511), Crash (884/1640), detail and downloaded/poster-preview access succeeded. No-match returned 409 and retained failed state. Chinese entry routes returned 200.
- Favorite write rejection and committed-write/read failure recovered without replaying PUT. Shanghai local-calendar watched date was correct. Same-folder editions, excluded trailer, contiguous two-part edition, selected default and scrape state survived repeat scan and a full backend/frontend restart.
- Production maintenance checked real TMDB/API and poster CDN: both HTTP 200. Keyboard trap/Escape/focus restoration and 390 px title wrapping passed; screenshots retained in the task's isolated artifacts.
- Normal 5,000-Film Library/search/favorite pages rendered 40 cards; return restored page 2 and card focus. Isolated 7-run read benchmark: 1,000-Film page median 11.35 ms vs legacy 62.97 ms; 5,000-Film page 42.09 ms vs 451.41 ms, search 55.51 ms and favorites 90.37 ms. Response fell from approximately 10 MB to 80 KB. These are local measurements, not deployment latency guarantees.
- Verified backup, manifest validation, offline restore to a separate disposable target and portable-export validation passed. Primary/profile/scrape state and all 6 Films matched the live snapshot; integrity and foreign keys passed.
- Code review corrected retired asset-locator matching and added a replaced-path regression. Existing mocked route tests were changed to avoid application lifespan/default-DB initialization. Default DB remains its initial empty file; 53 original media files retain size and modification time.

## Remaining risks

- Extras are recognized by common suffixes; contiguous CD/Disc/Disk/Part grouping is conservative. Every part's independent NFO keeps separate editions. Split media report filenames; playback concatenation is outside this change.
- Routed Library/search and metadata care are bounded. Legacy full-list callers remain compatible and can still load the entire library.
- Schema v6 adds a nullable default-edition FK and rebuilds Library/detail projections on upgrade. Normal migration backup and verified offline restore remain required operational safeguards.
- Local diagnostics check readiness and versions; use the documented projection CLI for full consistency. Full backup can contain secrets and paths; media/NFO/artwork need separate backup. Portable export currently has no import UI.
- Browser preview depends on proxy CA trust. Live acceptance used the existing trusted Chromium CA store; no TLS bypass was used. Deterministic CI fixtures are regression coverage and are separate from the real TMDB evidence.
