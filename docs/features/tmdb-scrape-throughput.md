# TMDB Safe Scrape Throughput

Status: Done
Last updated: 2026-08-25
Related: none

## Goal

Speed up whole-library TMDB scraping without concentrating user-provided API
key traffic into unsafe bursts or changing existing scrape results and APIs.

## Scope

- Process up to three movies concurrently by default.
- Limit TMDB API requests to six per second with a three-request burst.
- Coordinate retry and cooldown behavior for rate limits and transient errors.
- Serialize metadata persistence and prevent concurrent writes to one movie.
- Allow bounded environment overrides for concurrency and request rate.

## Non-goals

- Frontend tuning controls or retry statistics.
- Persistent TMDB response caching.
- Changes to REST payloads, database schemas, or API-key precedence.

## Existing behavior

Whole-library scraping processes one movie at a time. TMDB calls use standalone
`requests.get` calls without connection reuse, explicit throttling, or 429
retry handling. Movie details already combine credits, external IDs, and images
with `append_to_response`.

## Acceptance criteria

- [x] At most three movie scrapes run concurrently by default.
- [x] All metadata TMDB calls share a six-request-per-second token bucket.
- [x] 429 responses pause all callers and retry transient failures safely.
- [x] One failed movie does not stop the batch or corrupt aggregate counts.
- [x] Same-movie and SQLite/Event Store writes are serialized.
- [x] Full backend regression tests pass and Compose declarations are consistent.

## Decisions

- Keep the synchronous `requests` stack and use a bounded thread pool.
- Use thread-local sessions because `requests.Session` is not shared across
  worker threads.
- Let in-flight movies reach a safe completion after cancellation, while
  stopping new submissions.
- Keep image CDN requests outside the TMDB API token bucket.

## Open questions

- None.

## Slices

### Slice 1 — Govern TMDB requests

Status: Complete

- Intended behavior: connection reuse, token-bucket throttling, coordinated
  429 cooldown, transient retries, and credential-safe errors.
- Likely affected areas: TMDB transport and settings.
- Dependencies: none beyond existing `requests`.
- Verification: focused TMDB client unit tests.

### Slice 2 — Run bounded concurrent batches

Status: Complete

- Intended behavior: sliding three-movie window with safe progress,
  cancellation, persistence, and per-movie locking.
- Likely affected areas: metadata job actor and scraper.
- Dependencies: Slice 1.
- Verification: concurrency, failure-isolation, cancellation, and lock tests.

### Slice 3 — Configure and verify

Status: Complete

- Intended behavior: Compose overrides, documented defaults, and complete
  regression evidence.
- Likely affected areas: environment examples, Compose, and install docs.
- Dependencies: Slices 1 and 2.
- Verification: full unittest discovery and Compose config validation.

## Verification evidence

- `uv run python -X utf8 -m unittest test_tmdb_client.py test_metadata_batch_concurrency.py test_metadata_scraper.py` — 21 tests passed.
- `uv run python -X utf8 -m unittest discover -s . -p "test_*.py"` — 150 tests passed.
- `rg -n "TMDB_(SCRAPE_CONCURRENCY|API_REQUESTS_PER_SECOND)" backend/.env.example docker-compose.yml docker-compose.release.yml docs/install-baseline.md` — defaults and ranges are present in all intended files.
- `docker compose -f docker-compose.yml config` and the release equivalent — unavailable because Docker CLI is not installed in the verification environment.

## Remaining risks

- Real TMDB latency and 429 behavior have not been exercised with live user
  credentials; verification uses deterministic mocked responses.
- Compose schema expansion was not verified with `docker compose config`
  because Docker CLI is unavailable; the declarations were checked statically.
