"""Explicit bounded resumption; old FAIL, unknown receipts and grants survive.

Default execution prepares immutable local evidence, without a key or network.
Live stages require the renewed user authorization. No automatic retry exists.
"""
from dataclasses import asdict
from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import time
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import create_engine

from app.evaluation.openrouter_pilot import existing_credential
from app.evaluation.search_continuation import immutable
from app.evaluation.search_holdout import SOURCES
from app.evaluation.search_integration import RUN, authorization
from app.evaluation.search_recovery import IndexTimeoutClient, TraceSession
from app.evaluation.search_validation_budget import ValidationBudget, PREFIX
from app.services.openrouter_embeddings import http_session
from app.services.projections import ProjectionReader
from app.services.search_index import SearchIndexStore, CachedSearchEmbedding
from app.services.search_providers import SearchProviderClient, SearchEmbeddingProvider, ENDPOINTS, embedding_spec
from app.services.search_runtime import EvaluationRuntime
from app.services.semantic_search import SemanticError, _hash

DIRECTORY = RUN / 'resumption-20261026'
SOURCE = Path('D:/Projects/5X49/backend/data/library.db')
REPEAT_HASH = 'da48ca9d9b457be0ce0ca5e45ea0b9009ad0bf3e5d4f746ae0e75339d403d5e6'


def readonly(path):
    db = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA query_only=ON')
    return db


def manifest_runtime():
    manifest = json.loads((RUN / 'persistent-test-library/manifest.json').read_text(encoding='utf8'))
    engine = create_engine('sqlite:///file:' + SOURCE.as_posix() + '?mode=ro&uri=true',
                           connect_args={'check_same_thread': False})
    try:
        runtime = EvaluationRuntime(manifest, engine)
    except Exception:
        engine.dispose()
        raise
    return manifest, engine, runtime


def prepare():
    DIRECTORY.mkdir(exist_ok=True)
    baseline = json.loads((DIRECTORY / 'preparation.json').read_text(encoding='utf8'))
    manifest, engine, runtime = manifest_runtime()
    try:
        with closing(readonly(RUN / 'shared-budget.sqlite3')) as db:
            rows = [dict(r) for r in db.execute('SELECT * FROM search_budget_receipts ORDER BY number')]
            meta = {r[0]: r[1] for r in db.execute('SELECT key,value FROM search_budget_meta') if not r[0].startswith(PREFIX)}
        if (_hash(rows[:137]) != baseline['original_rows_sha256']
                or sha256((RUN / 'persistent-test-library/manifest.json').read_bytes()).hexdigest() != baseline['manifest_sha256']
                or runtime.current_revision() != baseline['source_revision_verified']):
            raise SemanticError('search_validation_baseline_changed')
        grant_path = DIRECTORY / 'grant.json'
        if grant_path.exists():
            grant = json.loads(grant_path.read_text(encoding='utf8'))
        else:
            if len(rows) != 137:
                raise SemanticError('search_validation_already_attempted')
            now = int(time.time())
            grant = {'version': 'bounded-validation-grant.v1', 'original_grant': authorization(RUN).fingerprint,
                'baseline': 137, 'max_attempts': 191, 'issued': now, 'expires': now + 86400,
                'original_rows_sha256': _hash(rows), 'historical_meta_sha256': _hash(meta),
                'document_batches': baseline['index_wire_hashes']}
            immutable(grant_path, grant)
        backend = Path(__file__).resolve().parents[2]
        names = (*SOURCES, 'app/services/search_literals.py', 'app/contracts/bound_search_plan.py',
                 'app/evaluation/search_validation_budget.py', 'app/evaluation/search_validation_resume.py')
        config = {'version': 'bounded-validation-resumption.v1', 'grant_sha256': _hash(grant),
            'models': [asdict(e) for e in ENDPOINTS], 'embedding': asdict(embedding_spec()),
            'policy': asdict(runtime.policy), 'source_revision': runtime.current_revision(),
            'sources': {n: sha256((backend / n).read_text(encoding='utf8').encode()).hexdigest() for n in names},
            'query_file_sha256': sha256((RUN / 'persistent-test-library/validation-queries.json').read_bytes()).hexdigest(),
            'timeouts': {'document': 60, 'query': 20, 'decision': 5, 'rerank': 10},
            'new_independent_assessment': False, 'max_additional_posts': 54, 'original_fail_unchanged': True}
        envelope = {'configuration': config, 'sha256': _hash(config)}
        immutable(DIRECTORY / 'configuration.json', envelope)
        return grant, envelope
    finally:
        engine.dispose()


def client_for(ledger, scope, credential_path):
    class NativeClient(SearchProviderClient):
        def request(self, endpoint, body, **options):
            if options['purpose'] == 'document':
                options = {**options, 'timeout': 60}
            return super().request(endpoint, body, **options)
    return NativeClient(ledger, scope, lambda: existing_credential(credential_path),
        session=TraceSession(http_session(), ledger, RUN / 'transport'),
        response_sink=lambda n, p: immutable(RUN / f'response-{n:03}.json', p))


def accounting():
    ledger = ValidationBudget(RUN / 'shared-budget.sqlite3', authorization(RUN))
    try:
        return ledger.summary()
    finally:
        ledger.close()


def repeat(credential_path, grant, config):
    ledger = ValidationBudget(RUN / 'shared-budget.sqlite3', authorization(RUN))
    manifest, engine, runtime = manifest_runtime()
    db = sqlite3.connect(runtime.index_path)
    client = client_for(ledger, runtime.scope, credential_path)
    try:
        if ledger.summary()['attempts'] != 137:
            raise SemanticError('search_repeat_already_attempted_or_ledger_changed')
        store = SearchIndexStore(db)
        job = db.execute('SELECT id FROM search_index_jobs ORDER BY created DESC LIMIT 1').fetchone()[0]
        texts = store._missing(store._work(job), runtime.spec)[:4]
        if len(texts) != 4 or _hash([{'input': texts, 'encoding_format': 'float', 'input_type': 'passage'}, 'document']) != REPEAT_HASH:
            raise SemanticError('search_repeat_input_mismatch')
        client.preflight()
        native = SearchEmbeddingProvider(client)
        if native.spec != runtime.spec:
            raise SemanticError('search_index_stale')
        ledger.activate(grant)
        start = time.monotonic()
        state = store.step(job, CachedSearchEmbedding(store, native))
        linked = ledger.complete_repeat(store, native.spec, texts)
        report = {'configuration_sha256': config['sha256'], 'status': 'repeat-success', 'linked': linked,
            'elapsed_ms': (time.monotonic() - start) * 1000, 'remaining_chunks': state['remaining_chunks'],
            'receipt': ledger.summary()['receipts'][-1], 'original_unknown_preserved': [50, 137]}
        immutable(DIRECTORY / 'repeat-completion.json', report)
        return report
    finally:
        client.close(); db.close(); ledger.close(); engine.dispose()


def library(credential_path, grant, config):
    initial = accounting()
    if initial['halted']:
        raise SemanticError('search_budget_blocked')
    manifest, engine, runtime = manifest_runtime()
    before = SOURCE.stat()
    runtime.provider_factory = lambda ledger, scope, _key: client_for(ValidationBudget.view(ledger), scope, credential_path)
    queries = json.loads((RUN / 'persistent-test-library/validation-queries.json').read_text(encoding='utf8'))
    if len(queries) != 10 or len({r['id'] for r in queries}) != 10:
        raise SemanticError('search_test_library_extent_changed')
    directory = DIRECTORY / 'test-library'; directory.mkdir(exist_ok=True)
    from app.api import explore as routes
    old = routes._evaluation; routes._evaluation = lambda: runtime
    application = FastAPI(); application.include_router(routes.router)
    results = []
    try:
        with TestClient(application) as client:
            response = client.post('/explore/search/index', json={'action': 'begin'})
            if response.status_code != 200:
                raise SemanticError('search_test_library_index_failed')
            state = response.json()
            while state['state'] != 'complete':
                if accounting()['halted']:
                    raise SemanticError('search_budget_blocked')
                response = client.post('/explore/search/index', json={'action': 'step', 'job_id': state['id']})
                if response.status_code != 200:
                    raise SemanticError('search_test_library_index_failed')
                state = response.json()
                print(json.dumps({'stage': 'library-index', 'remaining': state['remaining_chunks'], 'attempts': accounting()['attempts']}), flush=True)
            immutable(directory / 'index-complete.json', state)
            for row in queries:
                target = directory / (row['id'] + '.json')
                if target.exists():
                    results.append(json.loads(target.read_text(encoding='utf8'))); continue
                count = accounting()['attempts']; start = time.monotonic()
                response = client.post('/explore/search/interpret', json={**{k:v for k,v in row.items() if k!='id'},
                    'allow_ai': True, 'evaluation_only': True, 'request_id': 'rq_' + uuid4().hex})
                data = response.json(); elapsed = (time.monotonic() - start) * 1000
                ids = ([f['id'] for f in ProjectionReader().film_page(engine, query=data.get('keyword_query') or row['question'], rank_exact=True)['items']]
                       if data.get('status') == 'keyword' else [i['film']['id'] for i in (data.get('results') or {}).get('items', [])])
                restore = None
                if data.get('snapshot') and data.get('status') == 'ready':
                    saved = accounting()['attempts']
                    restored = client.post('/explore/search/query', json={'question': row['question'], 'plan': data['plan'],
                        'people_ids': data.get('people_ids', {}), 'semantic_snapshot': data['snapshot']})
                    restored_ids = [i['film']['id'] for i in (restored.json().get('results') or {}).get('items', [])]
                    restore = {'http_status': restored.status_code, 'same_ids': restored_ids == ids,
                               'additional_posts': accounting()['attempts'] - saved}
                summary = accounting()
                record = {**row, 'status': data.get('status'), 'http_status': response.status_code, 'raw_result': data,
                    'actual_ids': ids, 'elapsed_ms': elapsed, 'restore': restore, 'configuration_sha256': config['sha256'],
                    'receipts': [r for r in summary['receipts'] if r['number'] > count]}
                immutable(target, record); results.append(record)
                print(json.dumps({'stage': 'library-query', 'id': row['id'], 'status': data.get('status'), 'results': len(ids), 'attempts': summary['attempts']}), flush=True)
                if summary['halted']:
                    break
        report = {'configuration_sha256': config['sha256'], 'completed_queries': len(results), 'indexed_films': 14,
            'source_readonly': True, 'source_size_mtime_unchanged': (before.st_size, before.st_mtime_ns) == (SOURCE.stat().st_size, SOURCE.stat().st_mtime_ns),
            'results': results, 'accounting': accounting(), 'independent_quality_acceptance': False}
        immutable(directory / 'report.json', report)
        return {k:v for k,v in report.items() if k not in {'results', 'accounting'}}
    finally:
        routes._evaluation = old; engine.dispose()


def seen(credential_path, grant, config):
    """Only the ten missing seen cases; exact cached stages remain distinguished."""
    from app.evaluation.search_seen_replay import RecordedClient
    from app.evaluation.search_holdout import execution_questions
    from app.services.content_request import split_content_request
    from app.services.integrated_search import IntegratedSearch
    from app.services.search_local import LocalSearch
    from app.services.search_providers import EgressScope, DecisionProvider, RerankProvider
    if accounting()['halted']:
        raise SemanticError('search_budget_blocked')
    old_report = RUN / 'seen-regression-v4-d7f859bc1a4e3434/report.json'
    if sha256(old_report.read_bytes()).hexdigest() != 'ce1974a929b6ab25c68621b836158ee718b8deb54597128dc7c870b9a03ac809':
        raise SemanticError('search_validation_baseline_changed')
    prior = json.loads(old_report.read_text(encoding='utf8'))
    missing = {r['id'] for r in prior['results'] if not r['local_only'] and not r['model_replay_complete']}
    rows = [r for r in execution_questions(RUN / 'execution-queries.v2.json') if r['id'] in missing]
    if len(rows) != 10:
        raise SemanticError('search_validation_extent_changed')
    directory = DIRECTORY / 'seen'; directory.mkdir(exist_ok=True)
    copied = directory / 'index.sqlite3'
    if not copied.exists():
        with closing(readonly(RUN / 'holdout/index.sqlite3')) as source, closing(sqlite3.connect(copied)) as target:
            source.backup(target)
    db = sqlite3.connect(copied); store = SearchIndexStore(db); spec = embedding_spec()
    docs, _, _ = store.read(spec)
    engine = create_engine('sqlite:///file:' + (RUN / 'holdout/public-library.sqlite3').as_posix() + '?mode=ro&uri=true')
    local = LocalSearch(engine)
    query_texts = {r['question'] for r in rows} | {t for d in docs for t in d.chunks}
    for row in rows:
        request = split_content_request(row['question'], lookup=local.reference_candidates, mentions=local.title_mentions)
        if not request.issue:
            query_texts.add(request.text)
    scope = EgressScope('public-evaluation.v2', frozenset(_hash(t) for d in docs for t in d.chunks),
                       frozenset(_hash(t) for t in query_texts), True)
    ledger = ValidationBudget(RUN / 'shared-budget.sqlite3', authorization(RUN))
    native = client_for(ledger, scope, credential_path)
    original = json.loads((RUN / 'holdout/execution-report.json').read_text(encoding='utf8'))
    receipts = {r['number']: r for result in original['results'] for r in result['receipts']}
    actual = {r['number']: r for r in ledger.summary()['receipts']}
    if any(actual.get(n) != r for n, r in receipts.items()):
        raise SemanticError('search_replay_evidence_mismatch')
    responses = {n: json.loads((RUN / f'response-{n:03}.json').read_text(encoding='utf8')) for n in receipts
                 if (RUN / f'response-{n:03}.json').exists()}
    recorded = RecordedClient(list(receipts.values()), responses)

    class MissingOnly:
        def __init__(self):
            self.events = []; self.limit = 0
        def request(self, endpoint, body, **options):
            try:
                result = recorded.request(endpoint, body, **options)
                self.events.append({**recorded.events[-1], 'execution': 'exact_recorded_reuse'})
                return result
            except SemanticError as error:
                if error.code != 'search_replay_missing_response':
                    raise
            if sum(e['execution'] == 'live' for e in self.events) >= self.limit:
                raise SemanticError('search_validation_case_limit')
            result = native.request(endpoint, body, **options)
            self.events.append({'purpose': options['purpose'], 'execution': 'live',
                                'receipt': ledger.summary()['receipts'][-1]['number']})
            return result

    mixed = MissingOnly()
    class MissingEmbedding:
        def __init__(self):
            self.spec = spec
        def embed(self, texts, *, query):
            vectors = [store.cached_vector(text, spec, query=query) for text in texts]
            if all(v is not None for v in vectors):
                mixed.events.append({'purpose': 'query', 'execution': 'exact_vector_reuse'})
                return vectors
            if not query or sum(e['execution'] == 'live' for e in mixed.events) >= mixed.limit:
                raise SemanticError('search_validation_case_limit')
            values = SearchEmbeddingProvider(native).embed(texts, query=True)
            for text, vector in zip(texts, values):
                store.remember_vector(text, vector, spec, query=True)
            mixed.events.append({'purpose': 'query', 'execution': 'live',
                                 'receipt': ledger.summary()['receipts'][-1]['number']})
            return values
    search = IntegratedSearch(store, spec, local_interpret=local.interpret, known_literal=local.known_literal,
        resolve_hard=local.executor.resolve, eligible=lambda plan, ids: local.executor.eligible_ids(plan, people_ids=ids),
        summaries=local.summaries, corpus_revision=lambda: store.meta('revision'), reference_candidates=local.reference_candidates,
        title_mentions=local.title_mentions, decision=DecisionProvider(mixed), embedding=MissingEmbedding(), reranker=RerankProvider(mixed))
    outputs = []
    try:
        for row in rows:
            target = directory / (row['id'] + '.json')
            if target.exists():
                outputs.append(json.loads(target.read_text(encoding='utf8'))); continue
            if ledger.summary()['halted']:
                break
            count = ledger.summary()['attempts']; start = time.monotonic()
            native.preflight()
            if SearchEmbeddingProvider(native).spec != spec:
                raise SemanticError('search_index_stale')
            mixed.events = []
            request = split_content_request(row['question'], lookup=local.reference_candidates, mentions=local.title_mentions)
            mixed.limit = 1 if request.reference else 3
            result = search.submit(row['question'])
            ids = ([f['id'] for f in ProjectionReader().film_page(engine, query=result.get('keyword_query') or row['question'], rank_exact=True)['items']]
                   if result['status'] == 'keyword' else [i['film']['id'] for i in (result.get('results') or {}).get('items', [])])
            saved = store.snapshot(result['snapshot'], row['question']) if result.get('snapshot') else None
            record = {**row, 'configuration_sha256': config['sha256'], 'result': result, 'actual_ids': ids,
                'saved_snapshot': saved, 'stages': mixed.events, 'elapsed_ms': (time.monotonic()-start)*1000,
                'receipts': [r for r in ledger.summary()['receipts'] if r['number']>count],
                'independent_acceptance': False, 'seen_regression_only': True}
            immutable(target, record); outputs.append(record)
            print(json.dumps({'stage': 'seen', 'id': row['id'], 'status': result['status'], 'results': len(ids),
                              'attempts': ledger.summary()['attempts']}), flush=True)
        report = {'configuration_sha256': config['sha256'], 'results': outputs, 'completed_queries': len(outputs),
                  'accounting': ledger.summary(), 'seen_regression_only': True, 'original_fail_unchanged': True}
        immutable(directory / 'report.json', report)
        return {k:v for k,v in report.items() if k not in {'results', 'accounting'}}
    finally:
        native.close(); ledger.close(); db.close(); engine.dispose()


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-live', action='store_true')
    parser.add_argument('--phase', choices=['repeat', 'library', 'seen'], default='repeat')
    parser.add_argument('--credential-file', type=Path)
    args = parser.parse_args()
    try:
        grant, config = prepare()
        result = {'status': 'prepared', 'configuration_sha256': config['sha256'], 'new_posts': 0}
        if args.run_live:
            result = {'repeat': repeat, 'library': library, 'seen': seen}[args.phase](args.credential_file, grant, config)
        print(json.dumps(result, ensure_ascii=False), flush=True)
    except SemanticError as error:
        print(json.dumps({'status': 'stopped', 'code': error.code, 'phase': args.phase}), flush=True)
        raise SystemExit(1)
