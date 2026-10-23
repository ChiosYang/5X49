"""Separate14/15 whitelisted test-library API validation; no source writes.

The existing Explore handlers run in a local ASGI test instance with an explicit
runtime factory. No normal server settings, environment credentials or startup
migrations are changed. Only the previously prepared ten public test questions
may be submitted. No inference by default.
"""
from hashlib import sha256
import json
from pathlib import Path
import time
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import create_engine

from app.evaluation.openrouter_pilot import existing_credential
from app.evaluation.search_continuation import immutable
from app.evaluation.search_integration import RUN,authorization
from app.evaluation.search_recovery import ContinuedBudget,TraceSession
from app.evaluation.search_repeat import configuration as infrastructure_configuration
from app.services.discovery_search import keyword_text
from app.services.openrouter_embeddings import http_session
from app.services.projections import ProjectionReader
from app.services.search_providers import SearchProviderClient
from app.services.search_runtime import EvaluationRuntime
from app.services.semantic_search import SemanticError,_hash


def validate(source_path,credential_path,*,run_live=False):
    directory=RUN/'persistent-test-library'
    manifest_path=directory/'manifest.json'; question_path=directory/'validation-queries.json'
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    queries=json.loads(question_path.read_text(encoding='utf-8'))
    if len(queries)!=10 or len({r['id'] for r in queries})!=10:
        raise SemanticError('search_test_library_extent_changed')
    config={'version':'persistent-test-library-execution.v1','infrastructure_sha256':infrastructure_configuration()['sha256'],
        'manifest_sha256':sha256(manifest_path.read_bytes()).hexdigest(),
        'queries_sha256':sha256(question_path.read_bytes()).hexdigest(),
        'source_sha256':sha256(Path(__file__).read_text(encoding='utf-8').encode()).hexdigest(),
        'scope':'existing Explore API handlers, readonly actual test-library source,14 reviewed documents,10 queries',
        'not_public_holdout':True,'source_public_fields_only':True}
    envelope={'configuration':config,'sha256':_hash(config)}
    immutable(directory/'execution-configuration.v1.json',envelope)
    if not run_live: return {'status':'prepared','sha256':envelope['sha256'],'model_calls':0}
    before_source=source_path.stat()
    def accounting():
        budget=ContinuedBudget(RUN/'shared-budget.sqlite3',authorization(RUN))
        try: return budget.summary()
        finally: budget.close()
    initial=accounting()
    if initial['halted']: raise SemanticError('search_budget_blocked')
    if initial['attempts']+4+30>320: raise SemanticError('search_test_library_budget_insufficient')
    trace=RUN/'transport'; trace.mkdir(exist_ok=True)
    class NativeEvaluationClient(SearchProviderClient):
        def request(self,endpoint,body,**options):
            if options['purpose']=='document': options={**options,'timeout':60}
            return super().request(endpoint,body,**options)
    def provider_factory(original,scope,_unused_key_supplier):
        budget=ContinuedBudget.view(original)
        return NativeEvaluationClient(budget,scope,lambda:existing_credential(credential_path),
            session=TraceSession(http_session(),budget,trace),
            response_sink=lambda n,p:immutable(RUN/f'response-{n:03}.json',p))
    engine=create_engine('sqlite:///file:'+source_path.as_posix()+'?mode=ro&uri=true',connect_args={'check_same_thread':False})
    from app.api import explore as routes
    runtime=EvaluationRuntime(manifest,engine,provider_factory=provider_factory)
    old_factory=routes._evaluation
    routes._evaluation=lambda:runtime
    application=FastAPI(); application.include_router(routes.router)
    results=[]
    try:
        with TestClient(application) as client:
            start_index=client.post('/explore/search/index',json={'action':'begin'})
            if start_index.status_code!=200: raise SemanticError('search_test_library_index_failed')
            state=start_index.json()
            while state['state']!='complete':
                if accounting()['halted']: raise SemanticError('search_budget_blocked')
                response=client.post('/explore/search/index',json={'action':'step','job_id':state['id']})
                if response.status_code!=200: raise SemanticError('search_test_library_index_failed')
                state=response.json()
                print(json.dumps({'library_index':state['state'],'remaining_chunks':state['remaining_chunks'],'posts':accounting()['requests']}),flush=True)
            for row in queries:
                target=directory/(row['id']+'.json')
                if target.exists():
                    results.append(json.loads(target.read_text(encoding='utf-8'))); continue
                before=accounting()['attempts']; start=time.monotonic()
                response=client.post('/explore/search/interpret',json={**{k:v for k,v in row.items() if k!='id'},
                    'allow_ai':True,'evaluation_only':True,'request_id':'rq_'+uuid4().hex})
                data=response.json(); elapsed=(time.monotonic()-start)*1000
                if response.status_code==200 and data.get('status')=='keyword':
                    page=ProjectionReader().film_page(engine,
                        query=data.get('keyword_query') or keyword_text(row['question']),rank_exact=True)
                    ids=[film['id'] for film in page['items']]
                else: ids=[item['film']['id'] for item in (data.get('results') or {}).get('items',[])]
                restore=None
                if data.get('snapshot') and data.get('status')=='ready':
                    posts_before_restore=accounting()['requests']
                    restored=client.post('/explore/search/query',json={'question':row['question'],'plan':data['plan'],
                        'people_ids':data.get('people_ids',{}),'semantic_snapshot':data['snapshot']})
                    restored_ids=[item['film']['id'] for item in (restored.json().get('results') or {}).get('items',[])]
                    restore={'http_status':restored.status_code,'same_ids':restored_ids==ids,
                        'additional_native_posts':accounting()['requests']-posts_before_restore}
                summary=accounting()
                record={**row,'configuration_sha256':envelope['sha256'],'http_status':response.status_code,
                    'status':data.get('status'),'reason':data.get('reason') or data.get('detail'),
                    'plan':data.get('plan'),'semantic':data.get('semantic'),'actual_ids':ids,
                    'api_elapsed_ms':elapsed,'restore':restore,
                    'receipts':[r for r in summary['receipts'] if r['number']>before],
                    'fields_omitted_from_report':['profiles','viewing records','paths','private notes']}
                immutable(target,record); results.append(record)
                print(json.dumps({'library_case':row['id'],'status':data.get('status'),'returned':len(ids),'posts':summary['requests']}),flush=True)
                if summary['halted']: break
        after_source=source_path.stat()
        source_unchanged=(before_source.st_size,before_source.st_mtime_ns)==(after_source.st_size,after_source.st_mtime_ns)
        report={'version':'persistent-test-library-api-validation.v1','configuration_sha256':envelope['sha256'],
            'source_films':15,'indexed_films':len(runtime.documents),'public_field_exclusions':1,
            'completed_cases':len(results),'results':results,'accounting':accounting(),
            'source_readonly':True,'source_size_mtime_unchanged':source_unchanged,
            'production_enabled':False,'not_independent_quality_acceptance':True,
            'native_post_delta':accounting()['requests']-initial['requests']}
        immutable(directory/('execution-report.json' if len(results)==10 else f'execution-interrupted-{len(results)}.json'),report)
        if not source_unchanged: raise SemanticError('search_test_library_source_changed')
        return {k:v for k,v in report.items() if k not in {'results','accounting'}}
    finally:
        routes._evaluation=old_factory; engine.dispose()


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-live',action='store_true'); parser.add_argument('--source-db',type=Path,required=True)
    parser.add_argument('--credential-file',type=Path)
    args=parser.parse_args()
    print(json.dumps(validate(args.source_db,args.credential_file,run_live=args.run_live)))
