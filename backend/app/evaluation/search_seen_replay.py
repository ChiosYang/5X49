"""Read-only replay after the failed assessment; never a new blind evaluation.

Only byte-equivalent model request bodies and exact cached vectors may be
reused. Missing evidence is recorded as unverified. This module has no key
supplier, HTTP client, retry, ledger write or live execution option.
"""
from dataclasses import asdict
from contextlib import closing
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import time

from app.evaluation.search_holdout import SOURCES, execution_questions
from app.evaluation.search_integration import RUN, write_json
from app.services.integrated_search import IntegratedSearch, IntegratedSearchPolicy
from app.services.projections import ProjectionReader
from app.services.search_index import SearchIndexStore
from app.services.search_local import LocalSearch
from app.services.search_providers import DECISION, RERANK, ENDPOINTS, DecisionProvider, RerankProvider, embedding_spec
from app.services.semantic_search import SemanticError, _hash

ORIGINAL = "f3286a9dc2a0c432347e4b35e673762c65129dac1452ba4ca28b56e693d39f79"


class RecordedClient:
    def __init__(self, receipts, responses):
        self.receipts, self.responses = receipts, responses
        self.events = []

    def request(self, endpoint, body, *, purpose, validate, **_unused):
        if {"decision": DECISION, "rerank": RERANK}.get(purpose) != endpoint:
            raise SemanticError("search_replay_endpoint_mismatch")
        digest = _hash([body, purpose])
        matches = [r for r in self.receipts if r["purpose"] == purpose
                   and r["input_hash"] == digest and r["state"] == "reported"
                   and r["scope"] == "public-evaluation.v2"
                   and r["number"] in self.responses]
        event = {"purpose": purpose, "model": endpoint.model, "wire_body_sha256": digest,
                 "verified_recording": False, "new_requests": 0}
        self.events.append(event)
        if not matches:
            raise SemanticError("search_replay_missing_response")
        row = matches[0]
        response = self.responses[row["number"]]
        evidence = json.loads(row["evidence"])
        aliases = {endpoint.model}
        if endpoint == DECISION:
            aliases.update({"baseten/mammoth-1-20261021", "baseten/mammoth-1-20261021:free"})
        if endpoint == RERANK:
            aliases.add("nvidia/nemotron-3.5-rerank-8b")
        if (not evidence.get("id") or any(response.get(k) != evidence.get(k) for k in ("id", "model", "provider"))
                or response.get("model") not in aliases
                or response.get("provider") not in {endpoint.provider_name, endpoint.provider}
                or Decimal(row["cost"]) != 0 or response.get("usage", {}).get("cost") != 0
                or any(response.get("usage", {}).get(k) != v for k, v in evidence.get("usage", {}).items())):
            raise SemanticError("search_replay_evidence_mismatch")
        value = validate(response)
        event.update(verified_recording=True, original_receipt=row["number"],
                     response_sha256=_hash(response), request_id=evidence["id"])
        return value


class RecordedEmbedding:
    def __init__(self, store, spec):
        self.store, self.spec, self.events = store, spec, []

    def embed(self, texts, *, query):
        vectors = [self.store.cached_vector(text, self.spec, query=query) for text in texts]
        self.events.extend({"purpose": "query" if query else "document", "text_sha256": _hash(text),
            "verified_recording": vector is not None, "new_requests": 0} for text, vector in zip(texts, vectors))
        if any(vector is None for vector in vectors):
            raise SemanticError("search_replay_missing_vector")
        return vectors


def source_configuration():
    backend = Path(__file__).resolve().parents[2]
    names = (*SOURCES, "app/services/search_literals.py", "app/contracts/bound_search_plan.py", "app/evaluation/search_seen_replay.py")
    value = {"version": "search-seen-regression.v4", "independent_acceptance": False,
        "original_configuration_sha256": ORIGINAL, "new_requests": 0,
        "policy": asdict(IntegratedSearchPolicy()), "policy_sha256": IntegratedSearchPolicy().fingerprint,
        "models": [asdict(e) for e in ENDPOINTS], "embedding": asdict(embedding_spec()),
        "evidence": "exact saved request bodies and provider/text/mode vector cache only",
        "sources": {name: sha256((backend / name).read_text(encoding="utf8").encode()).hexdigest() for name in names}}
    return {"configuration": value, "sha256": _hash(value)}


def _read_only(path):
    connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    connection.execute("PRAGMA query_only=ON")
    return connection


def replay(root=RUN):
    from sqlmodel import create_engine
    frozen = source_configuration()
    original = json.loads((root / "holdout-configuration.v3.json").read_text(encoding="utf8"))
    if (original["sha256"] != ORIGINAL or _hash(original["configuration"]) != ORIGINAL
            or original["configuration"]["models"] != [asdict(e) for e in ENDPOINTS]
            or original["configuration"]["embedding"] != asdict(embedding_spec())):
        raise SemanticError("search_original_evidence_changed")
    inputs = root / "execution-queries.v2.json"
    rows = execution_questions(inputs)
    report = json.loads((root / "holdout/execution-report.json").read_text(encoding="utf8"))
    if report["execution_questions_sha256"] != sha256(inputs.read_bytes()).hexdigest():
        raise SemanticError("search_original_evidence_changed")
    before = sha256((root / "shared-budget.sqlite3").read_bytes()).hexdigest()
    with closing(_read_only(root / "shared-budget.sqlite3")) as ledger:
        ledger.row_factory = sqlite3.Row
        receipts = [dict(row) for row in ledger.execute("SELECT * FROM search_budget_receipts ORDER BY number")]
    original_receipts = {r["number"]: r for row in report["results"] for r in row["receipts"]}
    recorded = [r for r in receipts if r["number"] in original_receipts]
    if any(row != original_receipts[row["number"]] for row in recorded):
        raise SemanticError("search_replay_evidence_mismatch")
    responses = {r["number"]: json.loads(path.read_text(encoding="utf8")) for r in recorded
                 if (path := root / f"response-{r['number']:03}.json").is_file()}
    client = RecordedClient(recorded, responses)
    memory = sqlite3.connect(":memory:")
    with closing(_read_only(root / "holdout/index.sqlite3")) as source:
        source.backup(memory)
    store = SearchIndexStore(memory)
    spec = embedding_spec()
    embedding = RecordedEmbedding(store, spec)
    database = root / "holdout/public-library.sqlite3"
    engine = create_engine("sqlite:///file:" + database.resolve().as_posix() + "?mode=ro&uri=true")
    local = LocalSearch(engine)
    search = IntegratedSearch(store, spec, local_interpret=local.interpret,
        known_literal=local.known_literal, resolve_hard=local.executor.resolve,
        eligible=lambda plan, ids: local.executor.eligible_ids(plan, people_ids=ids),
        summaries=local.summaries, corpus_revision=lambda: store.meta("revision"),
        reference_candidates=local.reference_candidates, title_mentions=local.title_mentions,
        decision=DecisionProvider(client), embedding=embedding, reranker=RerankProvider(client))
    target = root / ("seen-regression-v4-" + frozen["sha256"][:16])
    target.mkdir(exist_ok=False)
    write_json(target / "configuration.json", frozen)
    outputs = []
    try:
        for row in rows:
            client.events, embedding.events = [], []
            start = time.monotonic()
            result = search.submit(row["question"])
            if result["status"] == "keyword":
                ordinary = ProjectionReader().film_page(engine,
                    query=result.get("keyword_query") or row["question"], rank_exact=True)
                identifiers = [film["id"] for film in ordinary["items"]]
            else:
                identifiers = [item["film"]["id"] for item in (result.get("results") or {}).get("items", [])]
            events = [*client.events, *embedding.events]
            output = {"id": row["id"], "status": result["status"], "reason": result.get("reason"),
                "keyword_query": result.get("keyword_query"), "plan": result.get("plan"),
                "semantic": result.get("semantic"), "issues": result.get("issues"),
                "actual_ids": identifiers, "recorded_events": events,
                "model_replay_complete": bool(events) and all(e["verified_recording"] for e in events),
                "local_only": not events, "elapsed_ms_local_replay": (time.monotonic() - start) * 1000,
                "new_requests": 0, "independent_acceptance": False}
            write_json(target / (row["id"] + ".json"), output)
            outputs.append(output)
        if sha256((root / "shared-budget.sqlite3").read_bytes()).hexdigest() != before:
            raise SemanticError("search_original_evidence_changed")
        result = {"version": "search-seen-regression.v4", "configuration_sha256": frozen["sha256"],
            "original_failed_assessment_unchanged": True, "independent_acceptance": False,
            "questions_sha256": sha256(inputs.read_bytes()).hexdigest(), "new_requests": 0,
            "existing_unknown_receipts": [r["number"] for r in receipts if r["state"] == "uncertain"],
            "known_reported_cost_usd": str(sum((Decimal(r["cost"]) for r in receipts if r["state"] == "reported"), Decimal(0))),
            "total_cost_finalized": False, "results": outputs}
        write_json(target / "report.json", result)
        return {"directory": str(target), "sha256": sha256((target / "report.json").read_bytes()).hexdigest(),
                "cases": len(outputs), "new_requests": 0, "configuration_sha256": frozen["sha256"]}
    finally:
        memory.close()
        engine.dispose()


if __name__ == "__main__":
    from unittest.mock import patch
    with patch("socket.socket.connect", side_effect=AssertionError("Replay forbids network")), patch(
            "requests.sessions.Session.request", side_effect=AssertionError("Replay forbids HTTP")):
        print(json.dumps(replay(), ensure_ascii=False))
