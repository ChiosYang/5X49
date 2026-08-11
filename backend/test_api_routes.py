import unittest
from unittest.mock import patch

from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.main import app


EXPECTED_ROUTES = {
    ("GET", "/health"),
    ("GET", "/"),
    ("GET", "/analyze/{movie_name}"),
    ("GET", "/library"),
    ("GET", "/watch-history"),
    ("GET", "/jobs"),
    ("GET", "/jobs/{job_id}"),
    ("POST", "/jobs/{job_id}/cancel"),
    ("POST", "/jobs/{job_id}/retry"),
    ("DELETE", "/jobs/{job_id}"),
    ("POST", "/library/external-scores/refresh"),
    ("GET", "/library/external-scores/status"),
    ("GET", "/metadata/search"),
    ("GET", "/metadata/movie/{tmdb_id}"),
    ("GET", "/library/events"),
    ("GET", "/library/root-videos"),
    ("GET", "/library/audit-events"),
    ("GET", "/library/{movie_id}/audit-events"),
    ("GET", "/library/user-states"),
    ("GET", "/library/{movie_id}/user-state"),
    ("PUT", "/library/{movie_id}/user-state"),
    ("GET", "/library/{movie_id}/timeline/state"),
    ("GET", "/library/{movie_id}/timeline/restore-preview"),
    ("POST", "/library/{movie_id}/timeline/restore"),
    ("GET", "/library/operations/dry-run"),
    ("POST", "/library/operations/restore"),
    ("POST", "/library/projections/movie/rebuild"),
    ("POST", "/library/events/backfill/movie-discovered"),
    ("POST", "/library/events/backfill/movie-replay"),
    ("POST", "/library/events/dry-run/nfo-signatures"),
    ("GET", "/library/{movie_id}"),
    ("POST", "/library/{movie_id}/external-scores/refresh"),
    ("POST", "/library/seed"),
    ("POST", "/library/scan"),
    ("POST", "/library/reconcile"),
    ("POST", "/library/scan-folder"),
    ("POST", "/library/{movie_id}/refresh"),
    ("GET", "/library/{movie_id}/artwork"),
    ("PUT", "/library/{movie_id}/artwork"),
    ("POST", "/library/{movie_id}/scrape"),
    ("POST", "/library/{movie_id}/ignore"),
    ("POST", "/library/{movie_id}/scrape/confirm"),
    ("POST", "/library/scrape"),
    ("GET", "/library/scrape/status"),
    ("POST", "/library/organize-root"),
    ("POST", "/library/organize-root/confirm"),
    ("GET", "/library/organize/status"),
    ("GET", "/library/sync/status"),
    ("POST", "/library/analyze/{movie_id}"),
    ("DELETE", "/library"),
    ("DELETE", "/library/data"),
    ("DELETE", "/library/missing"),
    ("GET", "/settings"),
    ("GET", "/settings/model"),
    ("PUT", "/settings/model"),
    ("GET", "/settings/media-dir"),
    ("PUT", "/settings/media-dir"),
    ("GET", "/settings/language"),
    ("PUT", "/settings/language"),
    ("GET", "/settings/artwork-language"),
    ("PUT", "/settings/artwork-language"),
    ("GET", "/settings/library-watch"),
    ("PUT", "/settings/library-watch"),
    ("GET", "/settings/auto-organize-root"),
    ("PUT", "/settings/auto-organize-root"),
    ("GET", "/settings/scrape-confirmation"),
    ("PUT", "/settings/scrape-confirmation"),
    ("GET", "/settings/tmdb"),
    ("PUT", "/settings/tmdb"),
    ("POST", "/settings/tmdb/test"),
    ("GET", "/settings/base-url"),
    ("PUT", "/settings/base-url"),
    ("POST", "/settings/models/refresh"),
    ("GET", "/settings/test-api-key"),
    ("GET", "/sys/list-dirs"),
    ("POST", "/sys/scan-library"),
    ("GET", "/api/agents/clean-inbox"),
}


class ApiRouteContractTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_public_route_contract_is_complete_and_unique(self):
        routes = [route for route in app.routes if isinstance(route, APIRoute)]
        actual = {
            (method, route.path)
            for route in routes
            for method in route.methods or set()
        }

        self.assertEqual(actual, EXPECTED_ROUTES)
        self.assertEqual(len(routes), len(EXPECTED_ROUTES))

    def test_static_library_routes_precede_movie_detail_route(self):
        get_paths = [
            route.path
            for route in app.routes
            if isinstance(route, APIRoute) and "GET" in (route.methods or set())
        ]
        detail_index = get_paths.index("/library/{movie_id}")

        for static_path in (
            "/library/events",
            "/library/root-videos",
            "/library/audit-events",
            "/library/user-states",
        ):
            self.assertLess(get_paths.index(static_path), detail_index)

    def test_health_endpoint_still_responds(self):
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "healthy"})

    def test_query_validation_still_rejects_invalid_job_limit(self):
        response = self.client.get("/jobs?limit=0")

        self.assertEqual(response.status_code, 422)

    def test_missing_movie_still_returns_not_found(self):
        with patch("app.api.library.library_manager.get_movie", return_value=None):
            response = self.client.get("/library/local_missing")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "Movie not found"})


if __name__ == "__main__":
    unittest.main()
