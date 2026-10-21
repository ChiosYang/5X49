"""Field-scoped autosave writes against an owned SQLite DB; no provider transport."""
import os
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlmodel import Session, create_engine, select
from app import database
from app.database import configure_sqlite_engine
from app.main import app
from app.models import Setting
from app.services import settings


class SettingsAutosaveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.engine = create_engine(f'sqlite:///{self.root / "settings.db"}', connect_args={"check_same_thread": False})
        configure_sqlite_engine(self.engine)
        Setting.__table__.create(self.engine)
        self.addCleanup(self.engine.dispose)
        for guard in (patch.object(database, 'engine', self.engine),
                      patch.dict(os.environ, {'OPENROUTER_API_KEY': 'synthetic-never-sent', 'WATCH_LIBRARY': 'false'}, clear=True)):
            guard.start(); self.addCleanup(guard.stop)
        guard = patch.object(settings.requests, 'get', side_effect=AssertionError('No provider request allowed'))
        self.network = guard.start(); self.addCleanup(guard.stop)
        self.initial = {'base_url': 'https://old.invalid/v1', 'model_name': 'old-model', 'tmdb_api_key': 'old-test-key',
                        'media_dirs': [], 'media_dir': '', 'video_health_config': {'paused': True}, 'unrelated': {'keep': 1}}
        with Session(self.engine) as session:
            for key, value in self.initial.items(): session.add(Setting(key=key, value=value))
            session.commit()

    def saved(self):
        with Session(self.engine) as session:
            return {row.key: row.value for row in session.exec(select(Setting)).all()}

    def test_base_url_route_does_not_load_models_or_rewrite_other_rows(self):
        with patch.object(settings, 'get_cached_models', return_value=None), \
             patch.object(settings, 'get_available_models', side_effect=AssertionError('No model refresh')) as models:
            client = TestClient(app)
            self.addCleanup(client.close)
            response = client.put('/settings/base-url', params={'base_url': 'https://new.invalid/v1'})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(client.get('/settings/base-url').json(), {'base_url': 'https://new.invalid/v1'})
            models.assert_not_called()
        self.assertEqual(self.saved(), {**self.initial, 'base_url': 'https://new.invalid/v1'})
        self.network.assert_not_called()

    def test_concurrent_preference_writers_preserve_each_others_fields(self):
        root = str(self.root / 'media')
        actions = [lambda: settings.set_base_url('https://latest.invalid/v1'), lambda: settings.set_current_model('new-model'),
                   lambda: settings.set_tmdb_api_key('new-test-key'), lambda: settings.set_media_dirs([root]),
                   lambda: settings.set_language('en'), lambda: settings.set_watch_library(True)]
        barrier = threading.Barrier(len(actions))
        def run(action):
            barrier.wait(timeout=5)
            return action()
        with patch.object(settings, 'load_settings', side_effect=AssertionError('No stale snapshot read')):
            with ThreadPoolExecutor(max_workers=len(actions)) as pool:
                self.assertTrue(all(pool.map(run, actions)))
        self.assertEqual(self.saved(), {**self.initial, 'base_url': 'https://latest.invalid/v1', 'model_name': 'new-model',
            'tmdb_api_key': 'new-test-key', 'media_dirs': [root], 'media_dir': root, 'language': 'en', 'watch_library': True})
        self.network.assert_not_called()

    def test_other_setting_controls_and_key_removal_are_field_scoped(self):
        with patch.object(settings, 'load_settings', side_effect=AssertionError('No stale snapshot read')):
            self.assertTrue(settings.set_auto_organize_root_videos(True))
            self.assertTrue(settings.set_scrape_require_confirmation(True))
            self.assertTrue(settings.set_artwork_language('en'))
            self.assertTrue(settings.set_tmdb_api_key(''))
        expected = {**self.initial, 'auto_organize_root_videos': True, 'scrape_require_confirmation': True, 'artwork_language': 'en'}
        expected.pop('tmdb_api_key')
        self.assertEqual(self.saved(), expected)
        self.network.assert_not_called()

    def test_failed_write_returns_failure_without_changing_any_row(self):
        with patch.object(settings, 'Session', side_effect=RuntimeError('owned test failure')):
            self.assertFalse(settings.set_base_url('https://uncommitted.invalid/v1'))
        self.assertEqual(self.saved(), self.initial)
        self.network.assert_not_called()


if __name__ == '__main__': unittest.main()
