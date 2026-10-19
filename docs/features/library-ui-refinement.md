# Library UI refinement

Status: In Progress
Last updated: 2026-10-19
Related: User-requested Library presentation changes

## Goal

Bring films back onto the first screen while retaining the large editorial title,
transparent navigation, all filtering capabilities, and existing film operations.

## Behavior contract

- Filter opens a right-hand modal drawer, closed on initial navigation even when
  conditions are applied. Search, watched status, favorites, duration, personal
  rating and year ranges still submit a native GET URL. Sorting survives Apply.
  Rapid identical submissions produce one navigation so a late duplicate cannot
  close a newly reopened drawer.
- Applied conditions remain visible in a compact summary, with a clear action and
  an active indicator on Filter. Invalid ranges remain correctable in the drawer.
- Filter, Sort, Scan for films and More use borderless icon buttons with tooltips,
  accessible names, focus rings and at least 44 by 44 CSS pixel targets.
- The desktop film grid has four columns at 1920 and 1980 pixels; smaller layouts
  retain one, two and three columns.
- Mouse hover restores the delayed glass inspector. Keyboard focus exposes the
  same actions, Escape dismisses it and returns focus, hidden actions cannot be
  tabbed to, and touch devices retain a visible toggle.
- Identity review remains available in the header. It compares identity conflicts
  and edition reconnection evidence; its workflow is unchanged.

## History and decisions

The inspector follows `1aa1792726af9ad91235fa6d1ffbf06fb21ced56`: image zoom and
shade, overlaid title/director/year, lower title fading, glass panel with watched/
diary, favorite, synopsis, external scores, media specifications, country and tags.
`033884ffc89a880bfa1b89e5cdc127952fe3cd93` replaced that hover panel with a fixed
ellipsis toggle. Restore the former presentation while keeping keyboard and touch
access and the later mutation/retry behavior.

The drawer reuses the existing Dialog focus isolation, focus trap, scroll lock and
focus restoration. The committed URL remains the sole applied-filter state.
No backend, public API, media files or personal data changes are required.

## Verification evidence

- `npm run lint` and `npm run typecheck`: passed during implementation.
- `npm run test:unit`: 92 passed using a task-local TEMP/TMP path. Windows 8.3
  short paths in the default temp directory trip the existing ESLint glob tests.
- Production Next build: passed through the E2E harness.
- `npm run test:e2e -- library-ui.spec.ts library-filters.spec.ts library-filter-care.spec.ts interactions.spec.ts`:
  40 passed against the real isolated test backend and installed Windows Chrome
  155.0.8059.40. Outbound browser/backend traffic is blocked by the harness.
- Browser images inspected: `frontend/e2e-artifacts/library-ui-1920x1080.png`,
  `library-ui-1980x1080.png`, `library-ui-mobile.png`, `library-ui-hover.png`,
  `library-ui-focus.png`, `library-ui-touch-actions.png`, `library-ui-filter-drawer.png`
  and `library-ui-mobile-drawer-zh.png`. Responsive assertions cover 360, 768 and
  1024px too. The capture helper requests a full repaint to avoid incomplete
  backdrop-filter frames in Windows Chrome screenshots.
- Self-review: checked native GET state, duplicate submission, invalid ranges,
  focus isolation/return, pointer crossing, adjacent film actions and touch access.

## Remaining work

- Independent PR review and required CI checks before merge. Implementation and
  local acceptance are complete; the task branch remains isolated from other work.
