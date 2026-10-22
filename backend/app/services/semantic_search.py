"""Offline semantic retrieval foundation. No production wiring or network adapter.

The caller explicitly supplies a dedicated cache connection, current corpus,
validated hard-filter IDs and a provider. Nothing indexes or loads a model on
import/startup. Synthetic providers test contracts, not semantic model quality.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
import re
import sqlite3
import struct
import time
from typing import Protocol, Sequence
from uuid import uuid4

from app.contracts.structured_metadata import normalize_metadata_text
from app.services.search_privacy import has_private_input

POLICY = "semantic-cache.offline.v1"
MAX_DOCUMENTS = 5000
MAX_SNAPSHOTS = 100
CHUNK_CHARS = 512
MAX_CHUNKS = 4
FILM_ID = re.compile(r"film_[0-9a-f]{32}")


class SemanticError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)  # Never expose provider errors or source content.


def _hash(value) -> str:
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":")).encode()).hexdigest()


def _safe(text: str, maximum: int) -> str:
    if not isinstance(text, str) or not text.strip() or len(text) > maximum:
        raise SemanticError("invalid_text")
    # Screen the full original before normalization or excerpt truncation.
    if has_private_input(text):
        raise SemanticError("private_input")
    try:
        text.encode("utf-8")
    except UnicodeError:
        raise SemanticError("invalid_text") from None
    return text.strip()


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    revision: str
    dimensions: int

    def __post_init__(self):
        if (not isinstance(self.name, str) or not re.fullmatch(r"[\w./:-]{1,120}", self.name)
                or not isinstance(self.revision, str) or not re.fullmatch(r"[\w.:-]{1,100}", self.revision)
                or type(self.dimensions) is not int or not 1 <= self.dimensions <= 4096):
            raise SemanticError("invalid_provider_spec")

    @property
    def fingerprint(self):
        return _hash([POLICY, self.name, self.revision, self.dimensions, CHUNK_CHARS, MAX_CHUNKS])


class EmbeddingProvider(Protocol):
    spec: ProviderSpec

    def embed(self, texts: Sequence[str], *, query: bool) -> Sequence[Sequence[float]]: ...


class Reranker(Protocol):
    def rank(self, query: str, documents: Sequence[str]) -> Sequence[float]: ...


@dataclass(frozen=True)
class ContentSource:
    kind: str
    text: str
    origin: str

    def __post_init__(self):
        if not isinstance(self.kind, str) or self.kind not in {"overview", "reviewed_theme"}:
            raise SemanticError("invalid_source")
        if not isinstance(self.origin, str) or self.origin not in {"library", "user", "nfo", "tmdb", "rule", "analysis_run"}:
            raise SemanticError("invalid_source")
        _safe(self.text, 10000)


@dataclass(frozen=True)
class ContentDocument:
    film_id: str
    title: str
    aliases: tuple[str, ...]
    sources: tuple[ContentSource, ...]

    def __post_init__(self):
        if not isinstance(self.film_id, str) or not FILM_ID.fullmatch(self.film_id):
            raise SemanticError("invalid_identity")
        _safe(self.title, 300)
        if (not isinstance(self.aliases, tuple) or not isinstance(self.sources, tuple)
                or any(not isinstance(s, ContentSource) for s in self.sources)):
            raise SemanticError("invalid_source")
        if (len(self.aliases) > 40 or len(self.sources) > 30
                or sum(len(s.text) for s in self.sources) > 20000):
            raise SemanticError("content_limit")
        for alias in self.aliases:
            _safe(alias, 300)
        if not self.sources:
            raise SemanticError("missing_content")

    @property
    def chunks(self):
        # Titles alone never become similarity vectors. Each included component
        # keeps its source label; reviewed themes remain interpretations.
        text = "\n".join(f"{s.kind}: {s.text}" for s in self.sources)
        return tuple(text[i:i + CHUNK_CHARS] for i in range(0, min(len(text),
                     CHUNK_CHARS * MAX_CHUNKS), CHUNK_CHARS))

    @property
    def digest(self):
        return _hash([self.film_id, self.title, self.aliases,
                      [(s.kind, s.text, s.origin) for s in self.sources]])

    @property
    def source_labels(self):
        return sorted({f"{s.kind}:{s.origin}" for s in self.sources})


def corpus_revision(documents: Sequence[ContentDocument]):
    if len(documents) > MAX_DOCUMENTS:
        raise SemanticError("corpus_limit")
    if any(not isinstance(d, ContentDocument) for d in documents):
        raise SemanticError("invalid_document")
    identities = [d.film_id for d in documents]
    if len(identities) != len(set(identities)):
        raise SemanticError("duplicate_identity")
    return _hash(sorted((d.film_id, d.digest) for d in documents))


def _vector(values, dimensions: int):
    if not isinstance(values, (list, tuple)) or len(values) != dimensions:
        raise SemanticError("invalid_vector")
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in values):
        raise SemanticError("invalid_vector")
    norm = math.hypot(*values)
    if not norm or not math.isfinite(norm):
        raise SemanticError("invalid_vector")
    return tuple(float(v / norm) for v in values)


def _embed(provider, texts, *, query):
    for text in texts:
        _safe(text, CHUNK_CHARS * MAX_CHUNKS + MAX_CHUNKS)
    try:
        raw = provider.embed(tuple(texts), query=query)
        if not isinstance(raw, (list, tuple)) or len(raw) != len(texts):
            raise SemanticError("invalid_vector")
        return [_vector(v, provider.spec.dimensions) for v in raw]
    except SemanticError:
        raise
    except Exception:
        raise SemanticError("provider_unavailable") from None


def _tokens(text):
    text = re.sub(r"(?m)^(?:overview|reviewed_theme):\s*", "", text)
    text = normalize_metadata_text(text)
    words = re.findall(r"[a-z0-9]+", text)
    for run in re.findall(r"[\u3400-\u9fff\u3040-\u30ff]+", text):
        words.extend(run[i:i + 2] for i in range(max(1, len(run) - 1)))
    return set(words) - {"a", "an", "the", "and", "or", "of", "in", "on", "with", "to", "from"}


def _eligible(values):
    if (not isinstance(values, (list, tuple, set, frozenset)) or len(values) > MAX_DOCUMENTS
            or any(not isinstance(i, str) or not FILM_ID.fullmatch(i) for i in values)):
        raise SemanticError("invalid_eligible_ids")
    return set(values)


class SemanticCache:
    """A caller-owned, disposable SQLite cache; never a canonical connection."""
    def __init__(self, connection: sqlite3.Connection):
        self.db = connection
        tables = {row[0] for row in self.db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        if tables - {"semantic_meta", "semantic_documents", "semantic_snapshots"}:
            raise SemanticError("cache_not_owned")
        with self.db:
            self.db.execute("CREATE TABLE IF NOT EXISTS semantic_meta (key TEXT PRIMARY KEY,value TEXT NOT NULL)")
            self.db.execute("""CREATE TABLE IF NOT EXISTS semantic_documents (
                film_id TEXT PRIMARY KEY,digest TEXT NOT NULL,document TEXT NOT NULL,vector BLOB NOT NULL)""")
            self.db.execute("""CREATE TABLE IF NOT EXISTS semantic_snapshots (
                id TEXT PRIMARY KEY,query_hash TEXT NOT NULL,revision TEXT NOT NULL,
                fingerprint TEXT NOT NULL,created REAL NOT NULL,expires REAL NOT NULL,ranked TEXT NOT NULL)""")
        if self.value("policy") not in (None, POLICY):
            raise SemanticError("cache_version")

    def value(self, key):
        row = self.db.execute("SELECT value FROM semantic_meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    def replace(self, documents: Sequence[ContentDocument], provider: EmbeddingProvider | None):
        revision = corpus_revision(documents)
        if provider is None:
            raise SemanticError("not_configured")
        spec = provider.spec
        same_model = self.value("fingerprint") == spec.fingerprint
        existing = {row[0]: row[1:] for row in self.db.execute(
            "SELECT film_id,digest,vector FROM semantic_documents")} if same_model else {}
        prepared = []
        for document in documents:
            old = existing.get(document.film_id)
            if old and old[0] == document.digest:
                packed = old[1]
            else:
                chunks = document.chunks
                vectors = _embed(provider, chunks, query=False)  # <=4 bounded excerpts.
                mean = _vector([sum(v[i] for v in vectors) for i in range(spec.dimensions)], spec.dimensions)
                packed = struct.pack("<" + "f" * spec.dimensions, *mean)
            payload = {"title": document.title, "aliases": document.aliases,
                       "chunks": document.chunks, "sources": document.source_labels}
            prepared.append((document.film_id, document.digest, json.dumps(payload, ensure_ascii=False), packed))
        # All input and provider output validated before replacing a usable cache.
        with self.db:
            self.db.execute("DELETE FROM semantic_documents")
            self.db.executemany("INSERT INTO semantic_documents VALUES (?,?,?,?)", prepared)
            self.db.executemany("INSERT OR REPLACE INTO semantic_meta VALUES (?,?)",
                [("policy", POLICY), ("fingerprint", spec.fingerprint), ("revision", revision)])
        return revision

    def documents(self, spec):
        if self.value("fingerprint") != spec.fingerprint:
            raise SemanticError("index_stale")
        rows = self.db.execute("SELECT film_id,document,vector FROM semantic_documents ORDER BY film_id").fetchall()
        if len(rows) > MAX_DOCUMENTS:
            raise SemanticError("corpus_limit")
        result = {}
        for film_id, raw, packed in rows:
            try:
                vector = _vector(list(struct.unpack("<" + "f" * spec.dimensions, packed)), spec.dimensions)
                payload = json.loads(raw)
                if (not isinstance(payload, dict) or set(payload) != {"title", "aliases", "chunks", "sources"}
                        or not isinstance(payload["aliases"], list) or len(payload["aliases"]) > 40
                        or not isinstance(payload["chunks"], list) or not 1 <= len(payload["chunks"]) <= MAX_CHUNKS
                        or not isinstance(payload["sources"], list) or not 1 <= len(payload["sources"]) <= 30):
                    raise ValueError("Invalid cached content")
                _safe(payload["title"], 300)
                for alias in payload["aliases"]:
                    _safe(alias, 300)
                for chunk in payload["chunks"]:
                    _safe(chunk, CHUNK_CHARS)
                # Validate the complete transport text as well as each chunk.
                # Fragmented restored data must not reconstruct a private path.
                _safe(" ".join(payload["chunks"]), CHUNK_CHARS * MAX_CHUNKS + MAX_CHUNKS)
                valid_labels = {f"{kind}:{origin}" for kind in ("overview", "reviewed_theme")
                                for origin in ("library", "user", "nfo", "tmdb", "rule", "analysis_run")}
                if any(label not in valid_labels for label in payload["sources"]):
                    raise ValueError("Invalid cached source")
            except (ValueError, TypeError, struct.error):
                raise SemanticError("index_invalid") from None
            result[film_id] = (payload, vector)
        return result

    def snapshot(self, query_hash, ranked, *, revision, fingerprint, now, ttl):
        if not 60 <= ttl <= 86400 or len(ranked) > MAX_DOCUMENTS:
            raise SemanticError("snapshot_limit")
        token = "ss_" + uuid4().hex
        with self.db:
            if self.value("revision") != revision or self.value("fingerprint") != fingerprint:
                raise SemanticError("index_stale")
            self.db.execute("DELETE FROM semantic_snapshots WHERE expires<=?", (now,))
            self.db.execute("""DELETE FROM semantic_snapshots WHERE id IN
                (SELECT id FROM semantic_snapshots ORDER BY created DESC,id LIMIT -1 OFFSET ?)""", (MAX_SNAPSHOTS - 1,))
            self.db.execute("INSERT INTO semantic_snapshots VALUES (?,?,?,?,?,?,?)",
                (token, query_hash, revision, fingerprint,
                 now, now + ttl, json.dumps(ranked)))
        return token


class SemanticSearch:
    """Structured offline retrieval; this is not a natural-language interpreter."""
    def __init__(self, cache: SemanticCache, spec: ProviderSpec, *, provider=None,
                 reranker=None, minimum_similarity=.35, strategy="hybrid", clock=time.time):
        if (type(minimum_similarity) not in (int, float) or not math.isfinite(minimum_similarity)
                or not -1 <= minimum_similarity <= 1):
            raise SemanticError("invalid_threshold")
        if not isinstance(strategy, str) or strategy not in {"dense", "lexical", "hybrid"}:
            raise SemanticError("invalid_strategy")
        self.cache, self.spec, self.provider = cache, spec, provider
        self.reranker, self.threshold, self.clock = reranker, minimum_similarity, clock
        self.strategy = strategy

    def _intent_hash(self, text, reference_id):
        return _hash([text, reference_id, self.strategy, self.threshold])

    @staticmethod
    def reference_candidates(title, identities):
        # identities come from the existing exact-title read model, not vectors.
        wanted = normalize_metadata_text(_safe(title, 200))
        return sorted({film_id for film_id, names in identities.items()
                       if any(normalize_metadata_text(n) == wanted for n in names)})

    def submit(self, text, *, eligible_ids, expected_revision, reference_id=None):
        text = _safe(text, 600)
        if self.cache.value("revision") != expected_revision:
            raise SemanticError("index_stale")
        documents = self.cache.documents(self.spec)
        eligible = _eligible(eligible_ids)
        query_hash = self._intent_hash(text, reference_id)
        if not eligible:
            token = self.cache.snapshot(query_hash, [], revision=expected_revision,
                fingerprint=self.spec.fingerprint, now=self.clock(), ttl=86400)
            return self.resume(token, text, eligible_ids=eligible,
                expected_revision=expected_revision, reference_id=reference_id)
        if not documents:
            raise SemanticError("missing_content")
        if reference_id is not None:
            if reference_id not in documents:
                raise SemanticError("reference_missing_content")
            vector = documents[reference_id][1]
            topic = " ".join(documents[reference_id][0]["chunks"])
        elif self.strategy != "lexical":
            if self.provider is None:
                raise SemanticError("not_configured")
            if self.provider.spec != self.spec:
                raise SemanticError("index_stale")
            vector = _embed(self.provider, [text], query=True)[0]
            topic = text
        else:
            vector, topic = None, text
        words = _tokens(topic)
        cosine = {}
        lexical = {}
        for film_id, (document, candidate) in documents.items():
            if film_id == reference_id:
                continue
            score = sum(a * b for a, b in zip(vector, candidate)) if vector is not None else -1
            shared = len(words & _tokens(" ".join(document["chunks"])))
            if self.strategy != "lexical" and score >= self.threshold:
                cosine[film_id] = score
            if self.strategy != "dense" and shared:
                lexical[film_id] = shared
        # RRF combines independent lists; do not pretend the score is probability.
        scores = {}
        for ranking in (cosine, lexical):
            for position, film_id in enumerate(sorted(ranking, key=lambda i: (-ranking[i], i)), 1):
                scores[film_id] = scores.get(film_id, 0) + 1 / (60 + position)
        ranked = sorted(scores, key=lambda i: (-scores[i], i))
        if self.reranker is not None:
            candidates = [i for i in ranked if i in eligible][:20]
            if candidates:
                safe_topic = _safe(topic, CHUNK_CHARS * MAX_CHUNKS + MAX_CHUNKS)
                safe_documents = [_safe(" ".join(documents[i][0]["chunks"]),
                    CHUNK_CHARS * MAX_CHUNKS + MAX_CHUNKS) for i in candidates]
                try:
                    values = self.reranker.rank(safe_topic, safe_documents)
                    if (not isinstance(values, (list, tuple)) or len(values) != len(candidates)
                            or any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1 for v in values)):
                        raise SemanticError("invalid_rerank")
                except SemanticError:
                    raise
                except Exception:
                    raise SemanticError("reranker_unavailable") from None
                reranked = sorted(zip(candidates, values), key=lambda item: (-item[1], item[0]))
                ordered = iter([i for i, _ in reranked])
                ranked = [next(ordered) if i in candidates else i for i in ranked]
        token = self.cache.snapshot(query_hash, ranked, revision=expected_revision,
                                   fingerprint=self.spec.fingerprint, now=self.clock(), ttl=86400)
        return self.resume(token, text, eligible_ids=eligible, expected_revision=expected_revision,
                           reference_id=reference_id)

    def resume(self, token, text, *, eligible_ids, expected_revision, reference_id=None, offset=0):
        text = _safe(text, 600)
        if not isinstance(token, str) or not re.fullmatch(r"ss_[0-9a-f]{32}", token):
            raise SemanticError("invalid_snapshot")
        if type(offset) is not int or not 0 <= offset <= 100000:
            raise SemanticError("invalid_offset")
        if self.cache.value("revision") != expected_revision:
            raise SemanticError("index_stale")
        row = self.cache.db.execute("""SELECT query_hash,revision,fingerprint,expires,ranked
            FROM semantic_snapshots WHERE id=?""", (token,)).fetchone()
        if row is None or row[3] <= self.clock():
            raise SemanticError("snapshot_expired")
        if row[0] != self._intent_hash(text, reference_id):
            raise SemanticError("snapshot_mismatch")
        if row[1] != expected_revision or row[2] != self.spec.fingerprint:
            raise SemanticError("snapshot_stale")
        documents = self.cache.documents(self.spec)
        eligible = _eligible(eligible_ids)
        try:
            saved = json.loads(row[4])
            if (not isinstance(saved, list) or len(saved) > MAX_DOCUMENTS
                    or len(saved) != len(set(saved))
                    or any(not isinstance(i, str) or not FILM_ID.fullmatch(i) for i in saved)):
                raise ValueError("Invalid cached identities")
        except (ValueError, TypeError):
            raise SemanticError("snapshot_invalid") from None
        ranked = [i for i in saved if i in eligible and i in documents and i != reference_id]
        total, limit = len(ranked), 40
        offset = min(offset, max(0, (total - 1) // limit * limit))
        return {"mode": "offline-contract", "real_model_quality_verified": False,
                "strategy": self.strategy,
                "snapshot_id": token, "total": total, "limit": limit, "offset": offset,
                "next_offset": offset + limit if offset + limit < total else None,
                "items": [{"film_id": i, "match_kind": "content_relevance",
                           "sources": documents[i][0]["sources"]} for i in ranked[offset:offset + limit]]}
