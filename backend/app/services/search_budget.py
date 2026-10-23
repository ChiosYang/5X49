"""A separate, shared, fail-closed receipt ledger for approved search calls.

No credentials or input text are stored. Opening this class is explicit; it does
not touch the canonical database or any previous experiment's receipts.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import json
from pathlib import Path
import re
import sqlite3
import time
from threading import Lock
from weakref import WeakValueDictionary

from app.services.openrouter_embeddings import _decimal
from app.services.search_privacy import has_private_input
from app.services.semantic_search import SemanticError, _hash

_LOCKS = WeakValueDictionary()
_LOCK_GUARD = Lock()


@dataclass(frozen=True)
class SearchAuthorization:
    identifier: str
    max_posts: int
    limit_usd: str
    expires: int

    def __post_init__(self):
        if (not isinstance(self.identifier, str)
                or not re.fullmatch(r"[a-zA-Z0-9_.-]{8,100}", self.identifier)
                or type(self.max_posts) is not int or not 1 <= self.max_posts <= 320
                or not 0 <= _decimal(self.limit_usd) <= Decimal("3")
                or type(self.expires) is not int or self.expires <= 0):
            raise SemanticError("search_authorization_invalid")

    @property
    def fingerprint(self):
        return _hash([self.identifier, self.max_posts, self.limit_usd, self.expires])


class SearchBudget:
    """SQLite serializes reservations across threads/processes and restart.

    There is one ledger for Decision, document/query embeddings and reranking,
    across public and library validation. An uncertain attempt blocks every
    subsequent dispatch. A different directory is not a way to resume a grant:
    the runtime owns one configured ledger path for the entire authorization.
    """
    def __init__(self, path: Path, authorization: SearchAuthorization, *, clock=time.time):
        self.authorization, self.clock = authorization, clock
        with _LOCK_GUARD:
            key = str(Path(path).resolve()).casefold()
            self.dispatch_lock = _LOCKS.setdefault(key, Lock())
        self.db = sqlite3.connect(path, timeout=5)
        self.db.row_factory = sqlite3.Row
        tables = {r[0] for r in self.db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        if tables - {"search_budget_meta", "search_budget_receipts"}:
            self.db.close()
            raise SemanticError("search_budget_not_owned")
        self.db.execute("PRAGMA synchronous=FULL")
        try:
            with self.db:
                self.db.execute("CREATE TABLE IF NOT EXISTS search_budget_meta (key TEXT PRIMARY KEY,value TEXT NOT NULL)")
                self.db.execute("""CREATE TABLE IF NOT EXISTS search_budget_receipts (
                    number INTEGER PRIMARY KEY, purpose TEXT NOT NULL, scope TEXT NOT NULL,
                    input_hash TEXT NOT NULL, tokens INTEGER NOT NULL, reservation TEXT NOT NULL,
                    state TEXT NOT NULL, evidence TEXT NOT NULL, cost TEXT, elapsed_ms REAL)""")
                saved = self._value("authorization")
                if saved is None:
                    self.db.execute("INSERT INTO search_budget_meta VALUES ('authorization',?)",
                                    (authorization.fingerprint,))
                elif saved != authorization.fingerprint:
                    raise SemanticError("search_authorization_changed")
        except Exception:
            self.db.close()
            raise

    def close(self):
        self.db.close()

    def _value(self, key):
        row = self.db.execute("SELECT value FROM search_budget_meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    def _halt(self, code):
        self.db.execute("INSERT OR REPLACE INTO search_budget_meta VALUES ('halted',?)", (code,))

    def reserve(self, purpose, scope, *, input_hash, tokens, reservation):
        if (purpose not in {"decision", "document", "query", "rerank"}
                or scope not in {"public-evaluation.v2", "persistent-test-library.v1", "library-validation.v1"}
                or not isinstance(input_hash, str) or not re.fullmatch(r"[a-f0-9]{64}", input_hash)
                or type(tokens) is not int or not 0 < tokens <= 100000):
            raise SemanticError("search_reservation_invalid")
        amount = _decimal(reservation)
        if not 0 <= amount <= Decimal("0.03"):
            raise SemanticError("search_reservation_invalid")
        try:
            self.db.execute("BEGIN IMMEDIATE")
            rows = self.db.execute("SELECT state,reservation,cost FROM search_budget_receipts").fetchall()
            held = sum((_decimal(r["cost"] if r["state"] in {"reported", "not_sent"} else r["reservation"])
                        for r in rows), Decimal(0))
            if (self.clock() >= self.authorization.expires or self._value("halted")
                    or any(r["state"] not in {"reported", "not_sent"} for r in rows)
                    or len(rows) >= self.authorization.max_posts
                    or held + amount > _decimal(self.authorization.limit_usd)):
                raise SemanticError("search_budget_blocked")
            cursor = self.db.execute("""INSERT INTO search_budget_receipts
                (purpose,scope,input_hash,tokens,reservation,state,evidence)
                VALUES (?,?,?,?,?,'pending','{}')""", (purpose, scope, input_hash, tokens, str(amount)))
            self.db.commit()  # Durable reservation BEFORE credential lookup/POST.
            return cursor.lastrowid
        except Exception:
            self.db.rollback()
            raise

    def not_sent(self, number, code):
        """A known local stop before transport is not an unknown model charge."""
        if code not in {"search_not_configured", "search_cancelled", "search_provider_unavailable"}:
            code = "search_provider_unavailable"
        with self.db:
            cursor = self.db.execute("UPDATE search_budget_receipts SET state='not_sent',cost='0',evidence=?"
                " WHERE number=? AND state='pending'", (json.dumps({"not_sent": code}), number))
            if cursor.rowcount != 1:
                raise SemanticError("search_receipt_invalid")

    def capture(self, number, payload):
        """Keep reconciliation evidence even if usage/model/result is invalid."""
        evidence = {}
        for field in ("id", "model", "provider"):
            value = payload.get(field)
            if (isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.:/-]{1,180}", value)
                    and not has_private_input(value)):
                evidence[field] = value
        usage = payload.get("usage")
        evidence["usage_shape"] = type(usage).__name__ if "usage" in payload else "missing"
        if isinstance(usage, dict):
            evidence["usage"] = {}
            for field in ("input_tokens", "output_tokens", "prompt_tokens", "total_tokens", "search_units", "cost"):
                value = usage.get(field)
                if value is None or type(value) in (bool, int):
                    safe = value
                elif type(value) in (str, float) and re.fullmatch(
                        r"[+-]?\d{1,30}(?:\.\d{1,30})?(?:[eE][+-]?\d{1,3})?", str(value)):
                    safe = value
                else:
                    safe = {"invalid_type": type(value).__name__}
                evidence["usage"][field] = safe
        with self.db:
            row = self.db.execute("SELECT state FROM search_budget_receipts WHERE number=?", (number,)).fetchone()
            if not row or row[0] != "pending":
                raise SemanticError("search_receipt_invalid")
            self.db.execute("UPDATE search_budget_receipts SET evidence=? WHERE number=?",
                            (json.dumps(evidence, allow_nan=False), number))

    def settle(self, number, payload, elapsed):
        row = self.db.execute("SELECT * FROM search_budget_receipts WHERE number=?", (number,)).fetchone()
        if not row or row["state"] != "pending":
            raise SemanticError("search_receipt_invalid")
        try:
            usage = payload["usage"]
            if not isinstance(usage, dict):
                raise ValueError
            cost = _decimal(usage["cost"])
            # Save observed charges, including excessive ones, before halting.
            with self.db:
                self.db.execute("UPDATE search_budget_receipts SET cost=?,elapsed_ms=? WHERE number=?",
                                (str(cost), round(elapsed * 1000, 3), number))
            if cost > _decimal(row["reservation"]):
                raise SemanticError("search_cost_exceeds_reservation")
            total = usage.get("total_tokens")
            if total is None:
                source, output = usage.get("input_tokens"), usage.get("output_tokens", 0)
                if type(source) is not int or type(output) is not int or output < 0:
                    raise ValueError
                total = source + output
            if type(total) is not int or not 0 <= total <= row["tokens"]:
                raise ValueError
            with self.db:
                self.db.execute("UPDATE search_budget_receipts SET state='reported' WHERE number=?", (number,))
        except SemanticError:
            self.fail(number, "search_billing_uncertain", elapsed)
            raise
        except (KeyError, TypeError, ValueError):
            self.fail(number, "search_billing_uncertain", elapsed)
            raise SemanticError("search_billing_uncertain") from None

    def fail(self, number, code, elapsed):
        # Codes are application constants; never store provider bodies or inputs.
        if not isinstance(code, str) or not re.fullmatch(r"[a-z_0-9]{1,80}", code):
            code = "search_provider_unavailable"
        with self.db:
            self._halt(code)
            self.db.execute("""UPDATE search_budget_receipts SET
                state=CASE WHEN state='reported' THEN state ELSE 'uncertain' END,
                elapsed_ms=? WHERE number=?""", (round(elapsed * 1000, 3), number))

    def acknowledge_published_alias(self):
        """Resolve only the observed, fully settled published-alias mismatch.

        This never removes a receipt, charge, request count or uncertain hold.
        It cannot acknowledge another error/provider/model or a nonzero charge.
        The fixed dated alias was verified in public endpoint metadata after the
        first contract check; no inference is replayed by this operation.
        """
        try:
            self.db.execute("BEGIN IMMEDIATE")
            rows = self.db.execute("SELECT * FROM search_budget_receipts ORDER BY number").fetchall()
            if (self._value("halted") != "search_route_mismatch" or not rows
                    or any(r["state"] != "reported" or _decimal(r["cost"]) != 0 for r in rows)):
                raise SemanticError("search_alias_acknowledgment_invalid")
            last = rows[-1]
            evidence = json.loads(last["evidence"])
            alias = (last["purpose"], evidence.get("provider"), evidence.get("model"))
            if (alias not in {("decision", "BaseTen", "baseten/mammoth-1-20261021"),
                    ("decision", "BaseTen", "baseten/mammoth-1-20261021:free"),
                    ("rerank", "Nvidia", "nvidia/nemotron-3.5-rerank-8b")}
                    or not evidence.get("id")):
                raise SemanticError("search_alias_acknowledgment_invalid")
            self.db.execute("INSERT INTO search_budget_meta VALUES (?,?)",
                ("acknowledged_alias_" + str(last["number"]), json.dumps({
                    "receipt": last["number"], "model": evidence["model"],
                    "basis": "verified fixed free endpoint response alias; zero reported cost"})))
            self.db.execute("DELETE FROM search_budget_meta WHERE key='halted'")
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    def summary(self):
        rows = [dict(r) for r in self.db.execute("SELECT * FROM search_budget_receipts ORDER BY number")]
        reported = sum((_decimal(r["cost"]) for r in rows if r["state"] == "reported"), Decimal(0))
        # Observed overcharges remain part of the conservative bound.
        unknown = sum((max(_decimal(r["reservation"]), _decimal(r["cost"] or 0))
                       for r in rows if r["state"] not in {"reported", "not_sent"}), Decimal(0))
        return {"requests": sum(r["state"] != "not_sent" for r in rows), "attempts": len(rows), "reported_cost_usd": str(reported),
                "unreported_upper_bound_usd": str(unknown),
                "total_cost_upper_bound_usd": str(reported + unknown),
                "halted": self._value("halted"), "receipts": rows}
