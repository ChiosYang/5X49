"""Opt-in INTERNAL EVALUATION wiring for the existing Explore routes.

Absent both explicit host environment switches, this module is inert. The free
NVIDIA trial adapters cannot serve an ordinary/private production instance. A
manifest binds approved public documents, query hashes, index and shared budget.
No credentials are written to the manifest or looked up on restore/fast paths.
"""
from __future__ import annotations

from contextlib import contextmanager
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
from urllib.parse import urlsplit

from sqlmodel import Session, select

from app.canonical_models import Film

from app.contracts.bound_search_plan import SearchPlan
from app.services.content_request import short_keyword, split_content_request
from app.services.integrated_search import IntegratedSearch, IntegratedSearchPolicy
from app.services.search_budget import SearchAuthorization, SearchBudget
from app.services.search_index import CachedSearchEmbedding, SearchIndexStore, decode_document
from app.services.search_local import LocalSearch
from app.services.search_providers import (DECISION, EMBEDDING, RERANK, DecisionProvider, EgressScope,
    RerankProvider, SearchEmbeddingProvider, SearchProviderClient, embedding_spec)
from app.services.semantic_search import SemanticError, _hash, _safe, corpus_revision


class EvaluationRuntime:
    def __init__(self, manifest, engine, *, provider_factory=SearchProviderClient):
        if (not isinstance(manifest, dict) or manifest.get("version") != "search-evaluation-runtime.v1"
                or manifest.get("internal_evaluation_only") is not True
                or manifest.get("scope") not in {"public-evaluation.v2", "persistent-test-library.v1"}
                or manifest.get("nvidia_public_logging_accepted") is not True
                or manifest.get("models") != [e.model for e in (DECISION, EMBEDDING, RERANK)]):
            raise SemanticError("search_evaluation_config_invalid")
        self.config, self.provider_factory = manifest, provider_factory
        self.local = LocalSearch(engine)
        self.spec = embedding_spec(manifest.get("embedding_created", 1792591666))
        self.policy = IntegratedSearchPolicy(**manifest.get("policy", {}))
        self.documents = tuple(decode_document(json.dumps(doc, ensure_ascii=False)) for doc in manifest["documents"])
        if (not self.documents or len(self.documents) > (64 if manifest["scope"] == "public-evaluation.v2" else 15)
                or corpus_revision(self.documents) != manifest["revision"]):
            raise SemanticError("search_evaluation_config_invalid")
        if any(s.origin not in {"tmdb", "rule"} or s.kind != "overview"
               for document in self.documents for s in document.sources):
            raise SemanticError("search_public_source_required")
        self._verify_provenance()
        self.scope = EgressScope(manifest["scope"], frozenset(_hash(text) for d in self.documents for text in d.chunks),
                                frozenset(manifest["query_hashes"]), accept_logged_public=True)
        # These are host-owned cache/authorization locations, never API inputs.
        self.index_path = Path(manifest["index_path"])
        self.ledger_path = Path(manifest["ledger_path"])
        self.authorization = SearchAuthorization(**manifest["authorization"])
        if (not self.index_path.is_absolute() or not self.ledger_path.is_absolute()
                or self.index_path.resolve() == self.ledger_path.resolve()
                or engine.url.database and self.index_path.resolve() == Path(engine.url.database).resolve()
                or engine.url.database and self.ledger_path.resolve() == Path(engine.url.database).resolve()):
            raise SemanticError("search_evaluation_config_invalid")

    def _verify_provenance(self):
        proof = self.config.get("provenance", {})
        if self.config["scope"] == "public-evaluation.v2":
            # The corpus-only package was independently reviewed and hash-bound.
            # No library scalar, private edit or arbitrary host document can be
            # substituted under the public-evaluation grant.
            from app.evaluation.search_corpus import load_corpus, documents
            try:
                path = Path(proof["corpus_path"])
                if not path.is_absolute():
                    raise ValueError
                _, films = load_corpus(path)
                allowed = {d.film_id: d.digest for d in documents(films)}
                if any(allowed.get(d.film_id) != d.digest for d in self.documents):
                    raise ValueError
            except (KeyError, TypeError, ValueError):
                raise SemanticError("search_public_source_required") from None
        elif (proof.get("version") != "reviewed-public-fields.v1"
                or proof.get("reviewed") is not True
                or not isinstance(proof.get("films"), dict)
                or set(proof["films"]) != {d.film_id for d in self.documents}):
            raise SemanticError("search_public_source_required")
        self.current_revision()  # Verify source bindings before any provider.

    def current_revision(self):
        if self.config["scope"] == "persistent-test-library.v1":
            # Historical scalar columns lack field-level provenance. Only exact
            # values independently checked against public sources are eligible.
            # A change invalidates the whitelist; it never auto-exports new text.
            proofs = self.config["provenance"]["films"]
            with Session(self.local.engine) as session:
                rows = {row.id: row for row in session.exec(select(Film).where(Film.id.in_(proofs))).all()}
                for document in self.documents:
                    row, proof = rows.get(document.film_id), proofs[document.film_id]
                    if row is None or row.lifecycle_status != "active" or not isinstance(proof, dict):
                        raise SemanticError("search_source_changed")
                    # Only automatic scalar fields, never overrides, notes,
                    # paths, profile records or opaque edition payloads.
                    fields = proof.get("fields", {})
                    if not fields or set(fields) - {"canonical_title", "original_title", "overview"}:
                        raise SemanticError("search_public_source_required")
                    values = []
                    for field, evidence in fields.items():
                        text = getattr(row, field)
                        try:
                            url = urlsplit(evidence["source"])
                            if (url.scheme != "https" or not url.hostname or url.username or url.password
                                    or not isinstance(text, str)
                                    or sha256(text.encode()).hexdigest() != evidence["sha256"]):
                                raise ValueError
                        except (TypeError, KeyError, ValueError):
                            raise SemanticError("search_source_changed") from None
                        _safe(text, 10000)
                        values.append(text)
                    if (document.title not in values or any(alias not in values for alias in document.aliases)
                            or any(source.text not in values for source in document.sources)):
                        raise SemanticError("search_public_source_required")
        return corpus_revision(self.documents)

    @contextmanager
    def search(self, *, remote=False, cancelled=lambda: False):
        db = sqlite3.connect(self.index_path)
        resources = []
        runtime = self

        class LazyProviders:
            spec = runtime.spec

            def __init__(self):
                self.client = None

            def get(self):
                if cancelled():
                    raise SemanticError("search_cancelled")
                if self.client is None:
                    ledger = SearchBudget(runtime.ledger_path, runtime.authorization)
                    resources.append(ledger)
                    self.client = runtime.provider_factory(ledger, runtime.scope,
                        lambda: os.getenv("OPENROUTER_API_KEY"))
                    self.client.cancelled = cancelled
                    resources.append(self.client)
                    self.client.preflight()
                    if SearchEmbeddingProvider(self.client).spec != runtime.spec:
                        raise SemanticError("search_index_stale")
                return self.client

            def decide(self, query):
                return DecisionProvider(self.get()).decide(query)

            def embed(self, texts, *, query):
                return SearchEmbeddingProvider(self.get()).embed(texts, query=query)

            def rank(self, query, docs):
                return RerankProvider(self.get()).rank(query, docs)

        providers = LazyProviders() if remote else None
        try:
            store = SearchIndexStore(db)
            yield IntegratedSearch(store, self.spec, local_interpret=self.local.interpret,
                known_literal=self.local.known_literal, resolve_hard=self.local.executor.resolve,
                eligible=lambda plan, ids: self.local.executor.eligible_ids(plan, people_ids=ids),
                summaries=self.local.summaries, corpus_revision=self.current_revision,
                reference_candidates=self.local.reference_candidates,
                decision=providers, embedding=CachedSearchEmbedding(store, providers) if providers else None,
                reranker=providers, policy=self.policy, title_mentions=self.local.title_mentions)
        finally:
            for resource in reversed(resources):
                resource.close()
            db.close()

    def index(self, request):
        self.current_revision()
        with self.search(remote=request.action == "step") as search:
            store = search.store
            if request.action == "begin":
                return store.begin(self.documents, self.spec)
            if not request.job_id:
                raise SemanticError("search_index_job_missing")
            if request.action == "step":
                return store.step(request.job_id, search.embedding)
            if request.action == "resume":
                return store.resume(request.job_id, self.spec)
            if request.action == "cancel":
                store.cancel(request.job_id, self.spec)
            return store.status(request.job_id, self.spec)

    def interpret(self, request, *, cancelled=lambda: False):
        _safe(request.question, 600)
        local = self.local.interpret(request.question)
        segmented = split_content_request(request.question, lookup=self.local.reference_candidates, mentions=self.local.title_mentions)
        if not request.edited_plan and (local.get("keyword_query") is not None or self.local.known_literal(request.question)
                or local.get("reason") in {"unknown_film", "ambiguous_film"}
                or (local.get("plan") or {}).get("film_ids")
                or not segmented.is_content and local.get("plan") and local["status"] in {"ready", "needs_clarification"}
                or local["status"] == "keyword" and short_keyword(request.question)):
            if local.get("plan") and request.people_ids:
                return self.local.executor.query(SearchPlan.model_validate(local["plan"]), people_ids=request.people_ids)
            return local
        if not request.allow_ai:
            return IntegratedSearch.failure("submit_to_interpret", status="needs_ai")
        with self.search(remote=True, cancelled=cancelled) as search:
            return search.submit(request.question, people_ids=request.people_ids,
                                 reference_id=request.reference_id, edited_plan=request.edited_plan, cancelled=cancelled)

    def query(self, request):
        if not request.semantic_snapshot:
            raise SemanticError("search_snapshot_invalid")
        if not isinstance(request.plan, SearchPlan):
            raise SemanticError("search_snapshot_invalid")
        with self.search() as search:
            if request.semantic_removed:
                # The raw question remains for display/history, while this
                # explicit edit removes content matching only. The opaque token
                # still proves the validated original request; every retained
                # factual condition and identity goes through current strict SQL.
                payload, hard = search.restored_plan(request.question, request.semantic_snapshot,
                    plan=request.plan, edited=request.edited)
                if payload["revision"] != self.current_revision():
                    raise SemanticError("search_snapshot_stale")
                return self.local.executor.query(hard, people_ids=request.people_ids, offset=request.offset)
            return search.resume(request.question, request.semantic_snapshot, plan=request.plan,
                people_ids=request.people_ids, offset=request.offset, order=request.semantic_order, edited=request.edited)


def configured_evaluation(engine):
    if os.getenv("SEARCH_INTERNAL_EVALUATION") != "1":
        return None
    filename = os.getenv("SEARCH_EVALUATION_MANIFEST")
    if not filename:
        raise SemanticError("search_evaluation_config_invalid")
    try:
        path = Path(filename)
        if not path.is_absolute() or path.stat().st_size > 512 * 1024:
            raise ValueError
        return EvaluationRuntime(json.loads(path.read_text(encoding="utf-8")), engine)
    except SemanticError:
        raise
    except Exception:
        raise SemanticError("search_evaluation_config_invalid") from None
