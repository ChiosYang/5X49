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
from fastapi.responses import JSONResponse
from app.main import app
from app.jobs import job_runtime
from app.services.scanner import NFOScanner
from app.services.metadata.scraper import metadata_scraper
from app.workflows.store import workflow_store
from app.services.operation_manifests import operation_manifest_store
from app.services import maintenance_backup as backup_module

# Test-only provider transport; even 'configured' cases cannot reach a real model.
import json
from types import SimpleNamespace
from app.services.ask import AskInterpreter
from app.services.discovery_search import discovery_search_service
discovery_ai_enabled = False
discovery_ai_calls = 0
discovery_ai_reply = {"status": "clarify", "plan": None, "confidence": 0.0, "unhandled": []}
discovery_ai_failure = None
discovery_ai_gate = threading.Event()
discovery_ai_gate.set()
discovery_original_names = {}

class DiscoveryClient:
    def __init__(self, **_kwargs):
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))
    def __enter__(self): return self
    def __exit__(self, *_args): pass
    def create(self, **_kwargs):
        global discovery_ai_calls
        discovery_ai_calls += 1
        reply, failure = discovery_ai_reply, discovery_ai_failure
        if not discovery_ai_gate.wait(60): raise RuntimeError('Synthetic provider gate expired')
        if failure == 'timeout':
            import httpx
            from openai import APITimeoutError
            raise APITimeoutError(request=httpx.Request('POST', 'https://synthetic.invalid'))
        if failure: raise RuntimeError('Synthetic provider failure')
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop', message=SimpleNamespace(content=json.dumps(reply)))])

discovery_interpreter = AskInterpreter(client_factory=DiscoveryClient)
discovery_interpreter.configured = lambda: discovery_ai_enabled
discovery_search_service.ask.interpreter = discovery_interpreter

from app.services.video_health import video_health
health_allowed = False
class ControlledHealthLoad:
    def sample(self, decoder_pid=None):
        return {"observable": True, "cpu": 0 if health_allowed else 95, "disk": 0}
video_health.observer = ControlledHealthLoad()

backup_gate = threading.Event()
backup_gate.set()
backup_failure = False
search_unavailable = False

@app.middleware('http')
async def search_failure(request, call_next):
    if search_unavailable and request.url.path == '/library/films/page':
        return JSONResponse({'detail': 'Synthetic search read failure'}, status_code=503)
    return await call_next(request)
original_sanitize_backup = backup_module.sanitize_snapshot

def controlled_sanitize_backup(path):
    global backup_failure
    if not backup_gate.wait(60):
        raise RuntimeError('Synthetic backup gate timed out')
    if backup_failure:
        backup_failure = False
        raise OSError('Synthetic backup storage failure')
    return original_sanitize_backup(path)

backup_module.sanitize_snapshot = controlled_sanitize_backup

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
    global backup_failure
    if x_e2e_token != os.environ['E2E_TOKEN']:
        raise HTTPException(403)
    global health_allowed
    action = payload['action']
    if action == 'discovery_ai':
        global discovery_ai_enabled, discovery_ai_reply, discovery_ai_failure, discovery_ai_calls
        discovery_ai_enabled = bool(payload.get('enabled'))
        discovery_ai_reply = payload.get('reply', {"status":"clarify","plan":None,"confidence":0.0,"unhandled":[]})
        discovery_ai_failure = payload.get('failure')
        if payload.get('reset', True): discovery_ai_calls = 0
        if payload.get('hold'): discovery_ai_gate.clear()
        else: discovery_ai_gate.set()
        return {'calls': discovery_ai_calls, 'enabled': discovery_ai_enabled}
    elif action == 'discovery_ai_stats':
        return {'calls': discovery_ai_calls, 'enabled': discovery_ai_enabled}
    elif action == 'discovery_ambiguity':
        from app.canonical_models import Person
        from app.database import engine
        from sqlmodel import Session, select
        with Session(engine) as session:
            if payload.get('enabled'):
                for person in session.exec(select(Person).order_by(Person.id).limit(2)).all():
                    discovery_original_names[person.id] = (person.canonical_name, person.normalized_name)
                    person.canonical_name = 'Duplicate Person'
                    person.normalized_name = 'duplicate person'
                    session.add(person)
            else:
                for key, names in discovery_original_names.items():
                    person = session.get(Person, key)
                    if person:
                        person.canonical_name, person.normalized_name = names
                        session.add(person)
                discovery_original_names.clear()
            session.commit()
        return {'changed': True}
    if action == 'search_failure':
        global search_unavailable
        search_unavailable = bool(payload['enabled'])
        return {'enabled': search_unavailable}
    if action == 'health_fixture':
        import subprocess, json, shutil
        from app.services.library import library_manager
        from app.services.settings import set_media_dirs
        media = root / 'health-media'; media.mkdir(exist_ok=True)
        normal = media / 'Health normal.mp4'
        subprocess.run([shutil.which('ffmpeg'), '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=144x96:rate=8',
            '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=16000', '-t', '6', '-c:v', 'mpeg4', '-g', '8',
            '-c:a', 'aac', '-movflags', '+faststart', str(normal)], check=True, capture_output=True, timeout=30)
        packets = json.loads(subprocess.run([shutil.which('ffprobe'), '-v', 'error', '-show_packets', '-select_streams', 'v', '-of', 'json', str(normal)],
            check=True, capture_output=True).stdout)['packets']
        packet = next(row for row in packets if float(row.get('pts_time', 0)) > 3 and int(row['size']) > 1000)
        broken = bytearray(normal.read_bytes()); pos, size = int(packet['pos']), int(packet['size'])
        broken[pos:pos+size] = b'\xff' * size
        (media / 'Health corrupt.mp4').write_bytes(broken)
        set_media_dirs([str(media)])
        for index, path in enumerate(media.glob('*.mp4')):
            library_manager.upsert_observation(dict(title=path.stem, folder_name=path.stem,
                media_path=str(path), file_size=path.stat().st_size, file_mtime=path.stat().st_mtime, tmdb_id=str(987900+index)))
        video_health.configure({'enabled': False, 'paused': True, 'stable_seconds': 0, 'idle_seconds': 0})
        return {'root': str(media)}
    elif action == 'health_allow':
        health_allowed = True
        return {'allowed': True}
    elif action == 'health_replace':
        from app.services.library import library_manager
        media = root / 'health-media'; normal = media / 'Health normal.mp4'
        target = media / 'Health corrupt.mp4'
        target.write_bytes(normal.read_bytes() + b'replaced version')
        from app.models import MediaAsset
        from app import database
        from sqlmodel import Session, select
        with Session(database.engine) as session:
            asset = session.exec(select(MediaAsset).where(MediaAsset.locator == str(target))).one()
            asset.file_size = target.stat().st_size; asset.file_mtime = target.stat().st_mtime
            session.add(asset); session.commit()
        return {'changed': True}
    if action == 'matching_fixture':
        from app.services.library import library_manager
        from app.services.settings import set_media_dirs
        name = payload['name']
        set_media_dirs([str(root)])
        target_video = root / f'{name} target.mkv'
        target_video.write_bytes(f'{name} target synthetic media'.encode())
        target = library_manager.upsert_observation(dict(title='E2E Candidate',
            folder_name=f'{name} target', media_path=str(target_video),
            tmdb_id='900001', scrape_status='matched'))
        source_video = root / f'{name} unresolved.mkv'
        source_video.write_bytes(f'{name} source synthetic media'.encode())
        source = library_manager.upsert_observation(dict(title=f'{name} unresolved',
            folder_name=f'{name} unresolved', media_path=str(source_video), scrape_status='needs_review'))
        return {'source_id': source['film_id'], 'target_id': target['film_id']}
    elif action == 'matching_event':
        from app.services.event_bus import library_event_bus
        library_event_bus.publish_library_changed('metadata_scraped', film_id=payload['film_id'])
    elif action == 'multi_root_fixture':
        from PIL import Image
        import shutil
        sample = next((root / 'normal/media').rglob('*.mkv'), None) or next((root / 'normal/media').rglob('*.mp4'))
        roots = [root / 'multi' / name for name in ('a', 'b')]
        for index, (directory, relative) in enumerate([(roots[0], 'Direct.mkv'),
                (roots[0], 'country/year/Same/Film.mkv'), (roots[1], 'other/Same/Film.mkv')]):
            video = directory / relative
            video.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(sample, video)
            with video.open('ab') as handle: handle.write(f'multi-root-{index}'.encode())
            video.with_suffix('.nfo').write_text(f'<movie><title>Multi Root {index}</title><year>2001</year><runtime>90</runtime><tmdbid>{982000+index}</tmdbid></movie>')
            Image.new('RGB', (80, 120), ('red', 'green', 'blue')[index]).save(video.with_name(video.stem + '-poster.jpg'))
        return {'roots': [str(path) for path in roots]}
    elif action == 'multi_root_offline':
        (root / 'multi/b').rename(root / 'multi/parked-b')
    elif action == 'multi_root_online':
        (root / 'multi/parked-b').rename(root / 'multi/b')
    elif action == 'backup_fixture':
        from app.services.library import library_manager
        from app.services.user_state import film_profile_state_manager
        from app.services.viewings import viewing_manager
        from app.models import Setting, FilmMetadataOverride
        from app.database import engine
        from sqlmodel import Session
        video = root / 'Backup Synthetic Film.mkv'
        video.write_bytes(b'backup-synthetic-media')
        film_id = library_manager.upsert_observation(dict(title='Backup Synthetic Film',
            folder_name='Backup Synthetic Film', media_path=str(video), tmdb_id='981111',
            scrape_error='https://example.test?token=E2E-HISTORICAL-TOKEN-CANARY'))['film_id']
        film_profile_state_manager.upsert(film_id, favorite=True, rating=3, notes='Backup Film review', fields_set={'favorite', 'rating', 'notes'})
        viewing_manager.create(film_id, '2025', rating=5, notes='Backup Viewing review', idempotency_key='backup-viewing-00001')
        with Session(engine) as session:
            session.add(Setting(key='tmdb_api_key', value='E2E-CONFIG-CREDENTIAL-CANARY'))
            session.add(FilmMetadataOverride(film_id=film_id, values={'title': 'Backup Manual Title', 'year': None}, revision=1))
            session.commit()
        return {'film_id': film_id}
    elif action == 'hold_backup':
        backup_gate.clear()
    elif action == 'release_backup':
        backup_gate.set()
    elif action == 'fail_backup':
        backup_failure = True
    elif action == 'expire_backup':
        with backup_module.maintenance_backups.state() as db:
            db.execute("UPDATE attempt SET expires_at='2000-01-01T00:00:00+00:00' WHERE artifact_state='available'")
    elif action == 'backup_receipts':
        with backup_module.maintenance_backups.state() as db:
            return {'count': db.execute('SELECT COUNT(*) FROM attempt').fetchone()[0]}
    elif action == 'hold_scan':
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
    elif action == 'explore_sparse_fixture':
        from app.services.library import library_manager
        video = root / 'Explore unknown.mkv'
        video.write_bytes(b'explore fixture without factual metadata')
        library_manager.add_observations([dict(title='Explore Unknown', folder_name='Explore Unknown', media_path=str(video))])
        return {'created': True}
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
        from app.services.settings import set_media_dirs
        from app.services.canonical_runtime import canonical_runtime_writer
        from app.database import engine
        from sqlmodel import Session
        folder = root / 'Manual metadata fixture'
        folder.mkdir(exist_ok=True)
        set_media_dirs([str(folder)])
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
    elif action == 'deep_reset_fixture':
        from app.database import engine
        from app.models import Film, GraphEntity
        from app.services.library import library_manager
        from app.services.library_sync import library_sync_service
        from app.services.settings import set_media_dirs
        from sqlmodel import Session, select
        import shutil
        media = root / 'reset-media'
        set_media_dirs([str(media)])
        sample = next((root / 'normal/media').rglob('*.mkv'), None) or next((root / 'normal/media').rglob('*.mp4'))
        for index, name in enumerate(('A target', 'B alias', 'C alias')):
            folder = media / name
            folder.mkdir(parents=True, exist_ok=True)
            video = folder / 'film.mkv'
            shutil.copyfile(sample, video)
            with video.open('ab') as handle:
                handle.write(f'reset-{index}'.encode())
            nfo = video.with_suffix('.nfo')
            nfo.write_text(f'<movie><title>{name}</title><tmdbid>983001</tmdbid></movie>')
            observation = dict(title=name, folder_name=name, media_path=str(video))
            library_manager.upsert_observation({**observation, **({'tmdb_id': '983001'} if index == 0 else {})})
            if index:
                library_sync_service.scan_folder(folder, media_root=str(media))
        with Session(engine) as session:
            aliases = session.exec(select(Film).where(Film.lifecycle_status == 'merged')).all()
            assert len(aliases) == 2
            assert all(session.get(GraphEntity, film.id).merged_into_id == film.merged_into_id for film in aliases)
        return {'media': str(media), 'aliases': len(aliases)}
    elif action == 'identity_cleanup':
        # This entrypoint asserts the owned synthetic database/root at startup.
        from app.services.library import library_manager
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
