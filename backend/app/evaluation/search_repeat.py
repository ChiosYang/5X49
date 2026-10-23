"""One newly authorized repeat of request50; no automatic subsequent calls."""
from hashlib import sha256
import json
from pathlib import Path
import sqlite3

from app.evaluation.openrouter_pilot import existing_credential
from app.evaluation.search_holdout import freeze
from app.evaluation.search_integration import RUN,authorization,write_json
from app.evaluation.search_recovery import ContinuedBudget,IndexTimeoutClient,TraceSession
from app.services.openrouter_embeddings import http_session
from app.services.search_index import CachedSearchEmbedding,SearchIndexStore
from app.services.search_providers import EgressScope,SearchEmbeddingProvider,SearchProviderClient,embedding_spec
from app.services.semantic_search import SemanticError,_hash

ORIGINAL_NUMBER=50
ORIGINAL_HASH='afd315c96b95f625ef36d71aa18746ddb2e166306f06488111495d6218e2de28'


def configuration():
    original=freeze()
    backend=Path(__file__).resolve().parents[2]
    names=('app/evaluation/search_recovery.py','app/evaluation/search_repeat.py')
    config={'version':'holdout-infrastructure-continuation.v1',
        'original_configuration_sha256':original['sha256'],
        'original_source_manifest_sha256':_hash(original['configuration']['sources']),
        'changes':{'document_timeout_seconds':[20,60],
            'explicit_single_repeat':{'unknown_number':ORIGINAL_NUMBER,'input_hash':ORIGINAL_HASH},
            'safe_transport_event_timestamps':True},
        'unchanged':{'query_embedding_timeout_seconds':20,'decision_timeout_seconds':5,
            'rerank_timeout_seconds':10,'index_batch_chunks':4,
            'models_prompts_parser_SQL_candidate_K_admission_ordering':'original hash-bound implementation'},
        'scope':'infrastructure-change continuation; questions revealed,0/60 executed at authorization',
        'route_mapping':'post-reveal provisional classification; original enum implementation was pre-frozen',
        'sources':{name:sha256((backend/name).read_text(encoding='utf-8').encode()).hexdigest() for name in names}}
    envelope={'configuration':config,'sha256':_hash(config)}
    path=RUN/'holdout-infrastructure-continuation.v1.json'
    if path.exists() and json.loads(path.read_text(encoding='utf-8'))!=envelope:
        raise SemanticError('search_continuation_configuration_changed')
    if not path.exists(): write_json(path,envelope)
    return envelope


def repeat(credential_path,*,run_live=False):
    config=configuration()
    if not run_live: return {'status':'frozen-infrastructure-only','sha256':config['sha256'],'posts':0}
    ledger=ContinuedBudget(RUN/'shared-budget.sqlite3',authorization(RUN))
    connection=sqlite3.connect(RUN/'holdout'/'index.sqlite3')
    client=None
    try:
        raw=ledger.db.execute('SELECT number,state,input_hash FROM search_budget_receipts ORDER BY number').fetchall()
        if len(raw)!=50 or raw[-1]['number']!=ORIGINAL_NUMBER or raw[-1]['state']!='uncertain':
            raise SemanticError('search_repeat_already_attempted_or_ledger_changed')
        store=SearchIndexStore(connection)
        job=connection.execute('SELECT id FROM search_index_jobs ORDER BY created DESC LIMIT1'.replace('LIMIT1','LIMIT 1')).fetchone()[0]
        docs=store._work(job)
        texts=store._missing(docs,embedding_spec())[:4]
        body={'input':list(texts),'encoding_format':'float','input_type':'passage'}
        if len(texts)!=4 or _hash([body,'document'])!=ORIGINAL_HASH:
            raise SemanticError('search_repeat_input_mismatch')
        scope=EgressScope('public-evaluation.v2',frozenset(_hash(t) for d in docs for t in d.chunks),frozenset(),True)
        trace=RUN/'transport'; trace.mkdir(exist_ok=True)
        client=SearchProviderClient(ledger,scope,lambda:existing_credential(credential_path),
            session=TraceSession(http_session(),ledger,trace),
            response_sink=lambda n,p:write_json(RUN/f'response-{n:03}.json',p))
        client.preflight()
        native=SearchEmbeddingProvider(IndexTimeoutClient(client))
        if native.spec!=embedding_spec(): raise SemanticError('search_frozen_model_changed')
        ledger.authorize_repeat(ORIGINAL_NUMBER,ORIGINAL_HASH)
        state=store.step(job,CachedSearchEmbedding(store,native))
        linked=ledger.complete_repeat(store,native.spec,texts)
        summary=ledger.summary()
        receipt=summary['receipts'][-1]
        result={'status':'repeat-success','continuation_sha256':config['sha256'],'linked':linked,
            'original_receipt_unchanged':summary['receipts'][49]['state']=='uncertain',
            'original_usage_and_cost_still_unknown':True,'posts':summary['requests'],
            'new_elapsed_ms':receipt['elapsed_ms'],'new_evidence':json.loads(receipt['evidence']),
            'remaining_chunks':state['remaining_chunks'],'accounting':summary}
        write_json(RUN/'holdout'/'repeat-completion.json',result)
        return {k:v for k,v in result.items() if k!='accounting'}
    finally:
        if client: client.close()
        connection.close(); ledger.close()


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-live',action='store_true')
    parser.add_argument('--credential-file',type=Path)
    args=parser.parse_args()
    print(json.dumps(repeat(args.credential_file,run_live=args.run_live)))
