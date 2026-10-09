# UI consistency

Status: Done
Last updated: 2026-10-09
Related: `DESIGN.md`, `ui-primitives-extraction.md`

## Goal

Bring the identified everyday controls back to the monochrome editorial cinema
contract while preserving existing navigation, metadata and maintenance flows.

## Acceptance criteria

- [x] Explore uses semantic neutral surfaces, role-based small radii and shared
  white keyboard focus; no undefined gold classes or decorative warm gradient.
- [x] Menu and metadata confirmation controls have at least 44 px targets.
- [x] Search and pagination reuse shared button typography, hover and focus.
- [x] Unmatched films expose a labelled primary matching action; matched films
  keep a restrained toolbar. Existing candidate confirmation and errors work.
- [x] Backup coverage/privacy stay visible; advanced commands and offline
  recovery steps are collapsed initially and keyboard-accessible.
- [x] Advanced constellation layout is preserved; its action controls and
  supporting text use the shared sizes and readable semantic tones.

## Decisions

- Use the current main in the existing checkout, on an ordinary branch.
- Keep compact button padding but give important controls the same 44 px target.
- Reuse the existing Settings disclosure; retain every backup/restore step.
- Preserve data, API contracts, secrets, TLS verification and constellation
  layout. Use disposable SQLite data and media for browser verification.

## Verification evidence

- `npm run lint`, `npm run typecheck`, `npm run build`: passed.
- `npm run test:unit`: 75 passed.
- Two focused Playwright regressions against the normal production application:
  passed; no E2E transport launcher was used for this local verification.
- Isolated database/media browser acceptance: 21 checks passed, zero uncaught
  page errors. English and Chinese at 1440, 390 and 375 px cover Explore,
  fact selection, focus restoration, menu, native GET search, query/locale-aware
  pagination, collapsed/expanded maintenance and the constellation command UI.
- Real TMDB acceptance with the inherited Network secret and TLS verification:
  Le Samouraï (1967), TMDB 5511; search and confirmation HTTP 200, complete
  identity, browser poster loaded, matched toolbar restored. Provider diagnostics
  returned TMDB 200 and poster CDN 200; no-result action returned 409 with
  explicit feedback and no page error.
- The 375 px no-result check exposed edition filenames exceeding their parent;
  constrained their width and extended the existing edition regression with a
  long filename at 375/390/1440 px. Added three UI interaction regression cases,
  including the labelled pending-to-matched action and its DOM focus order.
- Code review: checked locale routes, pending/matched semantics, keyboard order,
  shared control sizing, popover wrapping and preservation of backup guidance.
- Original SQLite file and media snapshots remained unchanged; all writes used
  disposable test data.

## Remaining risks

- Live provider access depends on the runtime Network secret and trusted proxy
  CA. CI's existing deterministic transport regression is separate from the
  successful live-provider acceptance above.
- The shared compact button now uses the 44 px target; padding remains compact.
  The affected public pages were checked at the viewport sizes above.
