from datetime import timezone
from email.utils import parsedate_to_datetime
import logging
import random
from threading import Lock, local
import time
from typing import Callable, Optional

import requests

from app.services.settings import get_tmdb_api_key, get_tmdb_api_requests_per_second


logger = logging.getLogger(__name__)

TMDB_RATE_LIMIT_BURST = 3
TMDB_MAX_RETRIES = 3
TMDB_MAX_RETRY_AFTER_SECONDS = 60.0
TMDB_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class TokenBucketRateLimiter:
    def __init__(
        self,
        rate_per_second: float,
        capacity: int,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ):
        self.rate_per_second = rate_per_second
        self.capacity = float(capacity)
        self._clock = clock
        self._sleeper = sleeper
        self._lock = Lock()
        self._tokens = self.capacity
        self._updated_at = clock()
        self._deferred_until = 0.0

    def acquire(self) -> None:
        while True:
            with self._lock:
                now = self._clock()
                elapsed = max(0.0, now - self._updated_at)
                self._tokens = min(self.capacity, self._tokens + elapsed * self.rate_per_second)
                self._updated_at = now

                deferred_for = max(0.0, self._deferred_until - now)
                if deferred_for:
                    wait_for = deferred_for
                elif self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                else:
                    wait_for = (1.0 - self._tokens) / self.rate_per_second

            self._sleeper(wait_for)

    def defer(self, seconds: float) -> None:
        if seconds <= 0:
            return
        with self._lock:
            self._deferred_until = max(self._deferred_until, self._clock() + seconds)


_shared_rate_limiter = TokenBucketRateLimiter(
    get_tmdb_api_requests_per_second(),
    TMDB_RATE_LIMIT_BURST,
)


class TMDBClient:
    base_url = "https://api.themoviedb.org/3"
    image_base_url = "https://image.tmdb.org/t/p"

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        rate_limiter: Optional[TokenBucketRateLimiter] = None,
        session_factory: Callable[[], requests.Session] = requests.Session,
        sleeper: Callable[[float], None] = time.sleep,
        random_value: Callable[[], float] = random.random,
        wall_clock: Callable[[], float] = time.time,
    ):
        self.api_key = api_key
        self.rate_limiter = rate_limiter or _shared_rate_limiter
        self._session_factory = session_factory
        self._thread_local = local()
        self._sleeper = sleeper
        self._random_value = random_value
        self._wall_clock = wall_clock

    def is_configured(self) -> bool:
        return bool(self._api_key())

    def search_movies(self, query: str, year: Optional[int] = None, language: str = "zh-CN") -> list[dict]:
        self._require_api_key()
        api_key = self._api_key()
        params = {
            "api_key": api_key,
            "query": query,
            "language": language,
            "include_adult": "false",
        }
        if year:
            params["year"] = str(year)

        data = self._get("/search/movie", params=params)
        return data.get("results", [])

    def movie_details(self, tmdb_id: int, language: str = "zh-CN", artwork_language: Optional[str] = None) -> dict:
        self._require_api_key()
        api_key = self._api_key()
        return self._get(
            f"/movie/{tmdb_id}",
            params={
                "api_key": api_key,
                "language": language,
                "append_to_response": "credits,external_ids,images",
                "include_image_language": self._image_languages(language, artwork_language),
            },
        )

    def configuration(self) -> dict:
        self._require_api_key()
        return self._get("/configuration", params={"api_key": self._api_key()})

    def image_url(self, path: Optional[str], size: str = "original") -> Optional[str]:
        if not path:
            return None
        return f"{self.image_base_url}/{size}{path}"

    def _get(self, path: str, params: dict) -> dict:
        for attempt in range(TMDB_MAX_RETRIES + 1):
            self.rate_limiter.acquire()
            try:
                response = self._session().get(
                    f"{self.base_url}{path}",
                    params=params,
                    timeout=15,
                )
            except (requests.Timeout, requests.ConnectionError) as exc:
                if attempt >= TMDB_MAX_RETRIES:
                    error_type = (
                        requests.Timeout
                        if isinstance(exc, requests.Timeout)
                        else requests.ConnectionError
                    )
                    raise error_type("TMDB API connection failed after retries") from None
                delay = self._backoff_delay(attempt)
                logger.warning(
                    "TMDB request retry path=%s reason=%s attempt=%s wait=%.2fs",
                    path,
                    exc.__class__.__name__,
                    attempt + 1,
                    delay,
                )
                self._sleeper(delay)
                continue

            if response.status_code < 400:
                return response.json()

            status_code = response.status_code
            if status_code not in TMDB_RETRYABLE_STATUS_CODES:
                raise self._safe_http_error(status_code, response)

            delay = self._retry_delay(response, attempt)
            if status_code == 429:
                self.rate_limiter.defer(delay)

            if attempt >= TMDB_MAX_RETRIES:
                raise self._safe_http_error(status_code, response)

            logger.warning(
                "TMDB request retry path=%s status=%s attempt=%s wait=%.2fs",
                path,
                status_code,
                attempt + 1,
                delay,
            )
            if status_code != 429:
                self._sleeper(delay)

        raise RuntimeError("TMDB API request failed")

    def _session(self) -> requests.Session:
        session = getattr(self._thread_local, "session", None)
        if session is None:
            session = self._session_factory()
            self._thread_local.session = session
        return session

    def _retry_delay(self, response: requests.Response, attempt: int) -> float:
        if response.status_code == 429:
            retry_after = self._parse_retry_after(response.headers.get("Retry-After"))
            if retry_after is not None:
                return min(retry_after, TMDB_MAX_RETRY_AFTER_SECONDS)
        return self._backoff_delay(attempt)

    def _parse_retry_after(self, value: Optional[str]) -> Optional[float]:
        if not value:
            return None
        try:
            return max(0.0, float(value))
        except ValueError:
            pass
        try:
            retry_at = parsedate_to_datetime(value)
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=timezone.utc)
            return max(0.0, retry_at.timestamp() - self._wall_clock())
        except (TypeError, ValueError, OverflowError):
            return None

    def _backoff_delay(self, attempt: int) -> float:
        return min(2**attempt, 4) + self._random_value() * 0.25

    def _safe_http_error(self, status_code: int, response: requests.Response) -> requests.HTTPError:
        return requests.HTTPError(
            f"TMDB API request failed with status {status_code}",
            response=response,
        )

    def _api_key(self) -> Optional[str]:
        return self.api_key or get_tmdb_api_key()

    def _require_api_key(self):
        if not self._api_key():
            raise RuntimeError("TMDB_API_KEY is not configured")

    def _image_languages(self, language: str, artwork_language: Optional[str] = None) -> str:
        lang = (language or "zh-CN").split("-")[0]
        fallback = "en" if lang != "en" else "zh"
        if artwork_language == "none":
            preferred = "null"
        elif artwork_language in {"zh", "en"}:
            preferred = artwork_language
        else:
            preferred = lang
        languages = [preferred, "null", fallback, lang]
        return ",".join(dict.fromkeys(languages))
