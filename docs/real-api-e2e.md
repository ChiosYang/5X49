# Real API browser acceptance

Prerequisites: Node 22+, uv with Python 3.13, FFmpeg/ffprobe, and Chromium's system
libraries. From a fresh checkout, install dependencies once:

```bash
uv sync --project backend --locked
npm ci --prefix frontend
cd frontend
npx playwright install --with-deps chromium
```

Run from `frontend/`:

```bash
npm run test:e2e
```

The runner builds the production frontend, starts the standalone Next server (as in the frontend container) and real FastAPI on
loopback ephemeral ports, and creates an owned temporary directory with SQLite,
normal/mixed media fixtures (including valid short audio/video), an empty media
root, artwork cache and operation manifests. It uses no real library or provider
credentials. The runner refuses frontend `.env`/production environment files so Next cannot load private configuration. Watchers are disabled. Both servers stop and temporary data is removed
on success/failure; do not run concurrent suites in the same checkout because
Next build output is shared. Windows is not yet verified; CI uses Ubuntu.

A locally installed Chromium can be selected with `E2E_CHROMIUM_PATH` (an absolute
executable path). The normal CI/default path uses Playwright-managed Chromium.

The serial suite represents one deliberate lifecycle: empty install → scan →
state/query/navigation/viewings → metadata review → tasks → backend restart.
Later cases require earlier setup; a failed prerequisite skips dependent cases.
Retries are disabled so a partial lifecycle is never silently reused.

Real: FastAPI HTTP routing, validation, SQLite migrations/projections, scan parsing,
FFprobe, settings, profile writes, Viewing writes/deletes, metadata confirmation,
workflow store/cancel/retry, and process restart persistence.

Explicit substitutes: TMDB search/details are deterministic provider responses;
scan completion and worker scheduling can be held by a token-protected test-only
entrypoint. Selected browser writes/reads/cancel requests return injected failures
or delays. AI interpretation is not called; Ask's no-key local route is real.
Outbound browser requests are rejected and Python socket connections to nonlocal
hosts are rejected. This is not a host firewall or OS network namespace.

On failure, `frontend/test-results/` contains screenshots and Playwright traces;
`frontend/playwright-report/` contains the HTML report, and
`frontend/e2e-artifacts/` contains build/server logs. CI uploads these for seven
days. They contain generated test data and paths only, never an application DB or
credentials. These ignored directories can be removed after inspecting failures.

Coverage does not claim live provider quality/availability, NAS permissions and
latency, real physical touch devices, or a full accessibility audit.
