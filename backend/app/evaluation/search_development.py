"""Old public development data only. No independent questions/qrels are opened.

The exact production parser/SQL/routing/retrieval code runs before development
labels are used for diagnostics. Expected hard plans are NEVER injected into the
request. Saved native scores allow offline threshold analysis without API reruns.
"""
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import time

from app.evaluation.public_movie_pilot import SavedVectors, approved_fixture, RUN_ROOT as OLD_RUN
from app.evaluation.public_movies import score
from app.evaluation.search_corpus import load_corpus, seed_projection_database, documents
from app.evaluation.search_integration import RUN, authorization, write_json
from app.evaluation.openrouter_pilot import existing_credential
from app.services.content_request import split_content_request
from app.services.integrated_search import IntegratedSearch, IntegratedSearchPolicy
from app.services.projections import ProjectionReader
from app.services.search_budget import SearchBudget
from app.services.search_index import CachedSearchEmbedding, SearchIndexStore
from app.services.search_local import LocalSearch
from app.services.search_providers import (DECISION, DecisionProvider, EgressScope, RerankProvider,
    SearchEmbeddingProvider, SearchProviderClient)
from app.services.semantic_search import SemanticError, _hash

OLD_VECTOR_SHA = "e389c28c39f965d44ad403515f263488eaa3b18283601c24bab4a1758abd8b0d"


def import_old_vectors(store, spec):
    fixture, _, freeze_id = approved_fixture()
    path = OLD_RUN / "vectors.json"
    if sha256(path.read_bytes()).hexdigest() != OLD_VECTOR_SHA:
        raise SemanticError("search_old_vector_hash_mismatch")
    replay = SavedVectors.replay(fixture, freeze_id, path)
    if replay.spec != spec:
        raise SemanticError("search_old_vector_profile_mismatch")
    for (text, query), vector in replay.memo.items():
        store.remember_vector(text, vector, spec, query=query)
    return len(replay.memo)


class RecordedDevelopmentDecision:
    """Reparse exact recorded dev responses; never fabricate a model answer.

    The request hash includes the unchanged prompt/schema and query. Only a
    settled zero-cost receipt with matching native ID/model/provider is reusable.
    Hidden acceptance questions are never supplied to this development wrapper.
    """
    def __init__(self, client, root):
        self.client, self.used, self.saved = client, [], {}
        for receipt in client.ledger.summary()["receipts"]:
            path = root / f"response-{receipt['number']:03}.json"
            if receipt["purpose"] != "decision" or receipt["state"] != "reported" or receipt["cost"] != "0" or not path.exists():
                continue
            payload = json.loads(path.read_text(encoding="utf-8"))
            evidence = json.loads(receipt["evidence"])
            if (payload.get("id") != evidence.get("id") or payload.get("model") != evidence.get("model")
                    or payload.get("provider") != "BaseTen" or payload.get("usage", {}).get("cost") != 0):
                raise SemanticError("search_development_receipt_mismatch")
            self.saved[receipt["input_hash"]] = (receipt["number"], payload, sha256(path.read_bytes()).hexdigest())

    def request(self, endpoint, body, **options):
        saved = self.saved.get(_hash([body, options["purpose"]])) if endpoint == DECISION else None
        if saved:
            self.client.scope.check(options["texts"], query=True)
            self.used.append({"receipt": saved[0], "response_sha256": saved[2]})
            return options["validate"](saved[1])
        return self.client.request(endpoint, body, **options)


def development(*, credential_path=None, run_live=False, revision="v1"):
    fixture, _, _ = approved_fixture()
    if not run_live:
        return {"status": "offline", "development_cases": len(fixture.cases), "requests": 0}
    from sqlmodel import create_engine
    corpus, films = load_corpus(RUN / "public-holdout-corpus-v1.json")
    # New corpus is available for later indexing. Development stays on the old
    # 24 Films, because their old labels do not judge the 40 new distractors.
    old_ids = {f.id for f in fixture.films}
    films = tuple(f for f in films if f.id in old_ids)
    docs = documents(films)
    queries = {case.question for case in fixture.cases}
    queries.update(request.text for case in fixture.cases
                   if not (request := split_content_request(case.question)).issue)
    queries.update(doc.chunks[0] for doc in docs)  # Public reference content.
    scope = EgressScope("public-evaluation.v2", frozenset(_hash(t) for doc in docs for t in doc.chunks),
                        frozenset(_hash(q) for q in queries), accept_logged_public=True)
    ledger = SearchBudget(RUN / "shared-budget.sqlite3", authorization(RUN))
    client = SearchProviderClient(ledger, scope, lambda: existing_credential(credential_path),
        response_sink=lambda n, p: write_json(RUN / f"response-{n:03}.json", p))
    directory = RUN / ("development" if revision == "v1" else "development-v2")
    directory.mkdir(exist_ok=True)
    backend = Path(__file__).resolve().parents[2]
    source_paths = ("app/services/search_providers.py", "app/services/integrated_search.py",
                    "app/services/content_request.py", "app/services/search_local.py",
                    "app/services/search_execution.py", "app/services/search_rules.py",
                    "app/services/retrieval_policy.py")
    source_hashes = {name: sha256((backend / name).read_text(encoding="utf-8").encode()).hexdigest()
                     for name in source_paths}
    manifest = {"version": "search-development-config.v1", "sources": source_hashes,
                "policy": asdict(IntegratedSearchPolicy()), "scope": "old public 24, development only"}
    manifest_path = directory / "configuration.json"
    if manifest_path.exists() and json.loads(manifest_path.read_text(encoding="utf-8")) != manifest:
        client.close()
        ledger.close()
        raise SemanticError("search_development_configuration_changed")
    write_json(manifest_path, manifest)
    database_engine = create_engine("sqlite://")
    # Model/text-bound cache is append-only reusable work, not a frozen score
    # report. Historical v1 per-case JSON/configuration remain untouched.
    db = sqlite3.connect(RUN / "development" / "index.sqlite3")
    store = SearchIndexStore(db)
    results = []
    try:
        if ledger.summary()["halted"]:
            raise SemanticError("search_budget_blocked")
        client.preflight()
        native = SearchEmbeddingProvider(client)
        reused = import_old_vectors(store, native.spec)
        embedding = CachedSearchEmbedding(store, native)
        state = store.begin(docs, native.spec)
        while state["state"] != "complete":
            state = store.step(state["id"], embedding)
        seed_projection_database(database_engine, corpus, films)
        local = LocalSearch(database_engine)
        recorded = RecordedDevelopmentDecision(client, RUN) if revision == "v2" else None
        engine = IntegratedSearch(store, native.spec, local_interpret=local.interpret,
            known_literal=local.known_literal, resolve_hard=local.executor.resolve,
            eligible=lambda plan, ids: local.executor.eligible_ids(plan, people_ids=ids),
            summaries=local.summaries, corpus_revision=lambda: store.meta("revision"),
            reference_candidates=local.reference_candidates, decision=DecisionProvider(recorded or client),
            embedding=embedding, reranker=RerankProvider(client))
        for case in fixture.cases:
            output = directory / (case.id + ".json")
            if output.exists():
                row = json.loads(output.read_text(encoding="utf-8"))
                results.append(row)
                continue
            if ledger.summary()["halted"]:
                break
            preflight_start = time.monotonic()
            # Quote validation itself enforces a 300-second maximum age. Avoid
            # four redundant public GETs for every local/cached development row.
            refreshed = any(time.monotonic() - checked > 240 for _quote, checked in client.quotes.values())
            if refreshed:
                client.preflight()
            preflight_ms = (time.monotonic() - preflight_start) * 1000 if refreshed else 0
            before = ledger.summary()["requests"]
            start = time.monotonic()
            result = engine.submit(case.question)
            pipeline_ms = (time.monotonic() - start) * 1000
            if result["status"] == "keyword":
                from app.services.discovery_search import keyword_text
                actual = [row["id"] for row in ProjectionReader().list_films(database_engine, keyword_text(case.question))]
            elif result["version"] != "discovery.v3" and result.get("plan") and result["status"] == "ready":
                from app.contracts.bound_search_plan import SearchPlan
                result = local.executor.query(SearchPlan.model_validate(result["plan"]))
                actual = [row["film"]["id"] for row in result["results"]["items"]]
            else:
                actual = [row["film"]["id"] for row in (result.get("results") or {}).get("items", [])]
            candidates = []
            raw_scores = {}
            if result.get("snapshot") and result.get("semantic") and result["status"] == "ready":
                saved = store.snapshot(result["snapshot"], case.question)
                index, _ = engine._index()
                retrieval = engine._retrieve(index, saved, result)
                raw_scores = saved["scores"]
                candidates = [{"id": c.film_id, "cosine": c.cosine, "bm25": c.lexical.bm25,
                    "rrf": c.rrf, "rerank": raw_scores.get(c.film_id), "fallback_admitted": c.admitted}
                    for c in retrieval.candidates]
            row = {"case_id": case.id, "question": case.question, "locale": case.locale, "kind": case.kind,
                "development_not_unseen": True, "status": result["status"], "reason": result.get("reason"),
                "route": (result.get("semantic") or {}).get("route", "local"),
                "mode": (result.get("semantic") or {}).get("mode"), "hard_plan": result.get("plan"),
                "candidate_ids": [c["id"] for c in candidates], "candidates": candidates,
                "actual_ids": actual, "raw_scores": raw_scores,
                "receipt_numbers": list(range(before + 1, ledger.summary()["requests"] + 1)),
                "elapsed_ms": pipeline_ms, "preflight_ms": preflight_ms,
                "end_to_end_server_evaluation_ms": pipeline_ms + preflight_ms,
                "step_timings_ms": engine.timings,
                "diagnostic_scores": score(case, actual)}
            write_json(output, row)
            results.append(row)
            print(json.dumps({"case": case.id, "status": result["status"], "calls": ledger.summary()["requests"]}), flush=True)
            if row["receipt_numbers"]:
                time.sleep(3.2)
        report = {"version": "search-development.v1", "not_independent_acceptance": True,
            "policy": asdict(engine.policy), "policy_hash": engine.policy.fingerprint,
            "reused_verified_vectors": reused, "completed_cases": len(results), "results": results,
            "reparsed_exact_decision_receipts": recorded.used if recorded else [],
            "accounting": ledger.summary()}
        write_json(directory / "report.json", report)
        return {k: report[k] for k in ("completed_cases", "reused_verified_vectors", "policy_hash", "accounting")}
    finally:
        db.close()
        database_engine.dispose()
        client.close()
        ledger.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-live", action="store_true")
    parser.add_argument("--credential-file", type=Path)
    parser.add_argument("--revision", choices=("v1", "v2"), default="v1")
    args = parser.parse_args()
    result = development(credential_path=args.credential_file, run_live=args.run_live, revision=args.revision)
    print(json.dumps({k: v for k, v in result.items() if k != "accounting"}
        | {"accounting": {k: v for k, v in result.get("accounting", {}).items() if k != "receipts"}}))
