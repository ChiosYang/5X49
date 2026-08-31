import asyncio
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, call, patch

from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

import app.database as database_module
from app.main import app, lifespan
from app.services.projections import ProjectionUnavailable
from app.services.viewings import ViewingDateError, ViewingNotFound, ViewingReadOnly


REMOVED_ROUTES = {
    ("GET", "/library"),
    ("GET", "/watch-history"),
    ("GET", "/library/user-states"),
    ("GET", "/library/{movie_id}"),
    ("POST", "/library/analyze/{movie_id}"),
    ("GET", "/analyze/{movie_name}"),
    ("POST", "/library/projections/movie/rebuild"),
    ("GET", "/jobs"),
    ("GET", "/jobs/{job_id}"),
    ("POST", "/jobs/{job_id}/cancel"),
    ("POST", "/jobs/{job_id}/retry"),
    ("DELETE", "/jobs/{job_id}"),
}

CANONICAL_ROUTES = {
    ("GET", "/library/films"),
    ("GET", "/library/films/{film_id}"),
    ("GET", "/films/{film_id}/profile-state"),
    ("PUT", "/films/{film_id}/profile-state"),
    ("GET", "/profile/watch-history"),
    ("GET", "/profile/viewings"),
    ("GET", "/films/{film_id}/viewings"),
    ("POST", "/films/{film_id}/viewings"),
    ("PATCH", "/viewings/{viewing_id}"),
    ("DELETE", "/viewings/{viewing_id}"),
    ("POST", "/library/items/{library_item_id}/refresh"),
    ("POST", "/library/items/{library_item_id}/ignore"),
    ("POST", "/films/{film_id}/analysis-runs"),
    ("GET", "/films/{film_id}/analysis"),
    ("GET", "/films/{film_id}/graph"),
    ("GET", "/films/{film_id}/artwork"),
    ("PUT", "/films/{film_id}/artwork"),
    ("POST", "/films/{film_id}/scrape"),
    ("GET", "/films/{film_id}/scrape/candidates"),
    ("POST", "/films/{film_id}/scrape/confirm"),
    ("POST", "/films/{film_id}/external-scores/refresh"),
    ("GET", "/library/organization/candidates"),
    ("POST", "/library/organization/preview"),
    ("POST", "/library/organization/confirm"),
    ("GET", "/activity/events"),
    ("GET", "/operations/{snapshot_id}/preview"),
    ("POST", "/operations/{snapshot_id}/restore"),
    ("GET", "/workflows"),
    ("GET", "/workflows/{workflow_id}"),
    ("POST", "/workflows/{workflow_id}/cancel"),
    ("POST", "/workflows/{workflow_id}/retry"),
}

REMOVED_ROUTES.update({
    ("GET", "/api/agents/clean-inbox"),
    ("POST", "/library/organize-root/confirm"),
})


class ApplicationLifespanTests(unittest.TestCase):
    def test_lifespan_disposes_engine_after_normal_shutdown(self):
        async def exercise():
            shutdown = MagicMock()
            with (
                patch("app.main.create_db_and_tables") as create_database,
                patch("app.main.get_watch_library", return_value=False),
                patch("app.main.job_runtime.start") as start_jobs,
                patch("app.main.job_runtime.stop") as stop_jobs,
                patch("app.main.library_watcher.start") as start_watcher,
                patch("app.main.library_watcher.stop") as stop_watcher,
                patch("app.main.engine.dispose") as dispose_engine,
            ):
                shutdown.attach_mock(stop_watcher, "stop_watcher")
                shutdown.attach_mock(stop_jobs, "stop_jobs")
                shutdown.attach_mock(dispose_engine, "dispose_engine")

                async with lifespan(app):
                    create_database.assert_called_once_with()
                    start_jobs.assert_called_once_with()
                    start_watcher.assert_not_called()

                self.assertEqual(
                    shutdown.mock_calls,
                    [call.stop_watcher(), call.stop_jobs(), call.dispose_engine()],
                )

        asyncio.run(exercise())

    def test_lifespan_disposes_engine_after_exceptional_shutdown(self):
        async def exercise():
            with (
                patch("app.main.create_db_and_tables"),
                patch("app.main.get_watch_library", return_value=True),
                patch("app.main.job_runtime.start"),
                patch("app.main.job_runtime.stop") as stop_jobs,
                patch("app.main.library_watcher.start") as start_watcher,
                patch("app.main.library_watcher.stop") as stop_watcher,
                patch("app.main.engine.dispose") as dispose_engine,
            ):
                with self.assertRaisesRegex(RuntimeError, "lifespan failure"):
                    async with lifespan(app):
                        raise RuntimeError("lifespan failure")

                start_watcher.assert_called_once_with()
                stop_watcher.assert_called_once_with()
                stop_jobs.assert_called_once_with()
                dispose_engine.assert_called_once_with()

        asyncio.run(exercise())

    def test_lifespan_disposes_engine_when_watcher_shutdown_fails(self):
        async def exercise():
            with (
                patch("app.main.create_db_and_tables"),
                patch("app.main.get_watch_library", return_value=False),
                patch("app.main.job_runtime.start"),
                patch("app.main.job_runtime.stop") as stop_jobs,
                patch(
                    "app.main.library_watcher.stop",
                    side_effect=RuntimeError("watcher shutdown failed"),
                ),
                patch("app.main.engine.dispose") as dispose_engine,
            ):
                with self.assertRaisesRegex(RuntimeError, "watcher shutdown failed"):
                    async with lifespan(app):
                        pass

                stop_jobs.assert_called_once_with()
                dispose_engine.assert_called_once_with()

        asyncio.run(exercise())


class ApiRouteContractTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        database_module.engine.dispose()

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

    def test_root_video_compatibility_route_is_deprecated(self):
        route = next(
            route
            for route in app.routes
            if isinstance(route, APIRoute) and route.path == "/library/root-videos"
        )
        self.assertTrue(route.deprecated)

    def test_health_endpoint_responds(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "healthy"})

    def test_query_validation_rejects_invalid_workflow_limit(self):
        response = self.client.get("/workflows?limit=0")
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

        with patch(
            "app.api.metadata.root_video_organizer.list_organization_candidates",
            side_effect=FileNotFoundError("media root is not configured"),
        ):
            response = self.client.get("/library/organization/candidates")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_organization_confirmation_rejects_a_stale_preview(self):
        preview = {
            "source": {"source_path": "Film.mkv"},
            "can_confirm": True,
            "confirmation_token": "fresh-token",
        }
        with patch("app.api.metadata._preview_organization", return_value=preview):
            response = self.client.post(
                "/library/organization/confirm",
                json={
                    "source_path": "Film.mkv",
                    "tmdb_id": 603,
                    "rename_style": "preserve_stem",
                    "confirmation_token": "b" * 64,
                },
            )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json(), {"detail": "Organization preview is stale"})

    def test_media_directory_status_reports_only_path_availability(self):
        with TemporaryDirectory() as media_dir:
            with patch("app.api.settings.get_media_dir", return_value=media_dir):
                response = self.client.get("/settings/media-dir")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"media_dir": media_dir, "exists": True, "readable": True},
        )
        self.assertNotIn("directories", response.json())
        self.assertNotIn("tmdb_api_key", response.json())

    def test_media_directory_status_distinguishes_missing_and_unreadable_paths(self):
        with patch("app.api.settings.get_media_dir", return_value="/definitely/missing/5x49"):
            response = self.client.get("/settings/media-dir")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["exists"], False)
        self.assertEqual(response.json()["readable"], False)

        with TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "movie.mkv"
            file_path.write_text("not a directory", encoding="utf-8")
            with patch("app.api.settings.get_media_dir", return_value=str(file_path)):
                response = self.client.get("/settings/media-dir")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["exists"], True)
        self.assertEqual(response.json()["readable"], False)

        with TemporaryDirectory() as media_dir:
            with (
                patch("app.api.settings.get_media_dir", return_value=media_dir),
                patch("app.api.settings.os.access", return_value=False),
            ):
                response = self.client.get("/settings/media-dir")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["exists"], True)
        self.assertEqual(response.json()["readable"], False)

    def test_media_directory_update_returns_validated_status(self):
        with TemporaryDirectory() as media_dir:
            with patch("app.api.settings.set_media_dir", return_value=True):
                response = self.client.put("/settings/media-dir", params={"media_dir": media_dir})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["media_dir"], str(Path(media_dir).resolve()))
        self.assertEqual(response.json()["exists"], True)
        self.assertEqual(response.json()["readable"], True)
        self.assertNotIn("directories", response.json())
        self.assertNotIn("tmdb_api_key", response.json())

    def test_media_directory_update_rejects_missing_file_and_unreadable_targets(self):
        missing = self.client.put(
            "/settings/media-dir",
            params={"media_dir": "/definitely/missing/5x49"},
        )
        self.assertEqual(missing.status_code, 400)
        self.assertEqual(missing.json(), {"detail": "Media directory does not exist"})

        with TemporaryDirectory() as temp_dir:
            file_path = f"{temp_dir}/movie.mkv"
            with open(file_path, "w", encoding="utf-8") as handle:
                handle.write("not a directory")
            not_directory = self.client.put(
                "/settings/media-dir",
                params={"media_dir": file_path},
            )
        self.assertEqual(not_directory.status_code, 400)
        self.assertEqual(not_directory.json(), {"detail": "Media directory is not readable"})

        with TemporaryDirectory() as media_dir:
            with patch("app.api.settings.os.access", return_value=False):
                unreadable = self.client.put(
                    "/settings/media-dir",
                    params={"media_dir": media_dir},
                )
        self.assertEqual(unreadable.status_code, 400)
        self.assertEqual(unreadable.json(), {"detail": "Media directory is not readable"})

    def test_library_scan_rejects_a_missing_media_directory_with_actionable_detail(self):
        with patch("app.api.library.get_media_dir", return_value="/definitely/missing/5x49"):
            response = self.client.post("/library/scan")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"detail": "Directory not found: /definitely/missing/5x49"})

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

    def test_viewing_routes_validate_resources_dates_and_read_only_sources(self):
        film_id = "film_" + "a" * 32
        viewing_id = "view_" + "b" * 32
        response = self.client.patch("/viewings/not-a-viewing", json={"watched_at": "2026"})
        self.assertEqual(response.status_code, 400)

        with patch(
            "app.api.library.viewing_manager.create",
            side_effect=ViewingDateError("watched_at date is invalid"),
        ):
            response = self.client.post(
                f"/films/{film_id}/viewings",
                json={"watched_at": "2026-02-30"},
            )
        self.assertEqual(response.status_code, 422)

        with patch(
            "app.api.library.viewing_manager.update",
            side_effect=ViewingReadOnly("Viewing source is read-only"),
        ):
            response = self.client.patch(
                f"/viewings/{viewing_id}",
                json={"watched_at": "2026"},
            )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"]["code"], "viewing_read_only")

        with patch(
            "app.api.library.viewing_manager.delete",
            side_effect=ViewingNotFound("Viewing not found"),
        ):
            response = self.client.delete(f"/viewings/{viewing_id}")
        self.assertEqual(response.status_code, 404)

        response = self.client.put(
            f"/films/{film_id}/profile-state",
            json={"watched": True, "watched_at": "2026-02-30"},
        )
        self.assertEqual(response.status_code, 422)

    def test_viewing_pagination_contract_is_bounded(self):
        response = self.client.get("/profile/viewings?limit=201")
        self.assertEqual(response.status_code, 422)
        with patch(
            "app.api.library.viewing_manager.list_profile",
            return_value={
                "items": [],
                "total": 0,
                "limit": 25,
                "offset": 0,
                "next_offset": None,
            },
        ):
            response = self.client.get("/profile/viewings?limit=25&offset=0")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["next_offset"], None)
        response = self.client.get("/profile/viewings?film_id=not-a-film")
        self.assertEqual(response.status_code, 400)

    def test_scrape_candidate_route_maps_resource_and_service_errors(self):
        film_id = "film_" + "a" * 32
        response = self.client.get("/films/not-a-film/scrape/candidates")
        self.assertEqual(response.status_code, 400)

        with patch(
            "app.api.metadata.metadata_scraper.candidates_for_film",
            side_effect=LookupError("Film not found"),
        ):
            response = self.client.get(f"/films/{film_id}/scrape/candidates")
        self.assertEqual(response.status_code, 404)

        with patch(
            "app.api.metadata.metadata_scraper.candidates_for_film",
            side_effect=ValueError("Film does not have an available media edition"),
        ):
            response = self.client.get(f"/films/{film_id}/scrape/candidates")
        self.assertEqual(response.status_code, 409)

        with patch(
            "app.api.metadata.metadata_scraper.candidates_for_film",
            side_effect=RuntimeError("TMDB API key is not configured"),
        ):
            response = self.client.get(f"/films/{film_id}/scrape/candidates")
        self.assertEqual(response.status_code, 503)

        with patch(
            "app.api.metadata.metadata_scraper.candidates_for_film",
            return_value=[],
        ):
            response = self.client.get(f"/films/{film_id}/scrape/candidates")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])


if __name__ == "__main__":
    unittest.main()
