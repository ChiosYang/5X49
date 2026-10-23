"""Explicit, incremental search indexing in a disposable caller-owned database.

No source database, filesystem scan, model loading or provider call on import.
Each acknowledged embedding batch is durable. The active generation changes
atomically only after the full requested corpus has been encoded and validated.
"""
from __future__ import annotations

from dataclasses import asdict
import json
import sqlite3
import struct
import time
from uuid import uuid4

from app.services.semantic_search import (ContentDocument, ContentSource, ProviderSpec,
    SemanticError, _embed, _hash, _safe, _vector, corpus_revision, MAX_DOCUMENTS)

VERSION = "search-index.v1"
TABLES = {"search_index_meta", "search_index_vectors", "search_index_jobs", "search_index_work",
          "search_index_active", "search_query_snapshots", "search_query_vectors"}


def encode_document(document):
    # Public metadata only is a caller-side extraction/egress requirement. These
    # type/path/chunk checks are an additional boundary, not a PII classifier.
    corpus_revision((document,))
    chunks = document.chunks
    return json.dumps({"film_id": document.film_id, "title": document.title,
        "aliases": document.aliases, "sources": [asdict(s) for s in document.sources],
        "chunks": chunks, "digest": document.digest}, ensure_ascii=False, allow_nan=False)


def decode_document(raw):
    try:
        payload = json.loads(raw)
        doc = ContentDocument(payload["film_id"], payload["title"], tuple(payload["aliases"]),
            tuple(ContentSource(**s) for s in payload["sources"]))
        if doc.digest != payload["digest"] or list(doc.chunks) != payload["chunks"]:
            raise ValueError
        return doc
    except (KeyError, ValueError, TypeError):
        raise SemanticError("search_index_invalid") from None


class SearchIndexStore:
    def __init__(self, connection: sqlite3.Connection, *, clock=time.time):
        self.db, self.clock = connection, clock
        self.db.row_factory = sqlite3.Row
        existing = {r[0] for r in self.db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        if existing - TABLES:
            raise SemanticError("search_index_not_owned")
        self.db.execute("PRAGMA synchronous=FULL")
        with self.db:
            self.db.execute("CREATE TABLE IF NOT EXISTS search_index_meta (key TEXT PRIMARY KEY,value TEXT NOT NULL)")
            self.db.execute("""CREATE TABLE IF NOT EXISTS search_index_vectors (
                fingerprint TEXT NOT NULL,text_hash TEXT NOT NULL,text TEXT NOT NULL,vector BLOB NOT NULL,
                PRIMARY KEY(fingerprint,text_hash))""")
            self.db.execute("""CREATE TABLE IF NOT EXISTS search_index_jobs (
                id TEXT PRIMARY KEY,revision TEXT NOT NULL,fingerprint TEXT NOT NULL,state TEXT NOT NULL,
                cancel_requested INTEGER NOT NULL DEFAULT 0,created REAL NOT NULL,error TEXT)""")
            self.db.execute("""CREATE TABLE IF NOT EXISTS search_index_work (
                job_id TEXT NOT NULL,film_id TEXT NOT NULL,document TEXT NOT NULL,
                PRIMARY KEY(job_id,film_id))""")
            self.db.execute("CREATE TABLE IF NOT EXISTS search_index_active (film_id TEXT PRIMARY KEY,document TEXT NOT NULL)")
            self.db.execute("""CREATE TABLE IF NOT EXISTS search_query_snapshots (
                id TEXT PRIMARY KEY,query_hash TEXT NOT NULL,payload TEXT NOT NULL,expires REAL NOT NULL)""")
            self.db.execute("""CREATE TABLE IF NOT EXISTS search_query_vectors (
                fingerprint TEXT NOT NULL,text_hash TEXT NOT NULL,vector BLOB NOT NULL,
                PRIMARY KEY(fingerprint,text_hash))""")
        if self.meta("version") not in (None, VERSION):
            raise SemanticError("search_index_version")

    def meta(self, key):
        row = self.db.execute("SELECT value FROM search_index_meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    def begin(self, documents, spec: ProviderSpec):
        revision = corpus_revision(documents)
        if not isinstance(spec, ProviderSpec):
            raise SemanticError("invalid_provider_spec")
        encoded = [(doc.film_id, encode_document(doc)) for doc in documents]
        if self.meta("revision") == revision and self.meta("fingerprint") == spec.fingerprint:
            return {"id": None, "state": "complete", "revision": revision, "remaining_chunks": 0}
        with self.db:
            job = self.db.execute("SELECT id FROM search_index_jobs WHERE revision=? AND fingerprint=?"
                " AND state IN ('pending','paused','working') ORDER BY created DESC LIMIT 1",
                (revision, spec.fingerprint)).fetchone()
            if job:
                return self.status(job[0], spec)
            identifier = "idx_" + uuid4().hex
            self.db.execute("INSERT INTO search_index_jobs (id,revision,fingerprint,state,created) VALUES (?,?,?,'pending',?)",
                            (identifier, revision, spec.fingerprint, self.clock()))
            self.db.executemany("INSERT INTO search_index_work VALUES (?,?,?)",
                               [(identifier, film_id, raw) for film_id, raw in encoded])
        return self.status(identifier, spec)

    def _job(self, identifier, spec):
        row = self.db.execute("SELECT * FROM search_index_jobs WHERE id=?", (identifier,)).fetchone()
        if row is None or row["fingerprint"] != spec.fingerprint:
            raise SemanticError("search_index_job_missing")
        return row

    def _work(self, identifier):
        rows = self.db.execute("SELECT document FROM search_index_work WHERE job_id=? ORDER BY film_id", (identifier,)).fetchall()
        if len(rows) > MAX_DOCUMENTS:
            raise SemanticError("corpus_limit")
        return tuple(decode_document(row[0]) for row in rows)

    def _missing(self, documents, spec):
        texts = dict.fromkeys(text for doc in documents for text in doc.chunks)
        return [text for text in texts if not self.db.execute(
            "SELECT 1 FROM search_index_vectors WHERE fingerprint=? AND text_hash=?",
            (spec.fingerprint, _hash(text))).fetchone()]

    def status(self, identifier, spec):
        job = self._job(identifier, spec)
        work = self._work(identifier)
        return {"id": identifier, "state": job["state"], "revision": job["revision"],
                "total_films": len(work), "remaining_chunks": len(self._missing(work, spec)),
                "cancel_requested": bool(job["cancel_requested"]), "error": job["error"]}

    def cancel(self, identifier, spec):
        job = self._job(identifier, spec)
        with self.db:
            self.db.execute("UPDATE search_index_jobs SET cancel_requested=1,state=? WHERE id=?",
                            ("working" if job["state"] == "working" else "cancelled", identifier))

    def resume(self, identifier, spec):
        job = self._job(identifier, spec)
        if job["state"] == "working":
            # A killed/in-flight provider is never assumed not to have run.
            raise SemanticError("search_index_job_busy")
        if job["state"] not in {"cancelled", "paused"}:
            raise SemanticError("search_index_job_not_paused")
        with self.db:
            self.db.execute("UPDATE search_index_jobs SET state='pending',cancel_requested=0,error=NULL WHERE id=?", (identifier,))
        return self.status(identifier, spec)

    def step(self, identifier, provider, *, batch_size=4, cancelled=lambda: False):
        if type(batch_size) is not int or not 1 <= batch_size <= 4:
            raise SemanticError("search_index_batch_limit")
        spec = provider.spec
        try:
            self.db.execute("BEGIN IMMEDIATE")
            job = self._job(identifier, spec)
            if job["state"] not in {"pending", "paused"}:
                raise SemanticError("search_index_job_busy")
            if job["cancel_requested"] or cancelled():
                self.db.execute("UPDATE search_index_jobs SET state='cancelled' WHERE id=?", (identifier,))
                self.db.commit()
                return self.status(identifier, spec)
            self.db.execute("UPDATE search_index_jobs SET state='working' WHERE id=?", (identifier,))
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        try:
            documents = self._work(identifier)
            if corpus_revision(documents) != job["revision"]:
                raise SemanticError("search_index_invalid")
            missing = self._missing(documents, spec)
            batch = missing[:batch_size]
            if batch:
                vectors = _embed(provider, batch, query=False)
                with self.db:
                    self.db.executemany("INSERT OR REPLACE INTO search_index_vectors VALUES (?,?,?,?)",
                        [(spec.fingerprint, _hash(text), text, struct.pack("<" + "f" * spec.dimensions, *vector))
                         for text, vector in zip(batch, vectors)])
            # Persist returned vectors even if cancellation happened in flight;
            # resume reuses them rather than paying/dispatching for them again.
            cancel = bool(self._job(identifier, spec)["cancel_requested"]) or cancelled()
            remaining = self._missing(documents, spec)
            with self.db:
                if cancel:
                    state = "cancelled"
                elif remaining:
                    state = "paused"
                else:
                    self.db.execute("DELETE FROM search_index_active")
                    self.db.execute("INSERT INTO search_index_active SELECT film_id,document FROM search_index_work WHERE job_id=?", (identifier,))
                    self.db.executemany("INSERT OR REPLACE INTO search_index_meta VALUES (?,?)",
                        [("version", VERSION), ("revision", job["revision"]), ("fingerprint", spec.fingerprint)])
                    state = "complete"
                self.db.execute("UPDATE search_index_jobs SET state=? WHERE id=?", (state, identifier))
            return self.status(identifier, spec)
        except Exception as exc:
            code = exc.code if isinstance(exc, SemanticError) else "search_index_failed"
            with self.db:
                self.db.execute("UPDATE search_index_jobs SET state='paused',error=? WHERE id=?", (code, identifier))
            raise SemanticError(code) from None

    def read(self, spec: ProviderSpec, *, expected_revision=None):
        revision = self.meta("revision")
        if self.meta("fingerprint") != spec.fingerprint or not revision or expected_revision and revision != expected_revision:
            raise SemanticError("search_index_stale")
        documents = tuple(decode_document(row[0]) for row in self.db.execute(
            "SELECT document FROM search_index_active ORDER BY film_id"))
        if corpus_revision(documents) != revision:
            raise SemanticError("search_index_invalid")
        vectors = {}
        for doc in documents:
            values = []
            for chunk in doc.chunks:
                row = self.db.execute("SELECT text,vector FROM search_index_vectors WHERE fingerprint=? AND text_hash=?",
                                      (spec.fingerprint, _hash(chunk))).fetchone()
                if row is None or row["text"] != chunk:
                    raise SemanticError("search_index_invalid")
                _safe(row["text"], 512)
                try:
                    values.append(_vector(list(struct.unpack("<" + "f" * spec.dimensions, row["vector"])), spec.dimensions))
                except (ValueError, TypeError, struct.error):
                    raise SemanticError("search_index_invalid") from None
            vectors[doc.film_id] = _vector([sum(v[i] for v in values) for i in range(spec.dimensions)], spec.dimensions)
        return documents, vectors, revision

    def save_snapshot(self, question, payload, *, ttl=86400):
        _safe(question, 600)
        if type(ttl) is not int or not 60 <= ttl <= 86400:
            raise SemanticError("search_snapshot_limit")
        token = "ds_" + uuid4().hex
        raw = json.dumps(payload, ensure_ascii=False, allow_nan=False, sort_keys=True)
        if len(raw) > 512 * 1024:
            raise SemanticError("search_snapshot_limit")
        now = self.clock()
        with self.db:
            self.db.execute("DELETE FROM search_query_snapshots WHERE expires<=?", (now,))
            self.db.execute("DELETE FROM search_query_snapshots WHERE id IN (SELECT id FROM search_query_snapshots ORDER BY expires DESC,id LIMIT -1 OFFSET 99)")
            self.db.execute("INSERT INTO search_query_snapshots VALUES (?,?,?,?)", (token, _hash(question), raw, now + ttl))
        return token

    def snapshot(self, token, question):
        _safe(question, 600)
        import re
        if not isinstance(token, str) or not re.fullmatch(r"ds_[0-9a-f]{32}", token):
            raise SemanticError("search_snapshot_invalid")
        row = self.db.execute("SELECT * FROM search_query_snapshots WHERE id=?", (token,)).fetchone()
        if row is None or row["expires"] <= self.clock():
            raise SemanticError("search_snapshot_expired")
        if row["query_hash"] != _hash(question):
            raise SemanticError("search_snapshot_invalid")
        try:
            return json.loads(row["payload"])
        except (ValueError, TypeError):
            raise SemanticError("search_snapshot_invalid") from None

    def remember_vector(self, text, values, spec, *, query):
        _safe(text, 600 if query else 512)
        vector = _vector(values, spec.dimensions)
        packed = struct.pack("<" + "f" * spec.dimensions, *vector)
        with self.db:
            if query:
                self.db.execute("INSERT OR REPLACE INTO search_query_vectors VALUES (?,?,?)",
                                (spec.fingerprint, _hash(text), packed))
            else:
                self.db.execute("INSERT OR REPLACE INTO search_index_vectors VALUES (?,?,?,?)",
                                (spec.fingerprint, _hash(text), text, packed))

    def cached_vector(self, text, spec, *, query):
        _safe(text, 600 if query else 512)
        table = "search_query_vectors" if query else "search_index_vectors"
        row = self.db.execute(f"SELECT vector FROM {table} WHERE fingerprint=? AND text_hash=?",
                              (spec.fingerprint, _hash(text))).fetchone()
        if not row:
            return None
        try:
            return _vector(list(struct.unpack("<" + "f" * spec.dimensions, row[0])), spec.dimensions)
        except (ValueError, TypeError, struct.error):
            raise SemanticError("search_index_invalid") from None


class CachedSearchEmbedding:
    """Exact provider/mode/text cache; never invent or approximate an encoding."""
    def __init__(self, store, provider):
        self.store, self.provider, self.spec = store, provider, provider.spec

    def embed(self, texts, *, query):
        if type(query) is not bool or not isinstance(texts, (list, tuple)) or not texts:
            raise SemanticError("search_embedding_limit")
        values = [self.store.cached_vector(text, self.spec, query=query) for text in texts]
        missing = list(dict.fromkeys(text for text, vector in zip(texts, values) if vector is None))
        if missing:
            vectors = _embed(self.provider, missing, query=query)
            for text, vector in zip(missing, vectors):
                self.store.remember_vector(text, vector, self.spec, query=query)
        return [self.store.cached_vector(text, self.spec, query=query) for text in texts]
