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
    elif action == 'viewing_review_fixture':
        from app.services.library import library_manager
        from app.services.user_state import film_profile_state_manager
        from app.services.viewings import viewing_manager
        video = root / 'Synthetic Rewatch.mkv'
        video.write_bytes(b'viewing-review-synthetic-video')
        library_manager.add_observations([dict(title='Synthetic Rewatch', folder_name='Synthetic Rewatch',
            media_path=str(video), year=1999, scrape_status='matched')])
        film = next(item for item in library_manager.list_films() if item['title'] == 'Synthetic Rewatch')
        film_profile_state_manager.upsert(film['id'], rating=3, notes='Historical Film note',
            fields_set={'rating', 'notes'})
        rows = [viewing_manager.create(film['id'], date) for date in
            ['2025', '2026-01-02', '2026-01-02T23:30:00+08:00', None]]
        return {'film_id': film['id'], 'viewings': rows}
    elif action == 'library_filter_fixture':
        from app.services.library import library_manager
        from app.services.user_state import film_profile_state_manager
        from app.models import FilmMetadataOverride, FilmExternalScore
        from app.services.viewings import viewing_manager
        from app.database import engine
        from sqlmodel import Session
        observations = []
        entries = [('Orbit Dawn', 1980, 90, None), ('Orbit Echo', 2001, 120, None),
                   ('Orbit Else', 2000, 95, None), ('Orbit Unknown', None, None, None),
                   ('Orbit Measured', 2000, 120, 5401)]
        entries += [(f'Shelf {i:02}', 1980, 80, None) for i in range(42)]
        for title, year, runtime, seconds in entries:
            video = root / (title + '.mkv')
            video.write_bytes(('filter-fixture-' + title).encode())
            observations.append(dict(title=title, folder_name=title, media_path=str(video),
                year=year, runtime=runtime, video_duration=seconds, scrape_status='matched'))
        library_manager.add_observations(observations)
        films = {film['title']: film['id'] for film in library_manager.list_films()}
        for title in ('Orbit Dawn', 'Orbit Echo', 'Orbit Else'):
            film_profile_state_manager.upsert(films[title], favorite=True, watched=title != 'Orbit Else',
                rating={'Orbit Dawn': 3, 'Orbit Echo': 5, 'Orbit Else': 4}[title],
                fields_set={'favorite', 'watched', 'rating'})
        with Session(engine) as session:
            session.add(FilmMetadataOverride(film_id=films['Orbit Dawn'], values={'year': 1999}, revision=1))
            session.add(FilmExternalScore(film_id=films['Orbit Unknown'], source='tmdb', label='TMDB',
                kind='rating', value=9.0, scale=10.0, fetched_at='2026-10-12T00:00:00Z'))
            session.commit()
        viewing_manager.create(films['Orbit Unknown'], '2026-10-12', rating=5,
            idempotency_key='filter-viewing-0001')
        return films
    elif action == 'library_filter_care_fixture':
        from app.services.library import library_manager
        from app.services.user_state import film_profile_state_manager
        if payload.get('mode') == 'offline':
            return {'missing': library_manager.mark_path_missing(str(root / 'Orbit Unknown.mkv'))}
        for film in library_manager.list_films():
            if film['title'].startswith('Shelf '):
                film_profile_state_manager.upsert(film['id'], favorite=True, watched=True, rating=3,
                    fields_set={'favorite', 'watched', 'rating'})
                library_manager.update_film_observation(film['id'], {
                    'scrape_status': 'matched' if payload.get('mode') == 'empty' else 'needs_review'})
        return {'updated': True}
    elif action == 'manual_metadata_fixture':
        from app.services.library_sync import library_sync_service
        from app.services.canonical_runtime import canonical_runtime_writer
        from app.database import engine
        from sqlmodel import Session
        folder = root / 'Manual metadata fixture'
        folder.mkdir(exist_ok=True)
        (folder / 'movie.mkv').write_bytes(b'manual-metadata-synthetic-video')
        (folder / 'movie.nfo').write_text('<movie><title>Source Film</title><originaltitle>Source Original</originaltitle>'
            '<year>1999</year><genre>Drama</genre><plot>Automatic source synopsis.</plot><uniqueid type="tmdb">900101</uniqueid></movie>', encoding='utf-8')
        film = library_sync_service.scan_folder(folder)
        with Session(engine) as session:
            canonical_runtime_writer.sync_user_state(session, film['id'], rating=4, notes='Synthetic retained note',
                favorite=True, watched=True, fields_set={'rating', 'notes', 'favorite', 'watched'})
            session.commit()
        return {'film_id': film['id']}
    elif action == 'manual_metadata_rescan':
        from app.services.library_sync import library_sync_service
        import hashlib
        folder = root / 'Manual metadata fixture'
        nfo = folder / 'movie.nfo'
        if payload.get('change_source'):
            nfo.write_text('<movie><title>Updated Source Film</title><originaltitle>Updated Original</originaltitle>'
                '<year>2001</year><genre>Drama</genre><plot>Updated automatic synopsis.</plot><uniqueid type="tmdb">900101</uniqueid></movie>', encoding='utf-8')
        film = library_sync_service.scan_folder(folder)
        return {'film': film, 'nfo_digest': hashlib.sha256(nfo.read_bytes()).hexdigest()}
    elif action == 'identity_cleanup':
        # This entrypoint asserts the owned synthetic database/root at startup.
        from app.services.library import library_manager
        from app.models import Film, GraphEntity
        from app.database import engine
        from sqlmodel import Session, update
        # Previous matching tests create merged aliases. Unlink their synthetic
        # self-references before teardown: SQLite RESTRICT otherwise makes the
        # bulk delete depend on row deletion order. Production reset
        # behavior is outside this test fixture's scope.
        with Session(engine) as session:
            session.exec(update(Film).values(merged_into_id=None))
            session.exec(update(GraphEntity).values(merged_into_id=None))
            session.commit()
        library_manager.clear_all_data()
    elif action == 'identity_fixtures':
        from sqlmodel import Session, select
        from app.database import engine
        from app.models import IdentityReview
        from app.services.library import library_manager
        from app.services.canonical_runtime import canonical_runtime_writer
        for name in ('Identity original', 'Identity copy'):
            video = root / (name + '.mkv')
            video.write_bytes(b'identity synthetic duplicate')
            library_manager.add_observations([dict(title=name, folder_name=name, media_path=str(video))])
        with Session(engine) as session:
            review = session.exec(select(IdentityReview)).one()
            candidate = review.candidate_snapshot['candidates'][0]
            canonical_runtime_writer.sync_user_state(session, candidate['film_id'], notes='Identity private notes',
                rating=4, favorite=True, watched=True, fields_set={'notes', 'rating', 'favorite', 'watched'})
            session.add(IdentityReview(source_instance_id='local', source_ref='legacy',
                reason_code='identity_conflict', candidate_hash='a'*64, review_key='e2e-legacy'))
            session.commit()
            return dict(review_id=review.id, candidate_item_id=candidate['library_item_id'], film_id=candidate['film_id'])
    elif action == 'identity_candidate_changed':
        from sqlmodel import Session
        from app.database import engine
        from app.models import LibraryItem
        with Session(engine) as session:
            item = session.get(LibraryItem, payload['library_item_id'])
            item.availability_status = 'missing'
            session.add(item)
            session.commit()
    elif action == 'identity_decision_fixtures':
        from sqlmodel import Session, select
        from app.database import engine
        from app.models import IdentityReview
        from app.services.library import library_manager
        from app.services.canonical_runtime import canonical_runtime_writer
        created = {}
        for name, content, identities in [('Decision original', b'decision-keep', {}),
                ('Decision copy', b'decision-keep', {}), ('Reconnect old', b'decision-reconnect', {'tmdb_id': '900099'}),
                ('Reconnect discovery', b'decision-reconnect', {'tmdb_id': '900099'})]:
            video = root / (name + '.mkv')
            video.write_bytes(content)
            created[name] = library_manager.upsert_observation(dict(title=name, folder_name=name,
                media_path=str(video), **identities))
        discovery = created['Reconnect discovery']
        library_manager.record_file_organization(discovery['film_id'], discovery['library_item_id'],
            'synthetic-e2e-manifest', command_id='synthetic-e2e-organization', tmdb_id=900099,
            sidecar_count=0, scrape_status='success')
        with Session(engine) as session:
            canonical_runtime_writer.sync_user_state(session, created['Reconnect old']['film_id'],
                notes='Reconnect retained notes', rating=5, favorite=True, watched=True,
                fields_set={'notes', 'rating', 'favorite', 'watched'})
            session.commit()
            review = session.exec(select(IdentityReview).where(
                IdentityReview.library_item_id == created['Reconnect discovery']['library_item_id'])).one()
            return dict(keep=created['Decision copy'], reconnect=created['Reconnect old'], review_id=review.id)
    elif action == 'identity_old_disappeared':
        (root / 'Reconnect old.mkv').unlink()
    else:
        raise HTTPException(400)
    return {'ok': True}
