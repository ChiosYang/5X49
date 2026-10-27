"""Source-to-search regression on synthetic metadata only; network forbidden."""
import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from sqlmodel import Session, select

import test_structured_metadata_runtime as fixture
from app.canonical_models import Film, FilmTitle, GraphEntity, LibraryItem
from app.contracts.discovery_search import DiscoveryQuestion
from app.services import ask as ask_module
from app.services.ask import AskService
from app.services.discovery_search import DiscoverySearchService
from app.services.metadata.tmdb import TMDBClient
from app.services.projections import projection_coordinator, projection_reader
from app.services.scanner import NFOScanner
from app.services.search_local import LocalSearch
from app.services.structured_metadata_observations import tmdb_structured_metadata_observation


class MetadataCoverageTests(unittest.TestCase):
    def setUp(self):
        fixture.StructuredMetadataRuntimeTests.setUp(self)
        self.addCleanup(fixture.StructuredMetadataRuntimeTests.tearDown, self)
        # Windows asyncio initializes a local socketpair. Initialize its loop
        # before blocking every connect; requests below stay network-disabled.
        self.runner = asyncio.Runner(); self.runner.get_loop()
        self.addCleanup(self.runner.close)
        network = patch('socket.socket.connect', side_effect=AssertionError('No network in metadata coverage tests'))
        network.start(); self.addCleanup(network.stop)
        self.payload = {'title': 'Main Title', 'original_title': 'Original Title', 'original_language': 'en',
            'production_countries': [{'iso_3166_1': 'JP'}], 'genres': [{'id': 18, 'name': 'Drama'}],
            'credits': {'crew': [{'id': 100, 'name': 'Test Director', 'job': 'Director'}],
                'cast': [{'id': i + 200, 'name': f'Local Actor {i}', 'original_name': f'Actor {i}',
                          'character': f'Role {i}', 'order': i} for i in range(15)]}}
        with Session(self.engine) as session:
            film = session.get(Film, fixture.FILM_ID); film.release_year = 2003
            session.add(film); session.commit()

    def apply(self, payload=None, language='en-US'):
        observation = tmdb_structured_metadata_observation(payload if payload is not None else self.payload, 42, language=language)
        with Session(self.engine) as session:
            self.sync.sync(session, film_id=fixture.FILM_ID, library_item_id=fixture.ITEM_ID, observation=observation)
            session.commit()

    def test_full_imported_cast_reaches_keyword_and_combined_role_filters(self):
        self.apply()
        self.assertEqual(projection_reader.film_page(self.engine, query='Local Actor 14')['total'], 1)
        local = LocalSearch(self.engine)
        result = local.interpret('films directed by Test Director starring Local Actor 14 after 2000')
        self.assertEqual(result['status'], 'ready')
        self.assertEqual(result['results']['total'], 1)
        self.assertEqual(local.interpret('films directed by Actor 14 after 2000')['results']['total'], 0)
        self.payload['credits']['cast'] = self.payload['credits']['cast'][:10]
        self.apply()
        self.assertEqual(projection_reader.film_page(self.engine, query='Local Actor 14')['total'], 0)
        self.assertEqual(local.interpret('films starring Local Actor 14 after 2000')['status'], 'needs_clarification')

    def test_alternative_snapshot_deduplicates_and_withdraws_without_losing_other_locales(self):
        self.payload['alternative_titles'] = {'titles': [{'title': 'Search Alias'}, {'title': ' Search Alias '}]}
        self.apply(language='zh-CN')
        self.assertEqual(projection_reader.film_page(self.engine, query='Search Alias')['total'], 1)
        with Session(self.engine) as session:
            aliases = session.exec(select(FilmTitle).where(FilmTitle.title_type == 'alternative', FilmTitle.superseded_at.is_(None))).all()
            self.assertEqual(len(aliases), 1); self.assertEqual(aliases[0].locale, 'und')
        del self.payload['alternative_titles']
        self.payload['title'] = 'Localized Other'
        self.apply(language='ja')
        self.assertEqual(projection_reader.film_page(self.engine, query='Search Alias')['total'], 1)
        self.payload['alternative_titles'] = {'titles': [None]}
        self.apply(language='ja')
        self.assertEqual(projection_reader.film_page(self.engine, query='Search Alias')['total'], 1)
        self.payload['alternative_titles'] = {'titles': []}
        self.apply(language='ja')
        self.assertEqual(projection_reader.film_page(self.engine, query='Search Alias')['total'], 0)
        self.assertEqual(projection_reader.film_page(self.engine, query='Main Title')['total'], 1)

    def test_synopsis_terms_are_local_soft_matches_and_exact_titles_keep_priority(self):
        self.payload['alternative_titles'] = {'titles': [{'title': 'Rare phrase'}]}
        self.apply()
        second = 'film_' + '9' * 32
        with Session(self.engine) as session:
            session.add(GraphEntity(id=second, entity_type='film'))
            session.add(Film(id=second, canonical_title='AAA Other', overview='A rare phrase describes stellar navigation.'))
            session.add(LibraryItem(id='lib_'+'9'*32, profile_id='profile_local', film_id=second,
                source_type='local', source_instance_id='local', source_item_key='synthetic:second'))
            session.commit()
        page = projection_reader.film_page(self.engine, query='Rare phrase', rank_exact=True)
        self.assertEqual([f['id'] for f in page['items']], [fixture.FILM_ID, second])
        self.assertEqual(projection_reader.film_page(self.engine, query='stellar navigation')['total'], 1)
        # A synopsis mention never establishes the hard country requirement.
        local = LocalSearch(self.engine)
        self.assertEqual(local.interpret('Japanese films after 2000')['results']['total'], 1)
        self.assertEqual(local.interpret('films excluding Japan')['results']['total'], 0)
        soft = local.interpret('Japanese films about stellar navigation')
        self.assertEqual(soft['status'], 'unsupported')
        self.assertIsNone(soft['results'])
        with Session(self.engine) as session:
            film = session.get(Film, second); film.overview = 'Changed astronomy account.'
            session.add(film); session.commit()
        self.assertEqual(projection_reader.film_page(self.engine, query='stellar navigation')['total'], 0)
        self.assertEqual(projection_reader.film_page(self.engine, query='astronomy')['total'], 1)
        self.assertEqual(projection_reader.film_page(self.engine, query='%')['total'], 0)

    def test_exact_imported_names_and_local_conditions_do_not_consult_ai(self):
        self.payload['alternative_titles'] = {'titles': [{'title': 'Known Alias'}]}
        self.apply()
        interpreter = Mock(); interpreter.interpret_search.side_effect = AssertionError('AI must not run')
        with patch.object(ask_module, 'engine', self.engine):
            service = DiscoverySearchService(ask=AskService(interpreter=interpreter))
            for question in ('Known Alias', 'Original Title', 'Local Actor 14'):
                self.assertEqual(service.interpret(DiscoveryQuestion(question=question, allow_ai=True))['status'], 'keyword')
            result = service.interpret(DiscoveryQuestion(question='films starring Local Actor 14 after 2000', allow_ai=True))
            self.assertEqual(result['status'], 'ready')
        interpreter.interpret_search.assert_not_called()

    def test_optional_runtime_failure_cannot_block_complete_local_requests(self):
        from app.api import explore as api
        from app.services.semantic_search import SemanticError
        self.payload['alternative_titles'] = {'titles': [{'title': 'Known Alias'}]}
        self.apply()
        with patch.object(ask_module, 'engine', self.engine), patch.object(api, '_evaluation',
                side_effect=SemanticError('search_evaluation_config_invalid')) as optional:
            for question in ('Known Alias', 'films starring Local Actor 14 after 2000'):
                result = self.runner.run(api.interpret_discovery(DiscoveryQuestion(question=question, allow_ai=True), Mock()))
                self.assertIn(result['status'], {'keyword', 'ready'})
            optional.assert_not_called()
            # An explicit evaluation submission cannot use this fast path to
            # bypass the disabled/invalid evaluation configuration.
            from fastapi import HTTPException
            with self.assertRaises(HTTPException):
                self.runner.run(api.interpret_discovery(DiscoveryQuestion(question='Known Alias', evaluation_only=True), Mock()))
            optional.assert_called_once()

    def test_long_descriptions_without_literal_hits_keep_the_semantic_route(self):
        from app.api import explore as api
        from unittest.mock import AsyncMock
        self.apply()
        marker = {'status': 'semantic-test-sentinel'}
        with patch.object(ask_module, 'engine', self.engine), patch.object(api, '_evaluation', return_value=Mock()) as optional, \
                patch.object(api, '_cancellable_search', new=AsyncMock(return_value=marker)) as routed:
            request = DiscoveryQuestion(question='An elderly musician searches for a missing manuscript', allow_ai=True)
            self.assertEqual(self.runner.run(api.interpret_discovery(request, Mock())), marker)
            optional.assert_called_once(); routed.assert_awaited_once()

    def test_synopsis_literal_results_survive_broken_optional_runtime(self):
        from app.api import explore as api
        self.apply()
        with Session(self.engine) as session:
            film = session.get(Film, fixture.FILM_ID); film.overview = 'Stellar navigation'
            session.add(film); session.commit()
        with patch.object(ask_module, 'engine', self.engine), patch.object(api, '_evaluation', side_effect=AssertionError('Optional runtime')) as optional:
            result = self.runner.run(api.interpret_discovery(DiscoveryQuestion(question='Stellar navigation', allow_ai=True), Mock()))
            self.assertEqual(result['status'], 'keyword'); optional.assert_not_called()

    def test_projection_bootstrap_rebuilds_old_search_version_without_source_mutation(self):
        from app.canonical_models import FilmSearchReadModel, ProjectionState
        self.apply()
        with Session(self.engine) as session:
            film = session.get(Film, fixture.FILM_ID); film.overview = 'Previously unindexed wording'
            session.add(film); session.commit()
            state = session.get(ProjectionState, 'search'); state.projection_version = 'film-search.v2'
            session.add(state); session.commit()
        projection_coordinator.bootstrap(self.engine)
        self.assertEqual(projection_reader.film_page(self.engine, query='unindexed wording')['total'], 1)
        with Session(self.engine) as session:
            self.assertEqual(session.get(Film, fixture.FILM_ID).overview, 'Previously unindexed wording')
            self.assertEqual(session.get(FilmSearchReadModel, fixture.FILM_ID).projection_version, 'film-search.v3')


class NfoAndTransportCoverageTests(unittest.TestCase):
    def test_nfo_typed_identity_and_full_cast_without_changing_preview(self):
        with tempfile.TemporaryDirectory() as folder, patch('socket.socket.connect', side_effect=AssertionError('No network')):
            root = Path(folder); nfo = root/'movie.nfo'
            actors = ''.join(f'<actor><name>Person {i}</name><tmdbid>{100+i}</tmdbid></actor>' for i in range(15))
            nfo.write_text('<movie><title>Localized</title><originaltitle>Original</originaltitle>'
                '<uniqueid type="tmdb">42</uniqueid><uniqueid type="imdb">tt1234567</uniqueid>'
                + actors + '</movie>', encoding='utf-8')
            result = NFOScanner(str(root))._parse_nfo_observed(nfo, root)
            self.assertIsNotNone(result)
            self.assertEqual((result.film['tmdb_id'], result.film['imdb_id']), ('42', 'tt1234567'))
            self.assertEqual(len(result.film['actors']), 5)
            self.assertEqual(len(result.structured_metadata.credits), 15)
            self.assertEqual(result.structured_metadata.credits[-1].name, 'Person 14')
            self.assertEqual(nfo.read_text(encoding='utf-8').count('<actor>'), 15)

    def test_nfo_ignores_unknown_or_conflicting_typed_ids_and_preserves_explicit_scalars(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); nfo = root/'movie.nfo'
            nfo.write_text('<movie><title>Film</title><uniqueid type="tmdb">7</uniqueid>'
                '<uniqueid type="tmdb">8</uniqueid><uniqueid type="unknown">tt111</uniqueid></movie>', encoding='utf-8')
            result = NFOScanner(str(root))._parse_nfo_observed(nfo, root)
            self.assertIsNone(result.film['tmdb_id'])
            self.assertIsNone(result.film['imdb_id'])
            nfo.write_text('<movie><title>Film</title><tmdbid>9</tmdbid><id>tt999</id>'
                '<uniqueid type="tmdb">8</uniqueid><uniqueid type="imdb">tt888</uniqueid></movie>', encoding='utf-8')
            result = NFOScanner(str(root))._parse_nfo_observed(nfo, root)
            self.assertEqual((result.film['tmdb_id'],result.film['imdb_id']),('9','tt999'))

    def test_alternative_titles_share_the_existing_details_request(self):
        client = TMDBClient(api_key='synthetic-only')
        with patch.object(client, '_get', return_value={}) as fetch:
            client.movie_details(42)
        self.assertEqual(fetch.call_count, 1)
        self.assertIn('alternative_titles', fetch.call_args.kwargs['params']['append_to_response'].split(','))


if __name__ == '__main__':
    unittest.main()
