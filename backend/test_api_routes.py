import unittest
from unittest.mock import patch

from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.main import app
from app.services.projections import ProjectionUnavailable


REMOVED_ROUTES = {
    ("GET", "/library"),
    ("GET", "/watch-history"),
    ("GET", "/library/user-states"),
    ("GET", "/library/{movie_id}"),
    ("POST", "/library/analyze/{movie_id}"),
    ("GET", "/analyze/{movie_name}"),
    ("POST", "/library/projections/movie/rebuild"),
}

CANONICAL_ROUTES = {
    ("GET", "/library/films"),
    ("GET", "/library/films/{film_id}"),
    ("GET", "/films/{film_id}/profile-state"),
    ("PUT", "/films/{film_id}/profile-state"),
    ("GET", "/profile/watch-history"),
    ("POST", "/library/items/{library_item_id}/refresh"),
    ("POST", "/library/items/{library_item_id}/ignore"),
    ("POST", "/films/{film_id}/analysis-runs"),
    ("GET", "/films/{film_id}/analysis"),
    ("GET", "/films/{film_id}/graph"),
    ("GET", "/films/{film_id}/artwork"),
    ("PUT", "/films/{film_id}/artwork"),
    ("POST", "/films/{film_id}/scrape"),
    ("POST", "/films/{film_id}/scrape/confirm"),
    ("POST", "/films/{film_id}/external-scores/refresh"),
    ("GET", "/activity/events"),
    ("GET", "/operations/{snapshot_id}/preview"),
    ("POST", "/operations/{snapshot_id}/restore"),
}


class ApiRouteContractTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_canonical_resource_routes_replace_movie_compatibility_routes(self):
        routes = [route for route in app.routes if isinstance(route, APIRoute)]
        actual = {
            (method, route.path)
            for route in routes
            for method in route.methods or set()
        }
        self.assertTrue(CANONICAL_ROUTES.issubset(actual))
        self.assertTrue(REMOVED_ROUTES.isdisjoint(actual))
        self.assertEqual(len(actual), len(set(actual)))

    def test_health_endpoint_responds(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "healthy"})

    def test_query_validation_rejects_invalid_job_limit(self):
        response = self.client.get("/jobs?limit=0")
        self.assertEqual(response.status_code, 422)

    def test_missing_film_and_item_return_resource_specific_404(self):
        with patch("app.api.library.library_manager.get_film", return_value=None):
            response = self.client.get("/library/films/film_" + "a" * 32)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "Film not found"})

        with patch("app.api.library.library_manager.get_item", return_value=None):
            response = self.client.post("/library/items/lib_" + "b" * 32 + "/refresh")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "Library item not found"})

    def test_invalid_resource_ids_are_rejected(self):
        response = self.client.get("/library/films/not/a/film")
        self.assertEqual(response.status_code, 404)
        response = self.client.get("/library/films/not-a-valid-id")
        self.assertEqual(response.status_code, 400)

    def test_unconfigured_media_root_does_not_break_the_library_page(self):
        with patch(
            "app.api.library.root_video_organizer.list_root_videos",
            side_effect=FileNotFoundError("media root is not configured"),
        ):
            response = self.client.get("/library/root-videos")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_projection_unavailable_has_stable_503_contract(self):
        with patch(
            "app.api.library.library_manager.list_films",
            side_effect=ProjectionUnavailable("library projection is unavailable"),
        ):
            response = self.client.get("/library/films")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"]["code"], "projection_unavailable")

    def test_graph_route_uses_film_resource_contract(self):
        film_id = "film_" + "a" * 32
        with patch(
            "app.api.library.graph_query_service.get_film_graph",
            return_value={"root": {"id": film_id}, "nodes": [], "edges": []},
        ):
            response = self.client.get(f"/films/{film_id}/graph")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["root"]["id"], film_id)


if __name__ == "__main__":
    unittest.main()
