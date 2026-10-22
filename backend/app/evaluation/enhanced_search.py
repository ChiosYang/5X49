"""Offline expected-ID metrics. The caller supplies fixtures; no provider/network."""
from dataclasses import dataclass
from math import ceil
from statistics import median
from time import perf_counter
from typing import Callable


@dataclass(frozen=True)
class SearchCase:
    name: str
    question: str
    expected_ids: tuple[str, ...]


def evaluate(cases: list[SearchCase], search: Callable[[str], list[str]]) -> dict:
    rows = []
    for case in cases:
        start = perf_counter()
        ids = search(case.question)
        elapsed = (perf_counter() - start) * 1000
        if len(ids) != len(set(ids)):
            raise ValueError("Search returned duplicate Film identities")
        expected = set(case.expected_ids)
        rows.append({"name": case.name, "expected_ids": list(case.expected_ids), "actual_ids": ids,
            "recall_at_40": len(set(ids[:40]) & expected) / len(expected) if expected else int(not ids),
            "unexpected_ids": sorted(set(ids) - expected),
            "top1_correct": (ids[:1] == list(case.expected_ids[:1])), "elapsed_ms": round(elapsed, 3)})
    times = sorted(row["elapsed_ms"] for row in rows)
    return {"version": "enhanced-search.offline.v1", "mode": "synthetic-local", "real_model": False,
        "cases": len(rows), "recall_at_40": sum(row["recall_at_40"] for row in rows) / len(rows) if rows else 0,
        "top1_accuracy": sum(row["top1_correct"] for row in rows) / len(rows) if rows else 0,
        "hard_condition_violations": sum(len(row["unexpected_ids"]) for row in rows),
        "median_ms": median(times) if times else 0, "p95_ms": times[max(0, ceil(len(times) * .95) - 1)] if times else 0,
        "results": rows}
