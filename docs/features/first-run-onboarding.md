# First-run Onboarding

Status: Done
Last updated: 2026-08-28
Related: `README.md`, `README.zh-CN.md`, `docs/install-baseline.md`

## Goal

Let a new local user go from an empty Library to a validated media directory,
a completed first scan, and visible Films without having to discover separate
Settings and Library Management routes.

## Scope

- Add an inline empty-Library onboarding flow for media-root setup and scanning.
- Add a short, session-scoped cinematic intro as progressive enhancement for
  the true empty-Library onboarding.
- Expose non-secret media-root availability in the settings API.
- Distinguish a genuinely empty Library from an empty filtered result.
- Provide localized recovery for backend connection failures and zero-result scans.
- Align the published-image Docker path, environment examples, setup script, and
  developer documentation with current runtime behavior.

## Non-goals

- Persisting an onboarding-complete flag or adding user accounts.
- Seeding demonstration data.
- Making TMDB or an analysis-provider key mandatory for the first scan.
- Adding full readiness probes, image digests, or reproducible-image guarantees.
- Adding audio, bitmap assets, a replay control, or a persistent onboarding flag.

## Existing behavior

- The empty Library tells users to scan but provides no action.
- Media-root setup and manual scanning live on separate routes.
- `GET /settings/media-dir` returns only the configured path even when it is
  missing or unreadable.
- Docker and local-development documents disagree about ports, environment
  files, optional credentials, and whether source is built locally.

## Acceptance criteria

- [x] A genuinely empty Library renders an inline directory and scan workflow.
- [x] A filtered non-empty Library renders a resettable no-results state instead.
- [x] Media-root status reports existence and readability without listing content.
- [x] Scanning is disabled until the media root is a readable directory.
- [x] The UI reports queued, running, failed, successful, and zero-result scans.
- [x] A successful non-empty scan refreshes into the normal Film grid.
- [x] TMDB and analysis-provider setup are clearly optional.
- [x] Backend failures render localized recovery actions.
- [x] Published-image Docker and source-development instructions are internally consistent.
- [x] The first empty-Library visit in a browser session plays a non-blocking
  cinematic intro and subsequent visits in that session skip it.
- [x] Reduced-motion users skip the intro and receive the complete onboarding immediately.
- [x] Relevant backend and frontend checks pass.

## Decisions

- Derive onboarding visibility from total Film count; do not store completion state.
- Reuse one media-directory control in onboarding and Library Settings.
- Use `POST /library/scan` and `GET /library/sync/status` for both onboarding and
  Library Management; retain `/sys/scan-library` for compatibility.
- Do not add sample data. A zero-result scan remains in onboarding and shows the
  supported directory shape and recovery links.
- Treat the root Compose file and published images as the default end-user path.
- Store only the presentation-level intro marker in `sessionStorage`; it never
  participates in Library emptiness, scan state, or onboarding completion.
- Render onboarding independently of the decorative overlay, which is
  pointer-transparent, hidden from assistive technology, and transform/opacity-only.
- Server-render the initial cover and run a tiny pre-paint session check so the
  onboarding cannot flash before hydration; CSS hides repeat/reduced-motion
  visits and provides a 1.3-second no-hydration fallback.
- Match the empty-Library layout to Figma node `17:3`: a 40px transition from
  the Library header, a borderless onboarding section, a 1.35/0.65 desktop
  split, indented scan actions, and inline ready-state feedback in the path field.

## Open questions

- None blocking.

## Slices

### Slice 1 — Media-root contract

Status: Complete

- Intended behavior: expose safe path availability and actionable validation errors.
- Likely affected areas: settings API, API contract tests, API documentation.
- Dependencies: existing settings storage and path validation.
- Verification: focused backend API tests.

### Slice 2 — Inline first-run experience

Status: Complete

- Intended behavior: configure the media root, run and observe the first scan,
  and recover from empty results or backend failure on the Library page.
- Likely affected areas: Library empty state, shared media-directory control,
  settings hooks, translations, File Browser.
- Dependencies: Slice 1.
- Verification: frontend unit checks, lint, typecheck, build, and browser smoke.

### Slice 3 — Installation guidance

Status: Complete

- Intended behavior: provide one accurate published-image path and a separate,
  minimal source-development path.
- Likely affected areas: Compose files, environment/setup templates, root and
  service README files.
- Dependencies: finalized onboarding behavior and runtime ports.
- Verification: documentation review and `docker compose config` when available.

### Slice 4 — Cinematic first-run intro

Status: Complete

- Intended behavior: play a 1.3-second film-gate, brand, and scan-beam intro
  once per browser session without blocking or replacing the underlying workflow.
- Likely affected areas: onboarding client component, presentation-state helper,
  onboarding unit coverage.
- Dependencies: Slice 2 and the existing Framer Motion dependency.
- Verification: unit checks, lint, typecheck, build, reduced-motion and responsive browser smoke.

## Verification evidence

- `uv run python -m unittest test_api_routes.ApiRouteContractTests` — 14 tests passed.
- `npm run test:unit` — 8 tests passed, including intro eligibility and onboarding state derivation.
- `npm run lint` — passed without warnings.
- `npm run typecheck` — passed.
- `npm run build` — production build and route generation passed.
- `C:\Program Files\Git\bin\bash.exe -n setup.sh` — syntax passed.
- Isolated `setup.sh` runtime smoke — the default input created `./media` and
  `.env` with exit code 0; a missing custom path stopped before writing config
  with exit code 1. Temporary directories were removed afterward.
- Browser smoke with an isolated temporary database and media root — Chinese and
  English onboarding rendered; missing-directory validation was localized; an
  empty scan showed layout guidance; a minimal NFO scan imported one Film and
  refreshed into the grid; a favorite filter with no matches did not show
  onboarding; backend failure and retry recovery succeeded.
- Browser smoke at 375 × 812 — no document, body, or onboarding horizontal overflow.
- Cinematic intro browser smoke — the overlay remained visible for 1,345 ms,
  then detached; it exposed `pointer-events: none` and `aria-hidden="true"`,
  allowed editing the media-directory input while visible, and did not replay
  after leaving and returning in the same tab.
- Reduced-motion browser smoke — emulated `prefers-reduced-motion: reduce`
  skipped the overlay while leaving the onboarding visible.
- Non-empty and filtered-empty browser smoke — neither state mounted the intro.
- Cinematic intro browser smoke at 375 × 812 — overlay and document widths
  stayed within the viewport before and after the animation, in Chinese.
- Initial-HTML regression probe — the empty-Library response contains both the
  onboarding and its opaque intro cover, preventing a pre-hydration content flash.
- Browser first-paint probe — when onboarding first appeared, the intro overlay
  was already `display: block` at opacity `1`; repeat-session and reduced-motion
  visits rendered onboarding with no visible overlay or console warnings.
- Figma node `17:3` comparison at 1864px — the rendered desktop geometry matched
  the 1736px content width, 1139/548px columns, 48px gutter, 433px grid row,
  938px path field, and 56px scan-action indent; the Figma node exposed no motion tracks.
- Responsive browser smoke at 375 × 812 — the revised onboarding had no document
  or body horizontal overflow and retained the stacked controls and readable sidebar.
- Temporary browser tab, backend/frontend processes, database, and media fixture
  were removed after the smoke.

## Remaining risks

- Docker is unavailable in the current environment, so `docker compose config`,
  image pull/start, container path permissions, and published-image smoke remain
  unverified.
- Clearing data was not invoked through the UI during browser smoke; the same
  empty-Library behavior was exercised with a fresh isolated database and is
  covered by the total-Film-count unit contract.
