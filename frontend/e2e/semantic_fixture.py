"""Synthetic native transport inside the owned E2E database. Never production."""
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import threading
from uuid import uuid4

from sqlmodel import Session, select

from app.canonical_models import Film, LibraryFilmReadModel
from app.services.content_request import split_content_request
from app.services.search_index import SearchIndexStore, encode_document
from app.services.search_providers import (DECISION, EMBEDDING, RERANK, ENDPOINTS,
    SearchProviderClient)
from app.services.search_runtime import EvaluationRuntime
from app.services.semantic_search import ContentDocument, ContentSource, _hash, corpus_revision
from test_search_providers import Transport, Response, metadata, zdr

runtime = None
calls = []
gate = threading.Event()
gate.set()
hold_stage = None
failure_stage = None


class NativeFixtureTransport(Transport):
    def get(self, url, **options):
        if url.endswith("/endpoints/zdr"):
            return Response(zdr())
        endpoint = next(e for e in ENDPOINTS if e.model in url)
        payload = metadata(endpoint)
        payload["data"]["created"] = 1792591666
        return Response(payload)

    def post(self, url, **options):
        endpoint = next(e for e in ENDPOINTS if url.endswith(e.api_path))
        stage = "decision" if endpoint == DECISION else "embedding" if endpoint == EMBEDDING else "rerank"
        calls.append(stage)
        if hold_stage == stage and not gate.wait(30):
            raise RuntimeError("Synthetic stage expired")
        if failure_stage == stage:
            raise RuntimeError("Synthetic provider failure")
        response = super().post(url, **options)
        if endpoint == RERANK:
            for item in response.payload["results"]:
                item["relevance_score"] = .95 - .015 * item["index"]
        return response


class NativeFixtureClient(SearchProviderClient):
    def __init__(self, ledger, scope, _unused_key_supplier):
        super().__init__(ledger, scope, lambda: "synthetic-not-a-real-key", session=NativeFixtureTransport())


def configure(root, engine, payload):
    global runtime, calls, hold_stage, failure_stage
    assert root.name.startswith("5x49-e2e-") and (root / ".owned").exists()
    assert Path(engine.url.database).resolve().is_relative_to(root)
    gate.set()
    if payload.get("release"):
        hold_stage = None
        return {"calls": calls}
    runtime, calls = None, []
    hold_stage, failure_stage = payload.get("hold"), payload.get("failure")
    if not payload.get("enabled"):
        return {"calls": calls}
    documents, proofs = [], {}
    with Session(engine) as session:
        rows = session.exec(select(Film).join(LibraryFilmReadModel, Film.id == LibraryFilmReadModel.film_id)
            .where(LibraryFilmReadModel.visible.is_(True)).order_by(Film.id).limit(12)).all()
        for row in rows:
            # Only the generated fixture's automatic scalars. No source writes,
            # personal fields, source paths, credentials or external network.
            if not row.overview:
                continue
            document = ContentDocument(row.id, row.canonical_title, (),
                (ContentSource("overview", row.overview, "rule"),))
            documents.append(document)
            proofs[row.id] = {"fields": {key: {"sha256": sha256(value.encode()).hexdigest(),
                "source": "https://example.com/public-synthetic-fixture"}
                for key, value in (("canonical_title", row.canonical_title), ("overview", row.overview))}}
    directory = root / ("semantic-fixture-" + uuid4().hex)
    directory.mkdir()
    questions = set(payload.get("queries", []))
    questions.update(r.text for q in tuple(questions) if not (r := split_content_request(q)).issue)
    questions.update(t for d in documents for t in d.chunks)
    manifest = {"version": "search-evaluation-runtime.v1", "internal_evaluation_only": True,
        "scope": "persistent-test-library.v1", "nvidia_public_logging_accepted": True,
        "models": [e.model for e in (DECISION, EMBEDDING, RERANK)],
        "documents": [json.loads(encode_document(d)) for d in documents], "revision": corpus_revision(documents),
        "query_hashes": [_hash(q) for q in questions], "index_path": str(directory / "index.db"),
        "ledger_path": str(directory / "receipts.db"),
        "authorization": {"identifier": "synthetic-browser-evaluation", "max_posts": 320,
            "limit_usd": "0", "expires": 2000000000},
        "provenance": {"version": "reviewed-public-fields.v1", "reviewed": True, "films": proofs}}
    runtime = EvaluationRuntime(manifest, engine, provider_factory=NativeFixtureClient)
    connection = sqlite3.connect(runtime.index_path)
    try:
        store = SearchIndexStore(connection)
        for document in documents:
            for text in document.chunks:
                store.remember_vector(text, [1.] + [0.] * 4095, runtime.spec, query=False)
        state = store.begin(documents, runtime.spec)
        class AlreadyEncoded:
            spec = runtime.spec
            def embed(self, *_a, **_k):
                raise AssertionError("Fixture document vectors are already present")
        store.step(state["id"], AlreadyEncoded())
    finally:
        connection.close()
    if hold_stage:
        gate.clear()
    return {"calls": calls, "indexed_films": len(documents),
            "films": [{"id": d.film_id, "title": d.title,
                       "year": next(r.release_year for r in rows if r.id == d.film_id)} for d in documents]}
