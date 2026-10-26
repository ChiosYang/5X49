"""Local-first search orchestration with explicit, restorable model boundaries.

Database access and remote providers are injected. Restoration never accesses
the injected Decision/embedding/rerank providers. All Film IDs are re-intersected
with the current strict SQL plan before ranking, counts and summaries.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import math
import re
import time

from app.contracts.bound_search_plan import SearchPlan
from app.services.content_request import short_keyword, split_content_request
from app.services.retrieval_policy import RetrievalIndex, RetrievalPolicy
from app.services.semantic_search import SemanticError, _hash, _safe, _vector


@dataclass(frozen=True)
class IntegratedSearchPolicy:
    # Native scores are ranking evidence, not probabilities. Calibrate on old
    # development data and freeze before independent questions are revealed.
    factual_min: float = .09
    exploratory_min: float = .04
    reference_min: float = .06
    candidate_k: int = 20

    def __post_init__(self):
        if (type(self.candidate_k) is not int or not 1 <= self.candidate_k <= 20
                or any(type(v) not in (int, float) or not math.isfinite(v) or not 0 < v < 1
                       for v in (self.factual_min, self.exploratory_min, self.reference_min))):
            raise SemanticError("search_policy_invalid")

    @property
    def fingerprint(self):
        return _hash(["integrated-search.v3-reference-focus", asdict(self), RetrievalPolicy(candidate_k=self.candidate_k).fingerprint])


class IntegratedSearch:
    def __init__(self, store, spec, *, local_interpret, known_literal, resolve_hard,
                 eligible, summaries, corpus_revision, reference_candidates,
                 decision=None, embedding=None, reranker=None, policy=None, title_mentions=None):
        self.store, self.spec = store, spec
        self.local_interpret, self.known_literal = local_interpret, known_literal
        self.resolve_hard, self.eligible, self.summaries = resolve_hard, eligible, summaries
        self.current_revision, self.reference_candidates = corpus_revision, reference_candidates
        self.decision, self.embedding, self.reranker = decision, embedding, reranker
        self.title_mentions = title_mentions
        self.policy = policy or IntegratedSearchPolicy()
        self.timings = {}

    def measured(self, name, callback):
        start = time.monotonic()
        try:
            return callback()
        finally:
            self.timings[name] = self.timings.get(name, 0) + (time.monotonic() - start) * 1000

    @staticmethod
    def failure(reason, *, status="unavailable"):
        return {"version": "discovery.v3", "status": status, "source": "local", "reason": reason,
                "plan": None, "person_id": None, "people_ids": {}, "constraints": [], "issues": [], "results": None}

    def _index(self):
        documents, vectors, revision = self.store.read(self.spec, expected_revision=self.current_revision())
        index = RetrievalIndex(documents, vectors, self.spec, RetrievalPolicy(candidate_k=self.policy.candidate_k))
        return index, revision

    def submit(self, question, *, people_ids=None, reference_id=None, edited_plan=None, cancelled=lambda: False):
        self.timings = {}
        _safe(question, 600)
        local = self.measured("local_interpret_ms", lambda: self.local_interpret(question))
        # A complete, catalog-backed literal binding is model-free, including
        # wrappers and exact title qualifiers. No arbitrary sentence truncation.
        if edited_plan is None and (local.get("keyword_query") is not None or self.known_literal(question)
                or local.get("reason") in {"unknown_film", "ambiguous_film"}
                or (local.get("plan") or {}).get("film_ids")):
            return local
        request = split_content_request(question, lookup=self.reference_candidates, mentions=self.title_mentions)
        if not edited_plan and not request.is_content and local.get("plan") and local.get("status") in {"ready", "needs_clarification"}:
            return local
        # Short literal lookup remains model-free. Unrecognized longer requests
        # are eligible for a finite route decision, not free-form filter guessing.
        if edited_plan is None and not request.reference and local.get("status") == "keyword" and short_keyword(question):
            return local
        if request.issue:
            return self.failure(request.issue, status="clarify")
        hard = edited_plan or request.hard
        resolved = self.measured("sql_resolve_ms", lambda: self.resolve_hard(hard, people_ids or {}))
        try:
            index, revision = self.measured("index_read_ms", self._index)
        except SemanticError as exc:
            return self.failure(exc.code)
        payload = {"revision": revision, "spec": self.spec.fingerprint, "policy": self.policy.fingerprint,
                   "text": request.text, "reference_id": None, "query_vector": None,
                   "hard": hard.model_dump(), "people_ids": people_ids or {},
                   "route": "hybrid", "mode": "factual", "scores": {}, "fallback": None,
                   "evaluated": False, "reference_text": request.reference,
                   "reference_focus": request.reference_focus,
                   "edited": edited_plan is not None}
        if request.reference:
            candidates = self.reference_candidates(request.reference)
            chosen = next((row for row in candidates if row["key"] == reference_id), None)
            if chosen is None and reference_id is None and len(candidates) == 1:
                chosen = candidates[0]
            if chosen is None:
                token = self.store.save_snapshot(question, payload)
                return {**self.failure("search_reference_choice", status="needs_clarification"),
                    "plan": hard.model_dump(), "snapshot": token, "constraints": resolved["constraints"],
                    "people_ids": resolved.get("people_ids", {}),
                    "issues": [{"field": "reference", "code": "choose_reference", "candidates": candidates}],
                    "semantic": {"text": request.text, "evaluation_only": True, "requires_submit": True}}
            payload.update(reference_id=chosen["key"], mode="reference")
            if chosen["key"] not in index.documents:
                return self.failure("reference_missing_content", status="clarify")
        if resolved["status"] != "ready":
            token = self.store.save_snapshot(question, payload)
            return {**resolved, "version": "discovery.v3", "snapshot": token,
                    "edited": edited_plan is not None,
                    "semantic": {"text": request.text, "reference_id": payload["reference_id"],
                                 "requires_submit": True, "evaluation_only": True}}
        payload["people_ids"] = resolved.get("people_ids", {})
        try:
            if cancelled():
                return self.failure("search_cancelled")
            if not request.reference:
                if self.decision is None or self.embedding is None:
                    return self.failure("search_not_configured")
                decision = self.measured("decision_ms", lambda: self.decision.decide(request.text))
                if cancelled():
                    return self.failure("search_cancelled")
                if decision.route == "keyword":
                    if hard != SearchPlan(version="search-plan.v2"):
                        return self.failure("search_route_uncertain", status="clarify")
                    return {**local, "status": "keyword", "plan": None}
                if decision.route == "clarify":
                    return self.failure("search_route_uncertain", status="clarify")
                payload.update(route=decision.route, mode=getattr(decision, "mode", "factual"))
                if payload["route"] not in {"semantic", "hybrid"} or payload["mode"] not in {"factual", "exploratory"}:
                    raise SemanticError("search_decision_invalid")
                payload["query_vector"] = list(_vector(self.measured("query_embedding_ms",
                    lambda: self.embedding.embed((request.text,), query=True))[0], self.spec.dimensions))
                if cancelled():
                    return self.failure("search_cancelled")
            retrieval = self.measured("retrieval_ms", lambda: self._retrieve(index, payload, resolved))
            candidates = retrieval.candidates[:self.policy.candidate_k]
            if candidates and self.reranker is not None:
                # The reference vector retrieves content neighbours. When the
                # user names a comparison aspect, rerank those neighbours for
                # that aspect instead of silently asking for whole-plot overlap.
                query = ((payload["reference_focus"] or index.documents[payload["reference_id"]].chunks[0])
                         if payload["reference_id"] else request.text)
                texts = [index.documents[c.film_id].chunks[0] for c in candidates]
                try:
                    if cancelled():
                        return self.failure("search_cancelled")
                    scores = self.measured("rerank_ms", lambda: self.reranker.rank(query, texts))
                    if (len(scores) != len(candidates) or any(type(s) not in (int, float)
                            or not math.isfinite(s) or not 0 <= s <= 1 for s in scores)):
                        raise SemanticError("search_rerank_invalid")
                    payload["scores"] = {c.film_id: s for c, s in zip(candidates, scores)}
                except SemanticError as exc:
                    payload["fallback"] = exc.code
            elif candidates:
                payload["fallback"] = "search_rerank_unavailable"
            if cancelled():
                return self.failure("search_cancelled")
            payload["evaluated"] = True
            token = self.store.save_snapshot(question, payload)
            return self.measured("final_page_ms", lambda: self._page(question, token, payload, hard, resolved, index))
        except SemanticError as exc:
            return self.failure(exc.code)

    def _retrieve(self, index, payload, resolved):
        hard = SearchPlan.model_validate(payload["hard"])
        if payload["reference_id"]:
            hard = hard.model_copy(update={"exclude_film_ids": sorted(set(hard.exclude_film_ids + [payload["reference_id"]]))})
        allowed = self.eligible(hard, payload["people_ids"])
        if isinstance(allowed, dict):
            allowed = allowed["eligible_ids"]
        # Defense in depth for injected callers, cached/native rank data and
        # restorations: a reference can never become its own recommendation.
        allowed = [identifier for identifier in allowed if identifier != payload["reference_id"]
                   and identifier not in hard.exclude_film_ids and (not hard.film_ids or identifier in hard.film_ids)]
        options = dict(eligible_ids=allowed, query_vector=payload["query_vector"],
            reference_id=payload["reference_id"], mode="exploratory" if payload["mode"] == "exploratory" else "factual",
            strategy="dense" if payload["route"] == "semantic" else "hybrid")
        broad = index.search(payload["text"], stage="lexical", **options)
        checked = {c.film_id: c for c in index.search(payload["text"], stage="admission", **options).candidates}
        if payload.get("reference_focus"):
            # No focus vector is fabricated and no extra provider is called.
            # A local fallback must support the explicit aspect as well as the
            # reference; reference cosine alone is not evidence of that aspect.
            focus_ids = set(index.search(payload["reference_focus"], eligible_ids=allowed,
                strategy="lexical", mode="factual", stage="admission").displayed_ids)
            checked = {key: replace(c, admitted=c.admitted and key in focus_ids,
                reason=c.reason if key in focus_ids else "reference_focus_insufficient_evidence")
                for key, c in checked.items()}
        # Admission never reorders or narrows the candidate set seen by native
        # rerank. It remains an independent guard for a disclosed local fallback.
        return replace(broad, candidates=tuple(replace(c, admitted=checked[c.film_id].admitted,
            reason=checked[c.film_id].reason) for c in broad.candidates[:self.policy.candidate_k]))

    def restored_plan(self, question, token, *, plan=None, edited=False):
        """Validate the stored origin before either semantic or SQL-only edits."""
        _safe(question, 600)
        payload = self.store.snapshot(token, question)
        try:
            if (payload["spec"] != self.spec.fingerprint or payload["policy"] != self.policy.fingerprint
                    or payload["mode"] not in {"factual", "exploratory", "reference"}
                    or payload["route"] not in {"semantic", "hybrid"}):
                raise SemanticError("search_snapshot_requires_submit")
            saved_hard = SearchPlan.model_validate(payload["hard"])
            if plan is not None and plan != saved_hard and not edited:
                raise SemanticError("search_snapshot_invalid")
            return payload, plan or saved_hard
        except (KeyError, TypeError, ValueError):
            raise SemanticError("search_snapshot_invalid") from None

    def resume(self, question, token, *, plan=None, people_ids=None, offset=0, order="relevance", edited=False):
        payload, hard = self.restored_plan(question, token, plan=plan, edited=edited)
        try:
            _safe(payload["text"], 600)
            if payload["query_vector"] is not None:
                payload["query_vector"] = list(_vector(payload["query_vector"], self.spec.dimensions))
            resolved = self.resolve_hard(hard, people_ids if people_ids is not None else payload["people_ids"])
            if not payload["evaluated"]:
                # A GET/refresh may reconstruct local choices but cannot finish
                # inference. The next identity choice is an explicit submission.
                result = {**resolved, "version": "discovery.v3", "snapshot": token,
                    "edited": bool(payload.get("edited")),
                    "semantic": {"text": payload["text"], "reference_id": payload["reference_id"],
                                 "evaluation_only": True, "requires_submit": True}}
                if payload.get("reference_text") and not payload["reference_id"]:
                    result.update(status="needs_clarification", reason="search_reference_choice", results=None,
                        issues=[{"field": "reference", "code": "choose_reference",
                                 "candidates": self.reference_candidates(payload["reference_text"])}])
                elif resolved["status"] == "ready":
                    result.update(status="clarify", reason="search_snapshot_requires_submit", results=None)
                return result
            if resolved["status"] != "ready":
                return {**resolved, "version": "discovery.v3", "snapshot": token,
                        "semantic": {"text": payload["text"], "evaluation_only": True}}
            payload = {**payload, "hard": hard.model_dump(), "people_ids": resolved.get("people_ids", {})}
            index, revision = self._index()
            if revision != payload["revision"]:
                raise SemanticError("search_snapshot_stale")
            # All paths below are local: rerank is NEVER repeated on restoration,
            # filter edits, mutations, paging or a newer navigation committing.
            return self._page(question, token, payload, hard, resolved, index, offset=offset, order=order)
        except (KeyError, TypeError, ValueError):
            raise SemanticError("search_snapshot_invalid") from None

    def _page(self, question, token, payload, hard, resolved, index, *, offset=0, order="relevance"):
        if self.current_revision() != payload["revision"]:
            raise SemanticError("search_snapshot_stale")
        if type(offset) is not int or offset < 0 or offset > 1000000 or order not in {"relevance", "title", "year"}:
            raise SemanticError("search_page_invalid")
        retrieval = self._retrieve(index, payload, resolved)
        scores = payload["scores"]
        if (not isinstance(scores, dict) or any(key not in index.documents or type(score) not in (int, float)
                or not math.isfinite(score) or not 0 <= score <= 1 for key, score in scores.items())):
            raise SemanticError("search_snapshot_invalid")
        threshold = getattr(self.policy, payload["mode"] + "_min")
        candidates = {c.film_id: c for c in retrieval.candidates}
        ranked = [
            c.film_id for c in retrieval.candidates if c.film_id != payload["reference_id"]
            and c.film_id not in hard.exclude_film_ids and (not hard.film_ids or c.film_id in hard.film_ids)
            if (scores[c.film_id] >= threshold if c.film_id in scores else c.admitted)]
        ranked.sort(key=lambda key: (key not in scores, -scores.get(key, 0), -candidates[key].rrf, key))
        summaries = self.summaries(ranked)
        ranked = [key for key in ranked if key in summaries]
        if order != "relevance":
            value = (lambda key: summaries[key].get("year")) if order == "year" else (lambda key: summaries[key].get("title", "").casefold())
            known = [key for key in ranked if value(key) is not None]
            known.sort(key=lambda key: (value(key), key), reverse=hard.direction == "desc")
            ranked = known + sorted(key for key in ranked if value(key) is None)
        total, limit = len(ranked), 40
        offset = min(offset, max(0, (total - 1) // limit * limit))
        page_ids = ranked[offset:offset + limit]
        uncovered = any(c.film_id not in scores for c in retrieval.candidates)
        result = {**resolved, "version": "discovery.v3", "status": "ready", "source": "ai", "snapshot": token,
            "edited": bool(payload.get("edited")),
            "semantic": {"text": payload["text"], "reference_id": payload["reference_id"],
                "route": payload["route"], "mode": payload["mode"], "order": order,
                "fallback": payload["fallback"] or ("search_cached_local_ranking" if uncovered else None),
                "evaluation_only": True, "indexed_films": len(index.documents),
                "bounded_candidates": self.policy.candidate_k},
            "results": {"visibility_policy": "strict-current-sql", "strict": True,
                "projection_version": "semantic-search.v1", "projection_versions": {},
                "active_filters": {"genre": [], "person": [], "country": [], "decade": [],
                    "view": hard.view, "sort": hard.sort, "dir": hard.direction, "person_match": "all"},
                "filters": [], "unresolved_filters": [],
                "items": [{"film": summaries[key], "matched_facts": []} for key in page_ids],
                "total": total, "limit": limit, "offset": offset,
                "next_offset": offset + len(page_ids) if offset + len(page_ids) < total else None}}
        return result
