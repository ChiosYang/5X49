# Safe Compose defaults and real API browser acceptance

Status: Done
Last updated: 2026-10-08
Related: PR #12 interaction recovery

## Goal and scope

Keep ordinary published-image installs local/read-only by default. Preserve the
seven interaction fixes with a repository-owned Chromium suite exercising the
real HTTP app, database, background workflows and generated media.
No pagination, Alpha recruitment, deployment or release is included.

## Acceptance

- [x] Ordinary Compose defaults to loopback ports and read-only existing media;
  explicit LAN/write opt-ins and bilingual installation guidance.
- [x] One documented command runs production frontend + isolated FastAPI with
  generated valid/abnormal NFO/video, fresh SQLite and private manifests.
- [x] Seven interaction flows, bilingual narrow-screen use and process restart
  persistence have repeatable browser assertions.
- [x] CI retains failure traces/screenshots/logs and cleans only owned resources.
- [x] Independent review, frontend/backend checks and Compose rendering pass.

## Boundaries

The test-only Python entrypoint imports the production app without changing its
routes/services. It replaces TMDB transport data only, controls scan timing and
worker scheduling, and uses authenticated test-only controls. Browser faults are
explicit one-request-class interceptions. Production never imports test controls.
Provider keys/proxies are not inherited. Browser routes reject third-party URLs;
Python socket connect rejects non-loopback destinations. This is a guard for the
exercised HTTP clients, not an operating-system network sandbox.

## Verification

- Real browser suite: 8 serial lifecycle scenarios passed with system Chromium,
  including a 320px-wide ffprobe result from generated valid media. Twelve normal
  and sixty mixed fixture cases are generated in a fresh temporary directory.
- Frontend lint, typecheck, 68 unit tests and production build passed.
- Backend full suite: 265 tests passed. Script suite: 13 tests passed, including
  rendered ordinary Compose defaults and explicit LAN/write overrides.
- Release Compose still renders with explicit placeholder image digests; its
  file and release workflow are unchanged. No images were rebuilt for the
  Compose-only change; Dockerfiles and image contents are unchanged.
- Independent code reviews found and resolved query-string interception and
  process-start failure cleanup gaps. Two focused subprocess tests cover failed
  startup and signal termination. No remaining blocking findings.
- Production standalone mode exposed an E2E hostname mismatch: Next normalizes
  loopback addresses to localhost, so the harness now binds and requests the
  frontend consistently as localhost. Product routing was not changed.
- Browser faults retained screenshots/trace/logs during development; final
  successful runs clean their processes and generated data. CI uploads only
  failure artifacts, retained seven days.

## Remaining limits

Chinese coverage is the Ask confirm/query narrow-screen flow, not all seven
flows in both languages. Restart verification concerns the backend process.
Do not interpret provider fixtures as live TMDB/AI quality, generated media as
real NAS acceptance, or touch emulation as physical device/screen-reader coverage.
Host firewall/network settings were never changed. No deployment was performed.
