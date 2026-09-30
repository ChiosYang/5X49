"""Process-isolated RC smoke: no credentials, real lifecycle and read-only media."""

import hashlib
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


class RcAcceptanceTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "posix", "POSIX read-only permission acceptance")
    def test_no_key_scan_read_only_media_restart_and_local_queries(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            media = root / "media"
            film = media / "RC Film (1999)"
            film.mkdir(parents=True)
            (film / "movie.nfo").write_text(
                "<movie><title>RC Film</title><year>1999</year>"
                "<genre>Drama</genre><country>Japan</country></movie>", encoding="utf-8",
            )
            (film / "film.mkv").write_bytes(b"isolated video fixture")
            files = list(film.iterdir())
            before = {file.name: hashlib.sha256(file.read_bytes()).hexdigest() for file in files}
            for file in files:
                file.chmod(0o444)
            film.chmod(0o555)
            media.chmod(0o555)
            try:
                if os.access(media, os.W_OK):
                    self.skipTest("Runtime bypasses directory permissions")
                environment = {
                    **os.environ,
                    "PYTHONPATH": str(Path(__file__).resolve().parent),
                    "SQLITE_DB_PATH": str(root / "data" / "library.db"),
                    "MEDIA_DIR": str(media),
                    "OPERATION_MANIFEST_DIR": str(root / "manifests"),
                    "WATCH_LIBRARY": "false",
                    "OPENROUTER_API_KEY": "", "TMDB_API_KEY": "",
                    "PYTHON_DOTENV_DISABLED": "1",
                }
                result = subprocess.run(
                    [sys.executable, "-c", textwrap.dedent("""
                        import time
                        from unittest.mock import patch
                        from fastapi.testclient import TestClient
                        from app.main import app

                        def scan(client):
                            response = client.post('/library/scan')
                            assert response.status_code == 200, response.text
                            workflow_id = response.json()['workflow_id']
                            deadline = time.monotonic() + 20
                            while time.monotonic() < deadline:
                                workflow = client.get('/workflows/' + workflow_id).json()
                                if workflow['status'] in ('succeeded', 'failed', 'cancelled'):
                                    assert workflow['status'] == 'succeeded', workflow
                                    return
                                time.sleep(0.05)
                            raise AssertionError('scan did not finish')

                        with patch('requests.sessions.Session.request', side_effect=AssertionError('unexpected provider request')):
                            with TestClient(app) as client:
                                assert client.get('/health').status_code == 200
                                assert client.get('/settings/media-dir').json()['readable']
                                assert client.get('/ask/status').json()['configured'] is False
                                scan(client)
                                films = client.get('/library/films').json()
                                assert len(films) == 1, films
                                film_id = films[0]['id']
                                scan(client)
                                assert [item['id'] for item in client.get('/library/films').json()] == [film_id]
                                assert client.put('/films/' + film_id + '/profile-state', json={'rating': 4, 'notes': 'RC note'}).status_code == 200
                                response = client.post('/films/' + film_id + '/viewings', json={'watched_at': '2026-09-28'})
                                assert response.status_code == 200, response.text
                                for route in ('/profile/viewings', '/profile/cinema-dna', '/explore'):
                                    assert client.get(route).status_code == 200, route
                                response = client.post('/ask/query', json={'plan': {'decade': 1990}, 'confirmed': True})
                                assert response.status_code == 200, response.text
                                assert response.json()['results']['total'] == 1, response.text
                                from app.projections import main as projections
                                assert projections(['verify']) == 0
                            with TestClient(app) as client:
                                assert [item['id'] for item in client.get('/library/films').json()] == [film_id]
                                state = client.get('/films/' + film_id + '/profile-state').json()
                                assert state['rating'] == 4 and state['notes'] == 'RC note', state
                                assert client.get('/profile/cinema-dna').json()['totals']['watched_films'] == 1
                        print('RC_PROCESS_SMOKE_PASSED')
                    """)],
                    cwd=root, env=environment, text=True, capture_output=True, timeout=60,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("RC_PROCESS_SMOKE_PASSED", result.stdout)
                self.assertEqual({file.name: hashlib.sha256(file.read_bytes()).hexdigest() for file in files}, before)
                self.assertEqual({file.name for file in film.iterdir()}, set(before))
            finally:
                media.chmod(0o755)
                film.chmod(0o755)
                for file in files:
                    file.chmod(0o644)


if __name__ == "__main__":
    unittest.main()
