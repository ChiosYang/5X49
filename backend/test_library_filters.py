import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.main import app
from app.models import FilmMetadataOverride, FilmExternalScore
from app.services.viewings import viewing_manager
from app.services.library import library_manager
from app.services.user_state import film_profile_state_manager
import test_projections as fixtures


class LibraryFilterTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ProjectionTests()
        self.fixture.setUp()
        self.engine = self.fixture.engine
        self.observations = []
        for title, year, runtime, seconds in (
            ("Range Alpha", 1999, 90, None),
            ("Range Beta", 2001, 120, None),
            ("Range Measured", 2000, 120, 5401),
            ("Range Unknown", None, None, None),
            ("Range Zero", 2000, 80, 0),
            ("Range Negative", 2000, 0, -1),
        ):
            self.observations.append({**self.fixture._observation(title), "year": year,
                "runtime": runtime, "video_duration": seconds, "scrape_status": "matched"})
        library_manager.add_observations(self.observations)
        self.ids = {film["title"]: film["id"] for film in library_manager.list_films()}
        for name, watched in (("Range Alpha", True), ("Range Beta", False)):
            film_profile_state_manager.upsert(self.ids[name], favorite=True, watched=watched,
                rating=3 if watched else 5, fields_set={"favorite", "watched", "rating"})

    def tearDown(self):
        self.fixture.tearDown()

    def titles(self, **query):
        return [item["title"] for item in library_manager.film_page(**query)["items"]]

    def test_all_conditions_intersect_before_count_pagination_and_sort(self):
        result = library_manager.film_page(query="RANGE", filter="watched", favorite=True,
            duration_min=90, duration_max=120, year_min=1999, year_max=2001,
            rating_min=3, rating_max=4,
            sort="duration", direction="desc", limit=1, offset=100)
        self.assertEqual((result["total"], result["library_total"], result["offset"]), (1, 6, 0))
        self.assertEqual(result["items"][0]["id"], self.ids["Range Alpha"])
        self.assertEqual(self.titles(filter="unwatched", favorite=True), ["Range Beta"])
        self.assertEqual(self.titles(filter="favorite"), ["Range Alpha", "Range Beta"])
        self.assertEqual(self.titles(query="%_"), [])
        self.assertEqual(self.titles(query="absent", duration_min=1), [])

    def test_inclusive_one_sided_ranges_unknowns_and_second_precision(self):
        self.assertEqual(self.titles(duration_min=90, duration_max=90), ["Range Alpha"])
        self.assertEqual(self.titles(duration_min=90, duration_max=91), ["Range Alpha", "Range Measured"])
        self.assertEqual(self.titles(duration_max=80), ["Range Zero"])
        self.assertEqual(self.titles(duration_min=120), ["Range Beta"])
        self.assertEqual(self.titles(year_min=1999, year_max=1999), ["Range Alpha"])
        self.assertEqual(self.titles(year_max=1999), ["Range Alpha"])
        self.assertEqual(self.titles(year_min=2001), ["Range Beta"])
        for direction in ("asc", "desc"):
            titles = self.titles(sort="duration", direction=direction)
            self.assertEqual(set(titles[-2:]), {"Range Negative", "Range Unknown"})
            known = ["Range Zero", "Range Alpha", "Range Measured", "Range Beta"]
            self.assertEqual(titles[:-2], known if direction == "asc" else known[::-1])
        self.assertEqual(len(self.titles()), 6)

    def test_rating_is_only_film_personal_overall_and_never_falls_back(self):
        with Session(self.engine) as session:
            for name in ("Range Alpha", "Range Unknown"):
                session.add(FilmExternalScore(film_id=self.ids[name], source="tmdb", label="TMDB",
                    kind="rating", value=9.0, scale=10.0, fetched_at="2026-10-12T00:00:00Z"))
            session.commit()
        with patch("app.services.viewings.engine", self.engine):
            for name in ("Range Alpha", "Range Unknown"):
                viewing_manager.create(self.ids[name], "2026-10-12", rating=5,
                    idempotency_key="filter-test-" + self.ids[name])
        self.assertEqual(self.titles(rating_min=3, rating_max=3), ["Range Alpha"])
        self.assertEqual(self.titles(rating_min=4), ["Range Beta"])
        self.assertEqual(self.titles(rating_max=3), ["Range Alpha"])
        self.assertEqual(self.titles(rating_min=1, rating_max=5), ["Range Alpha", "Range Beta"])
        self.assertIn("Range Unknown", self.titles())

    def test_effective_manual_year_survives_source_update_and_reads_are_pure(self):
        film_id = self.ids["Range Alpha"]
        with Session(self.engine) as session:
            session.add(FilmMetadataOverride(film_id=film_id, values={"year": 1984}, revision=1))
            session.commit()
        library_manager.upsert_observation({**self.observations[0], "year": 2020})
        with self.engine.connect() as connection:
            before = "\n".join(connection.connection.driver_connection.iterdump())
        self.assertEqual(self.titles(year_min=1984, year_max=1984), ["Range Alpha"])
        self.assertEqual(self.titles(year_min=2020), [])
        with self.engine.connect() as connection:
            self.assertEqual(before, "\n".join(connection.connection.driver_connection.iterdump()))
        with Session(self.engine) as session:
            override = session.get(FilmMetadataOverride, film_id)
            override.values = {"year": None}
            session.add(override)
            session.commit()
        self.assertNotIn("Range Alpha", self.titles(year_min=1870))

    def test_api_validation_and_parameter_forwarding(self):
        client = TestClient(app)
        try:
            with patch("app.api.library.library_manager.film_page") as page:
                for query in ("duration_min=0", "duration_max=10001", "duration_min=NaN",
                              "duration_min=1.5", "year_min=1869", "year_max=2101", "favorite=bad",
                              "duration_min=100&duration_max=90", "year_min=2001&year_max=1999",
                              "rating_min=0", "rating_max=6", "rating_min=1.5", "rating_max=NaN",
                              "rating_min=5&rating_max=4"):
                    self.assertEqual(client.get("/library/films/page?" + query).status_code, 422, query)
                page.assert_not_called()
                page.return_value = {"items": [], "total": 0}
                response = client.get("/library/films/page?q=Range&filter=watched&favorite=true"
                    "&duration_min=90&duration_max=120&year_min=1999&year_max=2001&rating_min=3&rating_max=5&sort=added&direction=desc")
                self.assertEqual(response.status_code, 200)
                page.assert_called_once_with(query="Range", filter="watched", favorite=True,
                    duration_min=90, duration_max=120, year_min=1999, year_max=2001,
                    rating_min=3, rating_max=5,
                    sort="added", direction="desc", metadata_status="all", limit=40, offset=0)
        finally:
            client.close()
