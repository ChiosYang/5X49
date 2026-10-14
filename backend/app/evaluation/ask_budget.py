"""Durable, serialized paid-evaluation guard. No client/network code lives here."""
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation
from pathlib import Path
import sqlite3
import uuid

HARD_LIMIT = Decimal("1.00")
STOP_LIMIT = Decimal("0.75")
INPUT_LIMIT = 8000
# Absolute official context ceiling backs up the conservative text-token bound.
# Reserve it for billing so tokenizer/framing assumptions cannot exceed budget.
BILLING_INPUT_RESERVE = 1_048_576
OUTPUT_LIMIT = 1600
PROMPT_PRICE_CAP = Decimal("0.00000010")
COMPLETION_PRICE_CAP = Decimal("0.00000020")


class BudgetStop(ValueError):
    pass


def amount(value):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise BudgetStop("invalid_cost_evidence") from None
    if not result.is_finite() or result < 0:
        raise BudgetStop("invalid_cost_evidence")
    return result


def input_upper_bound(messages):
    # Each text token consumes at least one UTF-8 byte in the model's byte-level
    # tokenizer. Reserve a further 1024 tokens for chat roles/framing. Refuse
    # large payloads instead of estimating with words or characters.
    count = sum(len(message["content"].encode("utf-8")) for message in messages) + 1024
    if count > INPUT_LIMIT:
        raise BudgetStop("input_token_upper_bound_exceeded")
    return count


class BudgetLedger:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS attempt (
                id TEXT PRIMARY KEY, run_id TEXT NOT NULL, case_id TEXT NOT NULL,
                reserved TEXT NOT NULL, cost TEXT, generation_id TEXT,
                state TEXT NOT NULL, outcome TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            db.row_factory = sqlite3.Row
            with db:
                db.execute("BEGIN IMMEDIATE")
                yield db
        finally:
            db.close()

    @staticmethod
    def _totals(db):
        rows = db.execute("SELECT * FROM attempt").fetchall()
        known = sum((amount(row["cost"]) for row in rows if row["cost"] is not None), Decimal(0))
        exposure = known + sum((amount(row["reserved"]) for row in rows if row["cost"] is None), Decimal(0))
        return known, exposure, any(row["cost"] is None for row in rows)

    def reserve(self, run_id, case_id, input_tokens, output_tokens):
        if not (isinstance(input_tokens, int) and not isinstance(input_tokens, bool) and 0 < input_tokens <= INPUT_LIMIT
                and isinstance(output_tokens, int) and not isinstance(output_tokens, bool) and 0 < output_tokens <= OUTPUT_LIMIT):
            raise BudgetStop("invalid_token_reservation")
        # Request fees are required to be zero by provider policy/preflight.
        reserved = BILLING_INPUT_RESERVE * PROMPT_PRICE_CAP + output_tokens * COMPLETION_PRICE_CAP
        attempt = uuid.uuid4().hex
        with self._db() as db:
            _, exposure, uncertain = self._totals(db)
            if uncertain:
                raise BudgetStop("unsettled_attempt_stop")
            if db.execute("SELECT 1 FROM attempt WHERE state='blocked' LIMIT 1").fetchone():
                raise BudgetStop("billing_or_contract_blocked")
            if exposure + reserved > STOP_LIMIT or exposure + reserved > HARD_LIMIT:
                raise BudgetStop("cumulative_budget_stop")
            db.execute("INSERT INTO attempt(id,run_id,case_id,reserved,state) VALUES (?,?,?,?,?)",
                       (attempt, run_id, case_id, str(reserved), "reserved"))
        return attempt

    def settle(self, attempt, *, cost, generation_id, outcome):
        with self._db() as db:
            row = db.execute("SELECT * FROM attempt WHERE id=?", (attempt,)).fetchone()
            if row is None or row["state"] != "reserved":
                raise BudgetStop("invalid_settlement")
            if cost is None or not generation_id:
                db.execute("UPDATE attempt SET state='unknown', generation_id=?, outcome=? WHERE id=?", (generation_id, outcome, attempt))
                stop = "unknown_billing_stop"
            else:
                billed = amount(cost)
                db.execute("UPDATE attempt SET cost=?,generation_id=?,state='settled',outcome=? WHERE id=?",
                           (str(billed), generation_id, outcome, attempt))
                stop = "reservation_exceeded_stop" if billed > amount(row["reserved"]) else None
                if stop:
                    db.execute("UPDATE attempt SET state='blocked' WHERE id=?", (attempt,))
        if stop:
            raise BudgetStop(stop)

    def block(self, attempt, outcome):
        with self._db() as db:
            db.execute("UPDATE attempt SET state='blocked',outcome=? WHERE id=?", (outcome, attempt))

    def summary(self):
        with self._db() as db:
            known, exposure, uncertain = self._totals(db)
            attempts = db.execute("SELECT id,run_id,case_id,reserved,cost,generation_id,state,outcome FROM attempt ORDER BY rowid").fetchall()
        return {"hard_limit_usd": str(HARD_LIMIT), "stop_limit_usd": str(STOP_LIMIT),
                "known_cost_usd": str(known), "reserved_exposure_usd": str(exposure),
                "uncertain_billing": uncertain, "blocked": any(row['state']=='blocked' for row in attempts),
                "attempts": [dict(row) for row in attempts]}
