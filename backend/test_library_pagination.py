import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlmodel import Session, delete

from app.main import app
from app.canonical_models import ProjectionState
from app.services.library import library_manager
from app.services.projections import ProjectionUnavailable
from app.services.user_state import film_profile_state_manager
import test_projections as fixtures


class LibraryPaginationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ProjectionTests()
        self.fixture.setUp()
        self.engine = self.fixture.engine
        observations = [self.fixture._observation(f"Film {index:03}") for index in range(17)]
        for index, item in enumerate(observations):
            item["runtime"] = None if index == 16 else 80 + index
            item["scrape_status"] = "needs_review" if index == 16 else "matched"
        library_manager.add_observations(observations)

    def tearDown(self): self.fixture.tearDown()

    def test_pages_are_bounded_complete_stable_and_outdated_offset_is_clamped(self):
        ids = []
        statements = []
        def capture(_conn, _cursor, statement, *_args): statements.append(statement)
        event.listen(self.engine,"before_cursor_execute",capture)
        try:
            for offset in (0,5,10,15):
                page = library_manager.film_page(limit=5,offset=offset)
                self.assertEqual((page["total"],page["library_total"],page["metadata_reviews"]),(17,17,1))
                self.assertLessEqual(len(page["items"]),5)
                ids.extend(item["id"] for item in page["items"])
        finally: event.remove(self.engine,"before_cursor_execute",capture)
        self.assertEqual(len(set(ids)),17)
        payload_reads = [sql for sql in statements if sql.startswith("SELECT library_film_read_model.film_id")]
        self.assertTrue(payload_reads)
        self.assertTrue(all("LIMIT" in sql for sql in payload_reads))
        self.assertEqual(library_manager.film_page(limit=5,offset=999)["offset"],15)

    def test_search_filter_and_review_counts_are_global_not_current_page(self):
        films = library_manager.film_page()["items"]
        film_profile_state_manager.upsert(films[2]["id"],favorite=True,watched=True,fields_set={"favorite","watched"})
        result = library_manager.film_page(query="FILM",filter="favorite",limit=1)
        self.assertEqual(result["total"],1)
        self.assertEqual(result["items"][0]["id"],films[2]["id"])
        self.assertEqual(library_manager.film_page(filter="watched")["total"],1)
        self.assertEqual(library_manager.film_page(filter="unwatched")["total"],16)
        self.assertEqual(library_manager.film_page(metadata_status="needs_review")["total"],1)
        self.assertEqual(library_manager.film_page(query="%_none")["total"],0)
        self.assertEqual(library_manager.film_page(query="absent")["offset"],0)

    def test_duration_sort_keeps_unknown_last_in_both_directions(self):
        for direction in ("asc","desc"):
            result = library_manager.film_page(sort="duration",direction=direction)
            self.assertEqual(result["items"][-1]["title"],"Film 016")
            durations = [item["runtime_minutes"] for item in result["items"][:-1]]
            self.assertEqual(durations,sorted(durations,reverse=direction=="desc"))

    def test_unavailable_projection_does_not_fall_back_to_canonical_reads(self):
        with Session(self.engine) as session:
            session.exec(delete(ProjectionState).where(ProjectionState.name=="library"));session.commit()
        with self.assertRaises(ProjectionUnavailable): library_manager.film_page()

    def test_api_rejects_unbounded_and_invalid_query_parameters(self):
        client = TestClient(app)
        with patch("app.api.library.library_manager.film_page") as page:
            for query in ("limit=101","offset=-1","offset=1000001","filter=ignored","sort=invalid","direction=bad"):
                self.assertEqual(client.get("/library/films/page?"+query).status_code,422)
            page.assert_not_called()
