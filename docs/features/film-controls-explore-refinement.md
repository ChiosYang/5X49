# Film controls and Explore entry refinement

Status: Done
Last updated: 2026-10-10
Related: `DESIGN.md`, `docs/features/factual-explore.md`

## Goal

Make common Film actions immediately available and expose the four Explore
entrances earlier, while preserving the cinematic presentation.

## Scope

- Labelled watched/favorite controls, with lower-frequency actions in More.
- Existing metadata matching, artwork, score/edition mutations and analysis flows.
- A shorter bilingual Explore introduction and a responsive two-column Lens Deck.
- Existing large titles, transparent navigation, typography and backend contracts.

## Acceptance criteria

- [x] More supports mouse, keyboard, Escape, Tab exit and outside click.
- [x] Artwork returns focus to its More action without changing its close rules.
- [x] Busy/failed actions retain feedback and do not duplicate requests.
- [x] Metadata matching keeps explicit candidate confirmation.
- [x] All four Explore entries fit the first 390px-wide viewport in both locales.
- [x] Unit, lint, typecheck, production build and real-browser E2E pass.
- [x] Desktop and narrow-screen synthetic-fixture screenshots are inspected.
- [x] Independent code review has no unresolved blocking finding.

## Decisions

- Keep mutation ownership in the existing hooks and Film component.
- Use an ordinary-button disclosure for More, preserving normal Tab order.
- Artwork uses its existing dialog through a portal so the popover cannot clip it.
- The analysis action scrolls and focuses the existing section without adding history.
- Candidate details consume Escape before More, and More before a containing detail dialog.
- A pending disabled action may lose focus to body; Escape can still close More.
- Keep the Film action instance across profile refreshes and synchronize profile versions.
  A late server refresh must preserve an already-open More or artwork dialog.
- Stack controls between md and xl so icons and labels retain their space.
- Preserve Lens artwork, coverage and interaction semantics while reducing repeated copy.
- Long Lens preview labels truncate with a full-text title; typography remains unchanged.

## Verification evidence

- `npm run test:unit` — 76/76 passed.
- `npm run lint` and `npm run typecheck` — passed.
- `npm run test:e2e` — production `next build` and 21/21 browser tests passed.
- Windows TEMP/TMP used a canonical task-local directory to avoid 8.3 alias differences.
  The two-edition fixture budgets its filename length on Windows; long Film titles remain.
- Real Chromium checked 390, 768 and 1440px controls, nested artwork return, busy/error
  behavior, metadata confirmation, and detail overlay return. Both 390px locales expose
  the four Explore entries in the first viewport.
- The late-refresh regression gates the RSC response, opens More after read retry,
  waits for the persisted profile version to enter the component, and checks More
  remains open, subsequent operations work, and no write is replayed.
- Independent code review and browser/pixel review found no remaining blocking issue.

## Remaining risks

- Provider credentials and real media were not used; artwork pixels are synthetic.
- Remote PR checks and merge coordination are handled by the parent task.
