from threading import Lock, Thread
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from app.jobs import actors
from app.jobs.runtime import JobCancelled
from app.services.metadata.models import ScrapeOptions
from app.services.metadata.scraper import MetadataScraper


def movies(count: int) -> list[dict]:
    return [{"id": f"movie-{index}"} for index in range(count)]


class FakeJobContext:
    def __init__(self, cancel_after_processed: int | None = None):
        self.cancel_after_processed = cancel_after_processed
        self.cancelled = False
        self.progress_updates = []

    def progress(self, **progress):
        self.progress_updates.append(progress)
        current = progress.get("current")
        if self.cancel_after_processed is not None and current is not None:
            if current >= self.cancel_after_processed:
                self.cancelled = True

    def is_cancel_requested(self):
        return self.cancelled

    def raise_if_cancelled(self):
        if self.cancelled:
            raise JobCancelled("Job cancelled")


class MetadataBatchConcurrencyTests(unittest.TestCase):
    def _batch_patches(self, library_movies, scrape_side_effect, concurrency=3):
        return (
            patch.object(actors.library_manager, "get_movies", return_value=library_movies),
            patch.object(actors.metadata_scraper, "_in_scope", return_value=True),
            patch.object(actors.metadata_scraper, "scrape_movie", side_effect=scrape_side_effect),
            patch.object(actors.metadata_scraper, "_set_status"),
            patch.object(actors.library_event_bus, "publish_library_changed"),
            patch.object(actors, "get_tmdb_scrape_concurrency", return_value=concurrency),
        )

    def test_batch_runs_out_of_order_with_bounded_concurrency_and_correct_counts(self):
        active = 0
        maximum_active = 0
        active_lock = Lock()
        statuses = {
            "movie-0": "success",
            "movie-1": "needs_review",
            "movie-2": "failed",
            "movie-3": "skipped",
            "movie-4": "success",
            "movie-5": "success",
        }

        def scrape(movie_id, _options):
            nonlocal active, maximum_active
            with active_lock:
                active += 1
                maximum_active = max(maximum_active, active)
            try:
                time.sleep(0.01 * (6 - int(movie_id.split("-")[1])))
                return SimpleNamespace(status=statuses[movie_id])
            finally:
                with active_lock:
                    active -= 1

        patches = self._batch_patches(movies(6), scrape)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            ctx = FakeJobContext()
            result = actors.scrape_library({}, ctx)

        self.assertGreater(maximum_active, 1)
        self.assertLessEqual(maximum_active, 3)
        self.assertEqual(
            result,
            {
                "processed": 6,
                "succeeded": 3,
                "needs_review": 1,
                "failed": 1,
                "skipped": 1,
            },
        )
        currents = [update["current"] for update in ctx.progress_updates if update.get("current")]
        self.assertEqual(currents, [1, 2, 3, 4, 5, 6])

    def test_worker_exception_only_fails_that_movie(self):
        def scrape(movie_id, _options):
            if movie_id == "movie-1":
                raise RuntimeError("worker failed")
            return SimpleNamespace(status="success")

        patches = self._batch_patches(movies(3), scrape)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            result = actors.scrape_library({}, FakeJobContext())

        self.assertEqual(result["processed"], 3)
        self.assertEqual(result["succeeded"], 2)
        self.assertEqual(result["failed"], 1)

    def test_three_workers_finish_simulated_network_work_faster_than_serial(self):
        def scrape(_movie_id, _options):
            time.sleep(0.04)
            return SimpleNamespace(status="success")

        def run_batch(concurrency):
            patches = self._batch_patches(movies(6), scrape, concurrency=concurrency)
            started_at = time.monotonic()
            with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
                actors.scrape_library({}, FakeJobContext())
            return time.monotonic() - started_at

        serial_duration = run_batch(1)
        concurrent_duration = run_batch(3)

        self.assertLess(concurrent_duration, serial_duration * 0.75)

    def test_cancellation_stops_submitting_new_movies_and_waits_for_running_work(self):
        started = []
        started_lock = Lock()

        def scrape(movie_id, _options):
            with started_lock:
                started.append(movie_id)
            time.sleep(0.01 if movie_id == "movie-0" else 0.1)
            return SimpleNamespace(status="success")

        patches = self._batch_patches(movies(6), scrape, concurrency=2)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            with self.assertRaises(JobCancelled):
                actors.scrape_library({}, FakeJobContext(cancel_after_processed=1))

        self.assertLessEqual(len(started), 2)


class MetadataMovieLockTests(unittest.TestCase):
    def test_same_movie_is_serialized_and_lock_entry_is_cleaned_up(self):
        scraper = MetadataScraper()
        active = 0
        maximum_active = 0
        active_lock = Lock()

        def scrape_unlocked(*_args, **_kwargs):
            nonlocal active, maximum_active
            with active_lock:
                active += 1
                maximum_active = max(maximum_active, active)
            try:
                time.sleep(0.03)
                return SimpleNamespace(status="success")
            finally:
                with active_lock:
                    active -= 1

        with patch.object(scraper, "_scrape_movie_unlocked", side_effect=scrape_unlocked):
            threads = [
                Thread(target=scraper.scrape_movie, args=("same-movie", ScrapeOptions()))
                for _ in range(2)
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

        self.assertEqual(maximum_active, 1)
        self.assertEqual(scraper._movie_locks, {})


if __name__ == "__main__":
    unittest.main()
