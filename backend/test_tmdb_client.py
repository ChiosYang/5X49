import json
import os
from collections import deque
from threading import Lock, Thread
import unittest
from unittest.mock import patch

import requests

from app.services.metadata.tmdb import TMDBClient, TokenBucketRateLimiter
from app.services.settings import (
    get_tmdb_api_requests_per_second,
    get_tmdb_scrape_concurrency,
)


def response(status_code: int, payload: dict | None = None, headers: dict | None = None) -> requests.Response:
    result = requests.Response()
    result.status_code = status_code
    result.headers.update(headers or {})
    result._content = json.dumps(payload or {}).encode("utf-8")
    return result


class SequenceSession:
    def __init__(self, items):
        self.items = deque(items)
        self.calls = []

    def get(self, url, *, params, timeout):
        self.calls.append((url, params, timeout))
        item = self.items.popleft()
        if isinstance(item, Exception):
            raise item
        return item


class RecordingLimiter:
    def __init__(self):
        self.acquires = 0
        self.deferred = []

    def acquire(self):
        self.acquires += 1

    def defer(self, seconds):
        self.deferred.append(seconds)


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class TokenBucketRateLimiterTests(unittest.TestCase):
    def test_allows_three_request_burst_then_refills_at_six_per_second(self):
        clock = FakeClock()
        limiter = TokenBucketRateLimiter(
            6,
            3,
            clock=clock.monotonic,
            sleeper=clock.sleep,
        )

        for _ in range(4):
            limiter.acquire()

        self.assertEqual(len(clock.sleeps), 1)
        self.assertAlmostEqual(clock.sleeps[0], 1 / 6)

    def test_defer_pauses_all_callers_using_the_limiter(self):
        clock = FakeClock()
        limiter = TokenBucketRateLimiter(
            1,
            1,
            clock=clock.monotonic,
            sleeper=clock.sleep,
        )
        limiter.acquire()
        limiter.defer(2)

        limiter.acquire()

        self.assertEqual(clock.sleeps, [2])


class TMDBClientTests(unittest.TestCase):
    def test_reuses_one_session_on_the_same_thread(self):
        session = SequenceSession([response(200), response(200)])
        created = []

        client = TMDBClient(
            "secret-key",
            rate_limiter=RecordingLimiter(),
            session_factory=lambda: created.append(session) or session,
        )
        client.configuration()
        client.configuration()

        self.assertEqual(created, [session])
        self.assertEqual(len(session.calls), 2)

    def test_uses_a_separate_session_per_thread(self):
        created = []
        created_lock = Lock()

        class SuccessSession:
            def get(self, url, *, params, timeout):
                return response(200)

        def session_factory():
            session = SuccessSession()
            with created_lock:
                created.append(session)
            return session

        client = TMDBClient(
            "secret-key",
            rate_limiter=RecordingLimiter(),
            session_factory=session_factory,
        )
        threads = [Thread(target=client.configuration) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(len(created), 2)
        self.assertIsNot(created[0], created[1])

    def test_429_uses_retry_after_and_shared_cooldown(self):
        limiter = RecordingLimiter()
        session = SequenceSession(
            [
                response(429, headers={"Retry-After": "2"}),
                response(200, {"images": {}}),
            ]
        )
        client = TMDBClient(
            "secret-key",
            rate_limiter=limiter,
            session_factory=lambda: session,
            sleeper=lambda _seconds: None,
            random_value=lambda: 0,
        )

        self.assertEqual(client.configuration(), {"images": {}})
        self.assertEqual(limiter.acquires, 2)
        self.assertEqual(limiter.deferred, [2])

    def test_transient_http_errors_retry_three_times_then_raise_safe_error(self):
        session = SequenceSession([response(500) for _ in range(4)])
        sleeps = []
        client = TMDBClient(
            "secret-key",
            rate_limiter=RecordingLimiter(),
            session_factory=lambda: session,
            sleeper=sleeps.append,
            random_value=lambda: 0,
        )

        with self.assertRaises(requests.HTTPError) as raised:
            client.configuration()

        self.assertEqual(sleeps, [1, 2, 4])
        self.assertEqual(len(session.calls), 4)
        self.assertNotIn("secret-key", str(raised.exception))
        self.assertNotIn("api.themoviedb.org", str(raised.exception))

    def test_deterministic_client_error_is_not_retried(self):
        session = SequenceSession([response(401)])
        sleeps = []
        client = TMDBClient(
            "secret-key",
            rate_limiter=RecordingLimiter(),
            session_factory=lambda: session,
            sleeper=sleeps.append,
        )

        with self.assertRaises(requests.HTTPError):
            client.configuration()

        self.assertEqual(len(session.calls), 1)
        self.assertEqual(sleeps, [])

    def test_timeout_retries_without_exposing_request_url(self):
        session = SequenceSession([requests.Timeout("network timeout"), response(200, {"ok": True})])
        sleeps = []
        client = TMDBClient(
            "secret-key",
            rate_limiter=RecordingLimiter(),
            session_factory=lambda: session,
            sleeper=sleeps.append,
            random_value=lambda: 0,
        )

        self.assertEqual(client.configuration(), {"ok": True})
        self.assertEqual(sleeps, [1])
        self.assertEqual(len(session.calls), 2)


class TMDBEnvironmentTests(unittest.TestCase):
    def test_defaults_and_valid_overrides(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(get_tmdb_scrape_concurrency(), 3)
            self.assertEqual(get_tmdb_api_requests_per_second(), 6)

        with patch.dict(
            os.environ,
            {
                "TMDB_SCRAPE_CONCURRENCY": "5",
                "TMDB_API_REQUESTS_PER_SECOND": "12.5",
            },
            clear=True,
        ):
            self.assertEqual(get_tmdb_scrape_concurrency(), 5)
            self.assertEqual(get_tmdb_api_requests_per_second(), 12.5)

    def test_invalid_or_out_of_range_values_use_defaults(self):
        with patch.dict(
            os.environ,
            {
                "TMDB_SCRAPE_CONCURRENCY": "99",
                "TMDB_API_REQUESTS_PER_SECOND": "nan",
            },
            clear=True,
        ):
            self.assertEqual(get_tmdb_scrape_concurrency(), 3)
            self.assertEqual(get_tmdb_api_requests_per_second(), 6)


if __name__ == "__main__":
    unittest.main()
