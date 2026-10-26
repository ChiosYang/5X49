"""One explicitly approved, hash-bound rerank supplement on the original ledger.

Historical receipts and metadata, including every halt, are immutable. Ordinary
budget callers remain blocked. This view permits only the sealed ordered inputs;
it is not a general acknowledgement of an uncertain charge or a retry mechanism.
"""
import json
import re

from app.services.openrouter_embeddings import _decimal
from app.services.search_budget import SearchBudget
from app.services.semantic_search import SemanticError, _hash

PREFIX = "focus_validation_v1_"
MAX_REQUESTS = 5


class FocusBudget(SearchBudget):
    def rows(self):
        return [dict(r) for r in self.db.execute("SELECT * FROM search_budget_receipts ORDER BY number")]

    def historical_meta(self):
        return {k: v for k, v in self.db.execute("SELECT key,value FROM search_budget_meta")
                if not k.startswith(PREFIX)}

    def _check(self, grant):
        try:
            required = {"version", "authorization", "baseline", "max_attempts", "issued", "expires",
                        "rows_sha256", "meta_sha256", "plan_sha256", "requests"}
            requests = grant["requests"]
            rows = self.rows(); baseline = grant["baseline"]
            previous = json.loads(self.historical_meta()["bounded_validation_v1_grant"])
            halt = json.loads(self.historical_meta()["bounded_validation_v1_halt"])
            digest = lambda value: isinstance(value, str) and re.fullmatch("[a-f0-9]{64}", value)
            if (set(grant) != required or grant["version"] != "focus-validation-grant.v1"
                    or grant["authorization"] != self.authorization.fingerprint
                    or self._value("authorization") != self.authorization.fingerprint
                    or _decimal(self.authorization.limit_usd) != 0
                    or type(baseline) is not int or not 1 <= baseline <= len(rows)
                    or [r["number"] for r in rows] != list(range(1, len(rows) + 1))
                    or type(grant["max_attempts"]) is not int
                    or grant["max_attempts"] != baseline + MAX_REQUESTS
                    or grant["max_attempts"] > min(previous["max_attempts"], self.authorization.max_posts)
                    or len(rows) > grant["max_attempts"]
                    or type(grant["issued"]) is not int or type(grant["expires"]) is not int
                    or not 0 < grant["expires"] - grant["issued"] <= 86400
                    or not grant["issued"] <= self.clock() < grant["expires"]
                    or not digest(grant["plan_sha256"])
                    or _hash(rows[:baseline]) != grant["rows_sha256"]
                    or _hash(self.historical_meta()) != grant["meta_sha256"]
                    or halt != {"number": baseline, "code": "provider_http_429"}
                    or rows[baseline - 1]["purpose"] != "rerank"
                    or rows[baseline - 1]["scope"] != "public-evaluation.v2"
                    or rows[baseline - 1]["state"] != "uncertain"
                    or rows[baseline - 1]["cost"] is not None
                    or any(r["state"] not in {"reported", "not_sent", "uncertain"}
                           or _decimal(r["cost"] or 0) != 0 or _decimal(r["reservation"]) != 0
                           for r in rows[:baseline])
                    or not isinstance(requests, list) or len(requests) != MAX_REQUESTS
                    or any(not isinstance(r, dict) or set(r) != {"input_hash", "tokens"}
                           or not digest(r["input_hash"]) or type(r["tokens"]) is not int
                           or not 0 < r["tokens"] <= 100000 for r in requests)
                    or len({r["input_hash"] for r in requests}) != MAX_REQUESTS
                    or any(r["input_hash"] == rows[baseline - 1]["input_hash"] for r in requests)
                    or any(r["purpose"] != "rerank" or r["scope"] != "public-evaluation.v2"
                           or r["input_hash"] != requests[i]["input_hash"] or r["tokens"] != requests[i]["tokens"]
                           or _decimal(r["reservation"]) != 0 for i, r in enumerate(rows[baseline:]))):
                raise ValueError
        except (KeyError, TypeError, ValueError, IndexError):
            raise SemanticError("search_focus_grant_invalid") from None
        return grant

    def activate(self, grant):
        try:
            self.db.execute("BEGIN IMMEDIATE")
            self._check(grant)
            saved = self._value(PREFIX + "grant")
            if saved is not None:
                if json.loads(saved) != grant:
                    raise SemanticError("search_focus_grant_changed")
            elif len(self.rows()) != grant["baseline"] or self._value(PREFIX + "halt"):
                raise SemanticError("search_focus_already_attempted")
            else:
                self.db.execute("INSERT INTO search_budget_meta VALUES (?,?)",
                                (PREFIX + "grant", json.dumps(grant)))
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    def _grant(self):
        try:
            return self._check(json.loads(self._value(PREFIX + "grant") or "null"))
        except (TypeError, ValueError):
            raise SemanticError("search_focus_not_authorized") from None

    def reserve(self, purpose, scope, *, input_hash, tokens, reservation):
        try:
            self.db.execute("BEGIN IMMEDIATE")
            grant = self._grant(); newer = self.rows()[grant["baseline"]:]
            if (self._value(PREFIX + "halt") or len(newer) >= MAX_REQUESTS
                    or any(r["state"] != "reported" or _decimal(r["cost"]) != 0
                           or r["purpose"] != "rerank" or r["scope"] != "public-evaluation.v2"
                           or r["input_hash"] != grant["requests"][i]["input_hash"]
                           or r["tokens"] != grant["requests"][i]["tokens"] for i, r in enumerate(newer))):
                raise SemanticError("search_budget_blocked")
            expected = grant["requests"][len(newer)]
            if (purpose != "rerank" or scope != "public-evaluation.v2"
                    or type(tokens) is not int or {"input_hash": input_hash, "tokens": tokens} != expected
                    or _decimal(reservation) != 0):
                raise SemanticError("search_focus_input_mismatch")
            cursor = self.db.execute("""INSERT INTO search_budget_receipts
                (purpose,scope,input_hash,tokens,reservation,state,evidence)
                VALUES (?,?,?,?,'0','pending','{}')""", (purpose, scope, input_hash, tokens))
            self.db.commit()
            return cursor.lastrowid
        except Exception:
            self.db.rollback()
            raise

    def stop(self, code):
        if not isinstance(code, str) or not re.fullmatch("[a-z_0-9]{1,80}", code):
            code = "search_focus_stopped"
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO search_budget_meta VALUES (?,?)", (PREFIX + "halt", code))

    def _new_receipt(self, number):
        # Evidence must still be captured after a grant expires mid-request.
        try:
            grant = json.loads(self._value(PREFIX + "grant"))
            if type(number) is not int or not grant["baseline"] < number <= grant["max_attempts"]:
                raise ValueError
            row = self.db.execute("SELECT * FROM search_budget_receipts WHERE number=?", (number,)).fetchone()
            expected = grant["requests"][number - grant["baseline"] - 1]
            if not row or row["input_hash"] != expected["input_hash"] or row["tokens"] != expected["tokens"]:
                raise ValueError
        except (KeyError, TypeError, ValueError, IndexError):
            raise SemanticError("search_receipt_invalid") from None

    def capture(self, number, payload):
        self._new_receipt(number)
        return super().capture(number, payload)

    def settle(self, number, payload, elapsed):
        self._new_receipt(number)
        return super().settle(number, payload, elapsed)

    def not_sent(self, number, code):
        self._new_receipt(number)
        super().not_sent(number, code)
        self.stop(code)

    def fail(self, number, code, elapsed):
        self._new_receipt(number)
        with self.db:
            self.db.execute("UPDATE search_budget_receipts SET state=CASE WHEN state='reported' THEN state ELSE 'uncertain' END,elapsed_ms=? WHERE number=?",
                            (round(elapsed * 1000, 3), number))
        self.stop(code)

    def summary(self):
        result = super().summary()
        result.update(focus_halted=self._value(PREFIX + "halt"), total_cost_finalized=False)
        return result
