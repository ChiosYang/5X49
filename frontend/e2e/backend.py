"""Test-only process entrypoint; never imported by the production app.

Real routes, SQLite, migrations, scans and writes. Only TMDB transport and explicit
scan/job scheduling controls are substituted. Outbound sockets fail closed.
"""
import os
import socket
import threading
from pathlib import Path

root = Path(os.environ['E2E_ROOT']).resolve()
assert root.name.startswith('5x49-e2e-') and (root / '.owned').is_file()
assert Path(os.environ['SQLITE_DB_PATH']).resolve().is_relative_to(root)
assert Path(os.environ['MEDIA_DIR']).resolve().is_relative_to(root)
_original_connect = socket.socket.connect

def local_connect(sock, address):
    if isinstance(address, tuple) and address[0] not in ('127.0.0.1', '::1'):
        raise RuntimeError('E2E forbids external network access')
    return _original_connect(sock, address)

socket.socket.connect = local_connect
from fastapi import Header, HTTPException
from app.main import app
from app.jobs import job_runtime
from app.services.scanner import NFOScanner
from app.services.metadata.scraper import metadata_scraper
from app.workflows.store import workflow_store
from app.services.operation_manifests import operation_manifest_store

# Deterministic external TMDB transport. Production matcher/confirmation/persistence remain real.
def candidate(tmdb_id=900001):
    return dict(id=tmdb_id, title='E2E Candidate', original_title='E2E Original',
                release_date='1999-01-01', overview='Fixture synopsis for explicit comparison.',
                poster_path=None, backdrop_path=None, popularity=1)
metadata_scraper.tmdb.search_movies = lambda *args, **kwargs: [candidate(), candidate(900002)]
metadata_scraper.tmdb.movie_details = lambda tmdb_id, *args, **kwargs: dict(
    **candidate(tmdb_id), original_language='en', runtime=90, external_ids={},
    genres=[dict(id=18, name='Drama')], production_countries=[dict(iso_3166_1='JP', name='Japan')],
    credits=dict(crew=[], cast=[]))
scan_gate = threading.Event()
scan_gate.set()
original_scan = NFOScanner.scan_observed

def controlled_scan(self, *args, **kwargs):
    if not scan_gate.wait(60):
        raise RuntimeError('E2E scan gate timed out')
    return original_scan(self, *args, **kwargs)
NFOScanner.scan_observed = controlled_scan

@app.post('/__e2e/control', include_in_schema=False)
def control(payload: dict, x_e2e_token: str = Header(default='')):
    if x_e2e_token != os.environ['E2E_TOKEN']:
        raise HTTPException(403)
    action = payload['action']
    if action == 'hold_scan':
        scan_gate.clear()
    elif action == 'release_scan':
        scan_gate.set()
    elif action == 'tasks':
        job_runtime.stop()
        path_ref = operation_manifest_store.create_path_reference(root / 'normal/media', root / 'normal/media')
        return [workflow_store.create('library.reconcile', {'media_root_ref': path_ref},
                dedupe_key=f'e2e-{i}')[0] for i in range(9)]
    elif action == 'resume_tasks':
        job_runtime.start()
    elif action == 'set_title':
        from app.services.library import library_manager
        library_manager.update_film_observation(payload['film_id'], {'title': payload['title'], 'title_cn': None})
    else:
        raise HTTPException(400)
    return {'ok': True}
