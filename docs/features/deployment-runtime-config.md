# Deployment runtime configuration

Status: Done
Last updated: 2026-10-10
Related: README.docker.md

## Goal

Make published/standalone deployment configuration predictable and prevent
optional watcher settings or misleading healthchecks from breaking startup.

## Scope and non-goals

- One runtime backend destination for API, SSE, and media requests.
- Correct default Compose/image healthchecks; documented media-directory setup.
- Safe numeric watcher environment defaults and removal of obsolete template settings.
- No new endpoints, data migrations, release, deployment, or authentication changes.

## Behavior contract and decisions

- Next route handlers share a streaming proxy instead of build-time rewrites.
  `BACKEND_URL` is resolved on each request, then legacy `API_URL`, then the
  existing development (`127.0.0.1:8000`) or production (`backend:8000`) default.
  Server-rendered data fetches use the same resolver, including trailing-slash cleanup.
- Preserve methods, encoded paths, query strings, request bodies, upstream status,
  redirects, cookies, authorization, range and conditional headers. Strip hop-by-hop
  headers and their Connection-nominated fields. Prefer identity encoding; strip
  stale length/encoding metadata when Fetch decompresses an upstream body.
- Stream response bodies without buffering; SSE disables intermediary buffering.
  Forward request aborts upstream. A connection failure returns 502.
- Image and default Compose probes use a five-second timeout and reject HTTP errors.
- Watch debounce/stability accept integer seconds 0–86400; polling accepts 1–86400.
  Empty, malformed, non-finite, fractional, and out-of-range values use defaults
  (5/15/5 seconds respectively), following existing TMDB environment validation.
- Media bind paths must exist before Compose startup. Default Compose fixed container
  names are distinguished from the release configuration's independent projects.

## Slices

1. Runtime proxy and HTTP regression tests: complete; rebuilt standalone checks passed.
2. Healthchecks and Docker setup documentation: implemented; snippet verification passed.
3. Environment defaults and template cleanup: complete; full suite and startup smoke passed.

## Verification evidence

- `npm run test:unit`: 76 passed (including real HTTP proxy unit regression).
- `backend/.venv/bin/python -m unittest discover -s scripts -p 'test_deployment_healthcheck.py' -q`: 2 passed.
- `backend/.venv/bin/python -m unittest discover -s scripts -p 'test_*release*.py' -q`: 10 passed, 1 Docker-dependent skip.

- Backend isolated full suite (`python -m unittest discover -p 'test_*.py' -q`):
  293 passed, zero skips, no API keys, temporary SQLite/media paths.
- `npm run lint`, `npm run typecheck`, and `BACKEND_URL=http://127.0.0.1:18000 npm run build`:
  passed on the final source. Regenerating build types removed a stale reference to
  the deleted dedicated SSE route from the pre-existing build.
- Actual rebuilt standalone with runtime backend `127.0.0.1:18001`: API, SSE, media
  with and without filename extensions all reach the runtime backend; zero requests
  reach the build-time backend. First SSE chunk arrived in approximately 2.5 ms while
  the upstream remained open. Methods, encoded paths/query/body, authorization,
  cookies, HEAD length, compression, redirect and conditional 304 probes passed.
- Proxy unit coverage also checks Range and upstream stream closure after request abort.
- Real backend + rebuilt standalone: `/`, `/zh`, `/en`, `/en/library`, `/api/health`,
  and `/api/library/films` return 200 (following the expected `/zh` redirect).
  API_URL-only legacy fallback also serves SSR library and API health successfully.
- Empty/malformed watcher environment startup: health 200 and defaults 5/5/15,
  including when the watcher is disabled. Temporary synthetic data only.
- `git diff --check`: passed.

## Remaining risks

- Docker is unavailable on this host; no image build or Compose execution claimed.
- No release or public deployment was performed. Verification is Linux x86_64 only.
