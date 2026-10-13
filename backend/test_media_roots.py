"""Synthetic multi-root coverage, identity retention and revoked-access regressions."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from sqlmodel import Session, create_engine, select
from app import database
from app.main import app
from app.database import configure_sqlite_engine
from app.migrations.runner import run_migrations
from app.models import LibraryItem, FilmMetadataOverride, FilmProfileState, Viewing, Setting
from app.services import library, event_store, settings
from app.services.library_sync import LibrarySyncService
from app.services.scanner import NFOScanner
from app.services.media_roots import (normalize_roots, configured_root, safe_path, root_id,
    explicitly_absent, relative_media_path, directory_status, MediaBoundaryError)
from app.services.operation_manifests import OperationManifestStore
from app.jobs import actors
from app.services.watcher import _RootWatcher, LibraryWatcher


class MediaRootsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.a, self.b = self.root / 'a', self.root / 'b'
        self.a.mkdir(); self.b.mkdir()
        self.engine = create_engine(f'sqlite:///{self.root / "library.db"}')
        configure_sqlite_engine(self.engine)
        run_migrations(self.engine, self.root / 'library.db', backup_required=False)
        for module in (database, library, event_store):
            guard = patch.object(module, 'engine', self.engine)
            guard.start(); self.addCleanup(guard.stop)
        for target, value in [('app.services.settings.get_available_models', []),
                              ('app.services.scanner.video_probe_service.probe', {})]:
            guard = patch(target, return_value=value)
            guard.start(); self.addCleanup(guard.stop)
        settings.set_media_dirs([str(self.a), str(self.b)])
        self.service = LibrarySyncService()
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close(); self.engine.dispose(); self.temp.cleanup()

    def movie(self, root, relative, identity):
        video = root / relative
        video.parent.mkdir(parents=True, exist_ok=True)
        video.write_bytes(f'unique synthetic video {identity} {relative}'.encode())
        video.with_suffix('.nfo').write_text(f'<movie><title>Film {identity}</title><year>2001</year><tmdbid>{identity}</tmdbid></movie>')
        return video

    def items(self):
        with Session(self.engine) as session:
            return {row.id: row.model_dump() for row in session.exec(select(LibraryItem)).all()}

    def test_ordered_configuration_duplicates_legacy_update_and_empty_disable(self):
        settings.set_media_dirs([str(self.a), str(self.a / '.'), str(self.b)])
        self.assertEqual(settings.get_media_dirs(), [str(self.a), str(self.b)])
        new = self.root / 'new'
        settings.set_media_dir(str(new))
        self.assertEqual(settings.get_media_dirs(), [str(new), str(self.b)])
        with self.assertRaises(MediaBoundaryError):
            settings.set_media_dirs([str(self.a), str(self.a / 'nested')])
        settings.set_media_dirs([])
        self.assertEqual(settings.get_media_dir(), '')
        with self.assertRaises(MediaBoundaryError): configured_root(self.a)
        with self.assertRaises(ValueError): actors._media_dir({})

    def test_legacy_setting_and_environment_fallback_survive_restart(self):
        with Session(self.engine) as session:
            for key in ('media_dirs', 'media_dir'):
                row = session.get(Setting, key)
                if row: session.delete(row)
            session.commit()
        with patch.dict(os.environ, {'MEDIA_DIR': str(self.a)}):
            self.assertEqual(settings.get_media_dirs(), [str(self.a)])
        with Session(self.engine) as session:
            session.add(Setting(key='media_dir', value=str(self.b))); session.commit()
        self.assertEqual(settings.get_media_dirs(), [str(self.b)])

    def test_settings_failure_does_not_restore_revoked_environment_root(self):
        settings.set_media_dirs([])
        with patch.dict(os.environ, {'MEDIA_DIR': str(self.a)}), patch.object(settings, 'Session', side_effect=RuntimeError('unavailable')):
            self.assertEqual(settings.get_media_dirs(), [])
            with self.assertRaises(MediaBoundaryError): configured_root(self.a)

    def test_replaced_root_or_ancestor_is_not_served_or_organized(self):
        from app.services.metadata.organizer import RootVideoOrganizer
        video = self.movie(self.a, 'Film.mkv', 120)
        original = Path.is_junction
        for replaced in (self.a, self.root):
            with patch.object(Path, 'is_junction', lambda path: path == replaced or original(path)):
                self.assertEqual(self.client.get(f'/media/_roots/{root_id(self.a)}/Film.mkv').status_code, 404)
                with self.assertRaises(MediaBoundaryError): RootVideoOrganizer().list_root_videos(str(self.a))
        self.assertTrue(video.exists())

    def test_backup_destination_link_is_rejected_before_copy(self):
        from app.services.metadata.scraper import metadata_scraper
        video = self.movie(self.a, 'Film.mkv', 121)
        destination = self.a / '.5x49-backups' / 'command' / 'test-Film.mkv'
        original = Path.is_symlink
        with patch.object(Path, 'is_symlink', lambda path: path == destination or original(path)), patch('shutil.copy2') as copy:
            with self.assertRaises(MediaBoundaryError): metadata_scraper._backup_file(video, 'test', 'command')
            copy.assert_not_called()

    def test_root_movies_keep_distinct_artwork(self):
        for name, identity in [('A', 122), ('B', 123)]:
            self.movie(self.a, name + '.mkv', identity)
            (self.a / (name + '-poster.jpg')).write_bytes(name.encode())
        observations = NFOScanner(str(self.a)).scan_observed()
        urls = [row.film['poster_local'] for row in observations]
        self.assertEqual(len(set(urls)), 2)
        self.assertEqual({self.client.get(url).content for url in urls}, {b'A', b'B'})

    def test_offline_second_root_never_falls_back_to_same_named_first_folder(self):
        from app.services.metadata.scraper import metadata_scraper
        self.movie(self.a, 'Same/Film.mkv', 124)
        absent = self.b / 'Same' / 'Film.mkv'
        self.assertIsNone(metadata_scraper._film_folder({'folder_path': str(absent.parent),
            'folder_name': 'Same', 'media_path': str(absent)}))
        self.assertIsNone(metadata_scraper._film_folder({'folder_name': 'Same', 'media_path': str(absent)}))

    def test_early_interruption_does_not_claim_root_completed(self):
        with patch.object(NFOScanner, 'scan_observed', side_effect=RuntimeError('cancelled early')):
            with self.assertRaises(RuntimeError): self.service.reconcile()
        result = self.service.get_status()['last_result']
        self.assertFalse(result['complete'])
        self.assertEqual([row['state'] for row in result['roots']], ['interrupted', 'not_scanned'])

    def test_nested_root_files_repeat_restart_and_personal_records(self):
        self.movie(self.a, 'AtRoot.mkv', 101)
        nested = self.movie(self.a, 'country/year/Same/Film.mkv', 102)
        self.movie(self.b, 'other/Same/Film.mkv', 103)
        first = self.service.reconcile()
        self.assertEqual((first['scanned'], first['added'], first['missing']), (3, 3, 0))
        before = self.items()
        film_id = next(iter(before.values()))['film_id']
        with Session(self.engine) as session:
            profile_id = next(iter(before.values()))['profile_id']
            session.add(FilmMetadataOverride(film_id=film_id, values={'title': 'Personal title'}, revision=1))
            state = session.get(FilmProfileState, (profile_id, film_id)) or FilmProfileState(profile_id=profile_id, film_id=film_id)
            state.rating=4; state.notes='Film review'; state.favorite=True; session.add(state)
            session.add(Viewing(id='view_'+'1'*32, profile_id=profile_id, film_id=film_id,
                source='diary', watched_at='2026', watched_at_precision='year', rating=5, notes='Viewing review'))
            session.commit()
        second = LibrarySyncService().reconcile()
        self.assertEqual((second['added'], second['missing']), (0, 0))
        self.assertEqual(set(before), set(self.items()))
        with Session(self.engine) as session:
            self.assertEqual(session.get(FilmMetadataOverride, film_id).values['title'], 'Personal title')
            self.assertEqual(session.get(FilmProfileState, (profile_id, film_id)).notes, 'Film review')
            self.assertEqual(session.get(Viewing, 'view_'+'1'*32).notes, 'Viewing review')
        self.assertTrue(nested.is_file())

    def test_complete_absence_is_scoped_and_existing_invalid_nfo_is_not_missing(self):
        old = self.movie(self.a, 'deep/Gone.mkv', 104)
        retained = self.movie(self.b, 'Present.mkv', 105)
        self.service.reconcile()
        old.unlink(); old.with_suffix('.nfo').unlink()
        retained.with_suffix('.nfo').write_text('<broken')
        partial = self.service.reconcile()
        self.assertFalse(partial['complete']); self.assertEqual(partial['missing'], 0)
        self.assertTrue(all(row['availability_status']=='available' for row in self.items().values()))
        retained.with_suffix('.nfo').write_text('<movie><title>Fixed</title><tmdbid>105</tmdbid></movie>')
        complete = self.service.reconcile()
        self.assertTrue(complete['complete']); self.assertEqual(complete['missing'], 1)
        self.assertEqual(self.service.reconcile()['missing'], 0)

    def test_offline_root_and_removed_root_retain_items_and_block_old_work(self):
        self.movie(self.a, 'One.mkv', 106)
        video = self.movie(self.b, 'Two.mkv', 107)
        self.service.reconcile(); before = self.items()
        store = OperationManifestStore(self.root/'manifests')
        reference = store.create_path_reference(self.b, self.b)
        # Synthetic mount disappears, without touching real media.
        video.unlink(); video.with_suffix('.nfo').unlink(); self.b.rmdir()
        result = self.service.reconcile()
        self.assertEqual(result['roots'][1]['state'], 'offline')
        self.assertEqual(result['missing'], 0)
        settings.set_media_dirs([str(self.a)])
        self.assertEqual(self.service.reconcile()['missing'], 0)
        self.assertEqual(set(before), set(self.items()))
        with patch.object(actors, 'operation_manifest_store', store):
            with self.assertRaises(ValueError): actors.scan_folder({'path_ref': reference}, Mock())
            with self.assertRaises(ValueError): actors.reconcile_library({'media_root_ref': reference}, Mock())
        with self.assertRaises(ValueError): actors.reconcile_library({'root_ids':[root_id(self.b)]}, Mock())

    def test_permission_failure_preserves_old_polling_snapshot_and_missing_state(self):
        video = self.movie(self.a, 'nested/Film.mkv', 108)
        self.service.reconcile()
        watcher = _RootWatcher()
        previous = watcher._build_snapshot(self.a)
        scan = os.scandir
        def deny(path):
            if Path(path) == video.parent: raise PermissionError('synthetic permission failure')
            return scan(path)
        with patch('os.scandir', side_effect=deny):
            result = self.service.reconcile()
            self.assertFalse(result['complete']); self.assertEqual(result['missing'], 0)
            with self.assertRaises(PermissionError): watcher._build_snapshot(self.a)
            self.assertFalse(explicitly_absent(video.parent/'missing.mkv', self.a))
        self.assertIn(str(video), previous)
        self.assertTrue(all(row['availability_status']=='available' for row in self.items().values()))

    def test_cancel_and_configuration_change_skip_missing_reconciliation(self):
        old=self.movie(self.a,'Missing.mkv',109); self.service.reconcile(); old.unlink()
        class Cancelled(Exception): pass
        context = Mock()
        def cancel(**values):
            if values.get('stage') == 'reconcile_missing': raise Cancelled()
        context.progress.side_effect=cancel
        with self.assertRaises(Cancelled): self.service.reconcile(ctx=context)
        self.assertTrue(all(row['availability_status']=='available' for row in self.items().values()))
        with patch.object(NFOScanner, 'scan_observed', side_effect=lambda: settings.set_media_dirs([])):
            with self.assertRaises(ValueError): self.service.reconcile()
        self.assertTrue(all(row['availability_status']=='available' for row in self.items().values()))

    def test_root_urls_disambiguate_nested_same_names_and_revoke_immediately(self):
        for root, identity in [(self.a,110),(self.b,111)]:
            video=self.movie(root,'x/Same/Film.mkv',identity)
            (video.parent/'film-poster.jpg').write_bytes(str(identity).encode())
        observations=[NFOScanner(str(root)).scan_observed()[0] for root in (self.a,self.b)]
        urls=[item.film['poster_local'] for item in observations]
        self.assertNotEqual(*urls)
        self.assertEqual(self.client.get(urls[0]).content,b'110')
        self.assertEqual(self.client.get(urls[1]).content,b'111')
        settings.set_media_dirs([str(self.a)])
        self.assertEqual(self.client.get(urls[1]).status_code,404)

    def test_scan_api_refuses_unconfigured_paths_even_when_they_exist(self):
        outside=self.root/'outside'; outside.mkdir()
        for route, params in [('/library/scan', {'media_dir':str(outside)}),
                              ('/library/scan-folder', {'folder_path':str(outside)})]:
            response=self.client.post(route,params=params)
            self.assertEqual(response.status_code,400,response.text)

    def test_both_path_grammars_and_component_boundaries(self):
        for value in ('../secret','/absolute',r'C:\secret',r'C:secret',r'\\host\share',r'folder\..\secret','x:y','%ignored/../secret'):
            with self.subTest(value=value), self.assertRaises(MediaBoundaryError): relative_media_path(value)
        with self.assertRaises(MediaBoundaryError): configured_root(self.root/'a-other'/'Film.mkv')
        with self.assertRaises(MediaBoundaryError): normalize_roots(['relative'])
        self.assertFalse(explicitly_absent(self.a,self.a))

    def test_symlink_escape_cycle_and_file_alias_not_scanned_or_served(self):
        outside=self.root/'outside'; outside.mkdir()
        self.movie(outside,'Secret.mkv',112)
        try:
            (self.a/'escape').symlink_to(outside,target_is_directory=True)
            (self.a/'cycle').symlink_to(self.a,target_is_directory=True)
            (self.a/'alias.mkv').symlink_to(outside/'Secret.mkv')
        except OSError as error: self.skipTest(f'Host cannot create symlinks: {type(error).__name__}')
        scanner=NFOScanner(str(self.a))
        self.assertEqual(scanner.scan_observed(),[])
        self.assertEqual(scanner.skipped_links,3)
        with self.assertRaises(MediaBoundaryError): safe_path(self.a/'escape'/'Secret.mkv',self.a)
        self.assertEqual(self.client.get(f'/media/_roots/{root_id(self.a)}/alias.mkv').status_code,404)

    def test_junction_boundary_is_shared_by_scan_and_watcher(self):
        video=self.movie(self.a,'junction/Film.mkv',113)
        original=Path.is_junction
        with patch.object(Path,'is_junction',lambda path: path==video.parent or original(path)):
            scanner=NFOScanner(str(self.a))
            self.assertEqual(scanner.scan_observed(),[])
            self.assertEqual(_RootWatcher()._build_snapshot(self.a),{})
            with self.assertRaises(MediaBoundaryError): configured_root(video)

    @unittest.skipUnless(os.name == 'nt', 'Windows junction API only')
    def test_native_windows_junction_is_not_traversed(self):
        import _winapi
        outside = self.root / 'outside'
        self.movie(outside, 'Secret.mkv', 125)
        junction = self.a / 'junction'
        _winapi.CreateJunction(str(outside), str(junction))
        try:
            self.assertTrue(junction.is_junction())
            scanner = NFOScanner(str(self.a))
            self.assertEqual(scanner.scan_observed(), [])
            self.assertEqual(scanner.skipped_links, 1)
            self.assertEqual(_RootWatcher()._build_snapshot(self.a), {})
            self.assertEqual(self.client.get(f'/media/_roots/{root_id(self.a)}/junction/Secret.mkv').status_code, 404)
        finally:
            junction.rmdir()  # Remove only this synthetic junction, never its target.
        self.assertTrue((outside / 'Secret.mkv').is_file())

    def test_restart_receipt_retains_results_but_running_becomes_interrupted(self):
        self.movie(self.a,'Film.mkv',114); result=self.service.reconcile()
        self.assertEqual(LibrarySyncService().get_status()['last_result'],result)
        self.service._set_status(state='running')
        self.assertEqual(LibrarySyncService().get_status()['state'],'interrupted')

    def test_watcher_starts_all_roots_including_offline_and_stops_each(self):
        watcher=LibraryWatcher()
        with patch('app.services.watcher._RootWatcher') as child:
            child.return_value.status.return_value={'media_dir':str(self.a),'running':True,'pending':0,'last_event_at':None,'last_error':None}
            watcher.start()
            self.assertEqual(child.call_count,2)
            self.assertEqual(child.return_value.start.call_count,2)
            watcher.stop()
            self.assertEqual(child.return_value.stop.call_count,2)

    def test_pending_watcher_folder_is_not_inspected_after_root_removal(self):
        watcher = _RootWatcher()
        watcher._pending_folders[str(self.b)] = 0
        settings.set_media_dirs([str(self.a)])
        with patch.object(watcher, '_has_recent_video') as inspect, patch.object(watcher, '_enqueue_job') as enqueue:
            watcher._flush_ready_folders()
            inspect.assert_not_called()
            enqueue.assert_not_called()
