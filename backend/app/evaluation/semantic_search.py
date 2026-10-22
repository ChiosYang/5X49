"""Provider-free metrics framework; synthetic contracts are not quality evidence."""
from dataclasses import dataclass
from math import ceil, log2
from statistics import median
from time import perf_counter
from typing import Callable


@dataclass(frozen=True)
class SemanticCase:
    name: str
    question: str
    expected_ids: tuple[str, ...]
    hard_allowed_ids: tuple[str, ...]


def evaluate(cases: list[SemanticCase], methods: dict[str, Callable[[SemanticCase], list[str]]]):
    """Callers own fixtures/transports. This module never downloads or calls APIs.

    Expected IDs define binary relevance for ranked NDCG and recall. Hard
    eligibility is independent ground truth, not inferred from returned results.
    Real evaluation needs separately authorized providers and human relevance
    labels; do not relabel this synthetic report as production model accuracy.
    """
    reports = {}
    for name, execute in methods.items():
        rows = []
        for case in cases:
            start = perf_counter()
            actual = execute(case)
            elapsed = (perf_counter() - start) * 1000
            if len(actual) != len(set(actual)):
                raise ValueError("Duplicate Film identities")
            expected = set(case.expected_ids)
            allowed = set(case.hard_allowed_ids)
            if not expected <= allowed:
                raise ValueError("Expected result violates its hard conditions")
            dcg = sum(1 / log2(rank + 2) for rank, film_id in enumerate(actual[:10]) if film_id in expected)
            ideal = sum(1 / log2(rank + 2) for rank in range(min(10, len(expected))))
            rows.append({"name": case.name, "actual_ids": actual,
                "recall_at_40": len(set(actual[:40]) & expected) / len(expected) if expected else int(not actual),
                "precision_at_10": len(set(actual[:10]) & expected) / len(actual[:10]) if actual else int(not expected),
                "ndcg_at_10": dcg / ideal if ideal else int(not actual),
                "hard_condition_violations": sorted(set(actual) - allowed),
                "elapsed_ms": round(elapsed, 3)})
        times = sorted(row["elapsed_ms"] for row in rows)
        reports[name] = {"cases": len(rows),
            "recall_at_40": sum(row["recall_at_40"] for row in rows) / len(rows) if rows else 0,
            "precision_at_10": sum(row["precision_at_10"] for row in rows) / len(rows) if rows else 0,
            "ndcg_at_10": sum(row["ndcg_at_10"] for row in rows) / len(rows) if rows else 0,
            "hard_condition_violations": sum(len(row["hard_condition_violations"]) for row in rows),
            "median_ms": median(times) if times else 0,
            "p95_ms": times[max(0, ceil(len(times) * .95) - 1)] if times else 0,
            "results": rows}
    return {"version": "semantic-evaluation.offline.v1", "mode": "synthetic-contract",
            "real_model": False, "human_quality_verified": False, "methods": reports}
