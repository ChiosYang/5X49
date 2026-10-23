"""Infrastructure-change continuation, with unchanged frozen query behavior.

No labels are loaded. No automatic model retry. Document transport alone uses
the newly authorized60s timeout. Original20s query embedding,5s Decision and10s
rerank implementations are imported unchanged from the pre-reveal freeze.
"""
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import time

from app.contracts.bound_search_plan import SearchPlan
from app.evaluation.openrouter_pilot import existing_credential
from app.evaluation.search_corpus import load_corpus,documents,seed_projection_database
from app.evaluation.search_holdout import freeze,execution_questions
from app.evaluation.search_integration import RUN,authorization,write_json
from app.evaluation.search_recovery import ContinuedBudget,IndexTimeoutClient,TraceSession
from app.evaluation.search_repeat import configuration as infrastructure_configuration
from app.services.content_request import split_content_request
from app.services.discovery_search import keyword_text
from app.services.integrated_search import IntegratedSearch
from app.services.openrouter_embeddings import http_session
from app.services.projections import ProjectionReader
from app.services.search_index import CachedSearchEmbedding,SearchIndexStore
from app.services.search_local import LocalSearch
from app.services.search_providers import DecisionProvider,EgressScope,SearchEmbeddingProvider,SearchProviderClient,RerankProvider,embedding_spec
from app.services.semantic_search import SemanticError,_hash


def immutable(path,value):
    if path.exists():
        if json.loads(path.read_text(encoding='utf-8'))!=value:
            raise SemanticError('search_execution_output_immutable')
    else:
        write_json(path,value)


def configuration():
    original=freeze(); infrastructure=infrastructure_configuration()
    config={'version':'search-execution-continuation.v1',
        'configuration_sha256':original['sha256'],'infrastructure_sha256':infrastructure['sha256'],
        'query_behavior':'unchanged original24 source hashes; no qrels loaded',
        'query_timeouts_seconds':{'decision':5,'query_embedding':20,'rerank':10},
        'document_timeout_seconds':60,'classification_protocol_deviation':True,
        'timing_boundary':'before conditional per-query preflight through final displayed-ID extraction; offline ablations/file writes and initial index excluded',
        'source_sha256':sha256(Path(__file__).read_text(encoding='utf-8').encode()).hexdigest(),
        'ablations':'A lexical/B fixed hybrid from saved query vector and strict SQL; C actual routed candidates with local admission/no rerank; D actual native rerank/display. Deterministic local fast paths shared; unexecuted alternatives marked unavailable.'}
    result={'configuration':config,'sha256':_hash(config)}
    immutable(RUN/'holdout-execution-continuation.v1.json',result)
    return result


def safe_responses(receipts):
    result=[]
    for receipt in receipts:
        path=RUN/f"response-{receipt['number']:03}.json"
        payload=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
        result.append({'number':receipt['number'],'purpose':receipt['purpose'],'state':receipt['state'],
            'elapsed_ms':receipt['elapsed_ms'],'input_hash':receipt['input_hash'],
            **{k:v for k,v in payload.items() if k in {'id','model','provider','usage','answers','results'}}})
    return result


def stage_state(name,receipts,result,saved):
    attempted=[r for r in receipts if r['purpose']==name]
    payload=result.get('semantic') or {}
    ready=result.get('status')=='ready'
    cached=name=='query' and saved is not None and saved.get('query_vector') is not None and not attempted
    reference=name=='query' and saved is not None and saved.get('reference_id') is not None
    if name=='decision':
        applied=bool(attempted) and (ready and bool(payload) or result.get('status')=='keyword')
    elif name=='rerank':
        applied=bool(attempted) and ready and bool((saved or {}).get('scores')) and not payload.get('fallback')
    else:
        applied=ready and (cached or bool(attempted)) and bool((saved or {}).get('query_vector'))
    reported=bool(attempted) and all(r['state']=='reported' for r in attempted)
    valid=reported and (result.get('reason') is None or result.get('reason')=='search_route_uncertain')
    if name=='rerank': valid=reported and not payload.get('fallback') and bool((saved or {}).get('scores'))
    if name=='query': valid=reported and bool((saved or {}).get('query_vector'))
    return {'attempted':bool(attempted),'transport_and_usage_reported':reported,
        'valid_output_applied_or_retained':bool(valid),'applied':bool(applied),
        'cache':'hit' if cached else 'reference_content' if reference else 'miss' if attempted else 'not_required',
        'fallback_reason':payload.get('fallback') if name=='rerank' else result.get('reason'),
        'receipt_numbers':[r['number'] for r in attempted]}


def record_case(row,result,engine,store,local,client,receipts,actual_ids,elapsed,preflight,wall):
    candidates=[]; baselines={}; saved=None
    if result.get('snapshot'):
        saved=store.snapshot(result['snapshot'],row['question'])
    if saved and result['status']=='ready':
        index,_=engine._index()
        candidates=[{'id':c.film_id,'cosine':c.cosine,'bm25':c.lexical.bm25,'rrf':c.rrf,
            'rerank':saved['scores'].get(c.film_id),'local_admitted':c.admitted,
            'local_reason':c.reason,'rerank_input_index':i}
            for i,c in enumerate(engine._retrieve(index,saved,result).candidates)]
        allowed=local.executor.eligible_ids(SearchPlan.model_validate(saved['hard']),people_ids=saved['people_ids'])['eligible_ids']
        for strategy in ('lexical','dense','hybrid'):
            baseline=index.search(saved['text'],eligible_ids=allowed,query_vector=saved['query_vector'],
                reference_id=saved['reference_id'],mode='exploratory' if saved['mode']=='exploratory' else 'factual',
                stage='admission',strategy=strategy)
            baselines[strategy]={'candidate_ids':[c.film_id for c in baseline.candidates[:20]],
                'displayed_ids':[c.film_id for c in baseline.candidates[:20] if c.admitted]}
    responses=safe_responses(receipts)
    raw_decision=next((r.get('answers') for r in responses if r['purpose']=='decision'),None)
    semantic=result.get('semantic') or {}
    if result['status'] in {'clarify','needs_clarification'}: route='clarify'
    elif semantic.get('reference_id'): route='similar'
    elif result['status']=='keyword': route='lexical'
    elif not semantic and result.get('plan') and result['status']=='ready': route='metadata'
    elif semantic.get('route') in {'semantic','hybrid'}:
        route='semantic_filtered' if SearchPlan.model_validate(result['plan'])!=SearchPlan(version='search-plan.v2') else semantic['route']
    else: route=None
    shared_local=not semantic and result['status'] in {'keyword','ready'}
    ablations={}
    for label,strategy in (('A','lexical'),('B','hybrid')):
        ablations[label]={'ids':baselines[strategy]['displayed_ids'],'available':True} if strategy in baselines else {
            'ids':actual_ids if shared_local else [],'available':shared_local,
            'note':'shared deterministic local fastpath' if shared_local else 'no saved query vector/complete semantic execution; no extra model calls for ablation'}
    ablations['C']={'ids':[c['id'] for c in candidates if c['local_admitted']] if candidates else actual_ids,
        'available':bool(candidates) or shared_local,'note':'same routed candidates, frozen local admission, no native rerank'}
    ablations['D']={'ids':actual_ids,'available':True,'status':result['status'],'fallback':semantic.get('fallback')}
    raw_rank=sorted(candidates,key=lambda c:(c['rerank'] is None,-(c['rerank'] or 0),-c['rrf'],c['id']))
    return {**row,'status':result['status'],'reason':result.get('reason'),'source':result.get('source'),
        'hard_plan':result.get('plan'),'people_ids':result.get('people_ids'),
        'reference_id':semantic.get('reference_id'),'issues':result.get('issues'),
        'semantic':result.get('semantic'),'raw_result':result,'snapshot':result.get('snapshot'),
        'route':route,'route_classification_provisional':True,'actual_internal_route':semantic.get('route'),
        'decision_raw_answers':raw_decision,
        'route_confidence':(raw_decision or {}).get('route',{}).get('confidence'),
        'candidate_ids':[c['id'] for c in candidates],'candidates':candidates,
        'rerank_index_to_id':{str(c['rerank_input_index']):c['id'] for c in candidates},
        'raw_final_rank_ids':[c['id'] for c in raw_rank],'actual_ids':actual_ids,
        'baselines':baselines,'ablations':ablations,
        'stages':{name:stage_state(name,receipts,result,saved) for name in ('decision','query','rerank')},
        'abstention':not actual_ids,'clarification':result['status'] in {'clarify','needs_clarification'},
        'fallback_reason':semantic.get('fallback') or (result.get('reason') if result['status']=='unavailable' else None),
        'pipeline_elapsed_ms':elapsed,'preflight_ms':preflight,'end_to_end_ms':wall,
        'step_timings_ms':dict(engine.timings),'receipts':receipts,'native_responses':responses}


def execute(path,credential_path,*,run_live=False):
    config=configuration()
    if not run_live: return {'status':'frozen-continuation','sha256':config['sha256'],'posts':0}
    rows=execution_questions(path)
    binding={'configuration_sha256':freeze()['sha256'],'execution_questions_sha256':sha256(path.read_bytes()).hexdigest()}
    directory=RUN/'holdout'
    if json.loads((directory/'binding.json').read_text())!=binding: raise SemanticError('search_execution_binding_changed')
    binding.update(infrastructure_sha256=infrastructure_configuration()['sha256'],execution_continuation_sha256=config['sha256'])
    immutable(directory/'continuation-binding.json',binding)
    corpus,films=load_corpus(RUN/'public-holdout-corpus-v1.json'); docs=documents(films)
    query_texts={r['question'] for r in rows}
    query_texts.update(r.text for row in rows if not (r:=split_content_request(row['question'])).issue)
    query_texts.update(t for d in docs for t in d.chunks)
    scope=EgressScope('public-evaluation.v2',frozenset(_hash(t) for d in docs for t in d.chunks),frozenset(_hash(t) for t in query_texts),True)
    ledger=ContinuedBudget(RUN/'shared-budget.sqlite3',authorization(RUN))
    trace=RUN/'transport'; trace.mkdir(exist_ok=True)
    client=SearchProviderClient(ledger,scope,lambda:existing_credential(credential_path),
        session=TraceSession(http_session(),ledger,trace),response_sink=lambda n,p:immutable(RUN/f'response-{n:03}.json',p))
    connection=sqlite3.connect(directory/'index.sqlite3')
    from sqlmodel import create_engine
    from sqlalchemy import inspect
    database_engine=create_engine('sqlite:///'+(directory/'public-library.sqlite3').as_posix())
    outputs=[]
    try:
        if ledger.summary()['halted']: raise SemanticError('search_budget_blocked')
        client.preflight(); native=SearchEmbeddingProvider(client)
        if native.spec!=embedding_spec(): raise SemanticError('search_frozen_model_changed')
        store=SearchIndexStore(connection)
        state=store.begin(docs,native.spec)
        index_embedding=CachedSearchEmbedding(store,SearchEmbeddingProvider(IndexTimeoutClient(client)))
        while state['state']!='complete':
            if ledger.summary()['halted']: raise SemanticError('search_budget_blocked')
            if any(time.monotonic()-checked>240 for _,checked in client.quotes.values()): client.preflight()
            state=store.step(state['id'],index_embedding)
            print(json.dumps({'index_state':state['state'],'remaining_chunks':state['remaining_chunks'],'posts':ledger.summary()['requests']}),flush=True)
        if not inspect(database_engine).get_table_names(): seed_projection_database(database_engine,corpus,films)
        local=LocalSearch(database_engine)
        engine=IntegratedSearch(store,native.spec,local_interpret=local.interpret,known_literal=local.known_literal,
            resolve_hard=local.executor.resolve,eligible=lambda plan,ids:local.executor.eligible_ids(plan,people_ids=ids),
            summaries=local.summaries,corpus_revision=lambda:store.meta('revision'),reference_candidates=local.reference_candidates,
            decision=DecisionProvider(client),embedding=CachedSearchEmbedding(store,native),reranker=RerankProvider(client))
        for row in rows:
            target=directory/(row['id']+'.json')
            if target.exists():
                old=json.loads(target.read_text(encoding='utf-8'))
                if any(old.get(k)!=v for k,v in binding.items()): raise SemanticError('search_execution_binding_changed')
                outputs.append(old); continue
            if ledger.summary()['halted']: break
            before=ledger.summary()['attempts']; wall_start=time.monotonic()
            refresh=any(time.monotonic()-checked>240 for _,checked in client.quotes.values())
            if refresh: client.preflight()
            preflight=(time.monotonic()-wall_start)*1000 if refresh else 0
            start=time.monotonic(); result=engine.submit(row['question']); elapsed=(time.monotonic()-start)*1000
            if result['status']=='keyword':
                ordinary=ProjectionReader().film_page(database_engine,query=keyword_text(row['question']),rank_exact=True)
                actual=[film['id'] for film in ordinary['items']]
            else: actual=[item['film']['id'] for item in (result.get('results') or {}).get('items',[])]
            wall=(time.monotonic()-wall_start)*1000
            receipts=[r for r in ledger.summary()['receipts'] if r['number']>before]
            output={**record_case(row,result,engine,store,local,client,receipts,actual,elapsed,preflight,wall),**binding}
            immutable(target,output); outputs.append(output)
            print(json.dumps({'case_id':row['id'],'status':result['status'],'returned':len(actual),'posts':ledger.summary()['requests']}),flush=True)
        report={'version':'search-holdout-continuation-execution.v1',**binding,
            'evaluation_scope':'infrastructure-change continuation; question text previously revealed; labels not loaded',
            'route_classification_protocol_deviation':True,'labels_not_loaded':True,
            'completed_cases':len(outputs),'results':outputs,'accounting':ledger.summary()}
        filename='execution-report.json' if len(outputs)==60 else f'execution-interrupted-{len(outputs):02}.json'
        immutable(directory/filename,report)
        return {'completed_cases':len(outputs),'posts':report['accounting']['requests'],
            'cost':report['accounting']['reported_cost_usd'],'halted':report['accounting']['halted'],**binding}
    finally:
        connection.close(); database_engine.dispose(); client.close(); ledger.close()


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-live',action='store_true'); parser.add_argument('--execution-queries',type=Path)
    parser.add_argument('--credential-file',type=Path)
    args=parser.parse_args()
    print(json.dumps(execute(args.execution_queries,args.credential_file,run_live=args.run_live)))
