import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlmodel import Session, create_engine, select
import app.services.library as library_module
import app.services.event_store as event_module
from app.canonical_models import FilmProfileState, LibraryItem, LibraryItemLocatorHistory, MediaAsset
from app.database import configure_sqlite_engine
from app.migrations.runner import run_migrations
from app.services.library import library_manager, LibraryManager
from app.services.library_sync import library_sync_service
from app.services.scanner import NFOScanner


class LibraryEditionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.folder = self.root / "Blade.Runner.1982"
        self.folder.mkdir()
        path = self.root / "library.db"
        self.engine = create_engine(f"sqlite:///{path}")
        configure_sqlite_engine(self.engine)
        run_migrations(self.engine, path, backup_required=False)
        self.patches = [patch.object(module, "engine", self.engine) for module in (library_module, event_module)]
        for item in self.patches: item.start()
        self.probe = patch("app.services.scanner.video_probe_service.probe", return_value={})
        self.probe.start()

    def tearDown(self):
        self.probe.stop()
        for item in self.patches: item.stop()
        self.engine.dispose()
        self.tmp.cleanup()

    def video(self, name):
        path = self.folder / name
        path.write_bytes(name.encode())
        return path

    def shared_nfo(self):
        (self.folder / "movie.nfo").write_text("<movie><title>Blade Runner</title><year>1982</year><tmdbid>78</tmdbid></movie>")

    def test_same_folder_editions_and_extras_are_distinct_and_repeatable(self):
        self.video("Blade.Runner.1982.Final.Cut.mkv")
        self.video("Blade.Runner.1982.Theatrical.mp4")
        self.video("Blade.Runner.1982.trailer.mkv")
        self.video("Blade.Runner.1982.sample.mp4")
        self.shared_nfo()
        first = library_sync_service.reconcile(str(self.root))
        self.assertEqual((first["scanned"], first["added"]), (2, 2))
        films = library_manager.list_films()
        self.assertEqual(len(films), 1)
        film = library_manager.get_film(films[0]["id"])
        ids = {item["id"] for item in film["editions"]}
        self.assertEqual(len(ids), 2)
        self.assertEqual(len({item["display_name"] for item in film["editions"]}), 2)
        second = library_sync_service.reconcile(str(self.root))
        self.assertEqual((second["added"],second["missing"]), (0,0))
        self.assertEqual({item["id"] for item in library_manager.get_film(film["id"])["editions"]}, ids)

    def test_matching_nfo_does_not_leak_to_other_video(self):
        first = self.video("Crash.1996.mkv")
        self.video("Crash.2005.mkv")
        first.with_suffix(".nfo").write_text("<movie><title>Crash</title><year>1996</year><tmdbid>884</tmdbid></movie>")
        observations = NFOScanner(str(self.root)).scan_folder_editions_observed(self.folder)
        by_file = {item.film["video_file"]:item.film for item in observations}
        self.assertEqual(by_file["Crash.1996.mkv"]["tmdb_id"], "884")
        self.assertNotIn("tmdb_id",by_file["Crash.2005.mkv"])

    def test_retired_locator_does_not_capture_a_new_film_at_reused_path(self):
        video = self.video("Film.mkv")
        self.shared_nfo()
        old = library_sync_service.scan_folder(self.folder)
        item_id = old["primary_item"]["id"]
        with Session(self.engine) as session:
            item = session.get(LibraryItem, item_id)
            item.source_item_key = str(self.folder.resolve())
            asset = session.exec(select(MediaAsset).where(MediaAsset.library_item_id == item_id)
                .where(MediaAsset.asset_kind == "video")).one()
            asset.availability_status = "retired"
            for history in session.exec(select(LibraryItemLocatorHistory)
                .where(LibraryItemLocatorHistory.library_item_id == item_id)).all():
                history.source_item_key = str(self.folder.resolve())
                session.add(history)
            session.add(item); session.add(asset); session.commit()
        video.rename(self.root / "archived-film.mkv")
        video.write_bytes(b"a different film now occupies this historical path")
        (self.folder / "movie.nfo").write_text("<movie><title>Le Samourai</title><year>1967</year><tmdbid>5511</tmdbid></movie>")
        new = library_sync_service.scan_folder(self.folder)
        self.assertNotEqual(new["id"], old["id"])
        self.assertNotEqual(new["primary_item"]["id"], item_id)
        self.assertEqual(new["identities"]["tmdb"], "5511")

    def test_split_parts_are_one_edition_and_noncontiguous_parts_are_separate(self):
        self.video("Film.1982.CD1.mkv"); self.video("Film.1982.CD2.mkv")
        self.shared_nfo()
        film = library_sync_service.scan_folder(self.folder)
        self.assertEqual(len(film["editions"]), 1)
        self.assertEqual(film["primary_item"]["video"]["part_files"], ["Film.1982.CD1.mkv","Film.1982.CD2.mkv"])
        self.video("Other.Disc2.mkv"); self.video("Other.Disc4.mkv")
        self.assertEqual(len(NFOScanner(str(self.root)).scan_folder_editions_observed(self.folder)),3)

    def test_refresh_targets_requested_video_and_legacy_key_keeps_id(self):
        self.video("Blade.Runner.1982.Final.mkv"); self.shared_nfo()
        film = library_sync_service.scan_folder(self.folder)
        old_id = film["primary_item"]["id"]
        with Session(self.engine) as session:
            old = session.get(LibraryItem, old_id)
            old.source_item_key = str(self.folder.resolve())
            old.scraped_at = "2026-10-01T12:00:00Z"
            old.match_confidence = 97
            session.add(old); session.commit()
        self.video("Blade.Runner.1982.Theatrical.mkv")
        result = library_sync_service.reconcile(str(self.root))
        self.assertEqual(result["added"],1)
        film = library_manager.get_film(film["id"])
        self.assertIn(old_id,{item["id"] for item in film["editions"]})
        other = next(item for item in film["editions"] if item["id"] != old_id)
        library_sync_service.refresh_item(other["id"])
        refreshed = library_manager.get_film(film["id"])
        self.assertEqual(next(item for item in refreshed["editions"] if item["id"] == other["id"])["video"]["file_name"],"Blade.Runner.1982.Theatrical.mkv")
        original = next(item for item in refreshed["editions"] if item["id"] == old_id)
        self.assertEqual((original["metadata"]["scraped_at"],original["metadata"]["match_confidence"]),("2026-10-01T12:00:00Z",97))

    def test_default_is_stable_and_explicit_selection_persists_with_fallback(self):
        self.video("Blade.Runner.1982.Final.mkv"); self.video("Blade.Runner.1982.Theatrical.mkv"); self.shared_nfo()
        film = library_sync_service.scan_folder(self.folder)
        first = film["primary_item"]["id"]
        second = next(item["id"] for item in film["editions"] if item["id"] != first)
        with Session(self.engine) as session:
            item = session.get(LibraryItem,second); item.last_seen_at = "2099-01-01"; session.add(item); session.commit()
        self.assertEqual(library_manager.get_film(film["id"])["primary_item"]["id"],first)
        library_manager.select_primary_item(film["id"],second)
        library_sync_service.reconcile(str(self.root))
        self.assertEqual(LibraryManager().get_film(film["id"])["primary_item"]["id"],second)
        library_manager.ignore_item(second)
        self.assertEqual(library_manager.get_film(film["id"])["primary_item"]["id"],first)
        with self.assertRaises(ValueError): library_manager.select_primary_item(film["id"],second)
        with self.assertRaises(LookupError): library_manager.select_primary_item("film_"+"f"*32,first)
        with Session(self.engine) as session:
            self.assertEqual(session.exec(select(FilmProfileState)).one().primary_item_id,second)

    def test_explicit_available_nfo_only_preference_is_respected(self):
        self.video("Blade.Runner.1982.mkv"); self.shared_nfo()
        film=library_sync_service.scan_folder(self.folder)
        library_manager.add_observations([{"title":"Blade Runner","tmdb_id":"78",
            "folder_path":str(self.root/"nfo-only"),"library_status":"available"}])
        detail=library_manager.get_film(film["id"])
        nfo=next(item for item in detail["editions"] if not item["video"])
        selected=library_manager.select_primary_item(film["id"],nfo["id"])
        self.assertEqual(selected["primary_item"]["id"],nfo["id"])
