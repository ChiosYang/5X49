"""Provider-free metrics framework; synthetic contracts are not quality evidence."""
from dataclasses import dataclass
from math import ceil, log2
from statistics import median
from time import perf_counter
from typing import Callable
from typing import Annotated, Literal

from pydantic import Field, model_validator

from app.contracts.ask import AskContract
from app.contracts.search_plan import SearchPlan, Year, Minutes
from app.services.semantic_search import ContentDocument, ContentSource
from app.services.search_privacy import has_private_input

FixtureId = Annotated[int, Field(strict=True, ge=1, le=5000)]
Text = Annotated[str, Field(strict=True, min_length=1, max_length=600)]


def canonical_fixture_id(value):
    return "film_" + f"{value:032x}"


class FixtureFilm(AskContract):
    id: FixtureId
    title: Annotated[str, Field(strict=True, min_length=1, max_length=300)]
    overview: Annotated[str, Field(strict=True, min_length=1, max_length=2048)]
    year: Year
    minutes: Minutes
    watched: Annotated[bool, Field(strict=True)]

    def document(self):
        return ContentDocument(canonical_fixture_id(self.id), self.title, (),
                               (ContentSource("overview", self.overview, "library"),))


class FixtureQuestion(AskContract):
    id: Text
    locale: Literal["en", "zh"]
    question: Text
    content_query: Text
    expected: list[FixtureId] = Field(min_length=1, max_length=8)
    allowed: list[FixtureId] = Field(min_length=1, max_length=8)
    reference: FixtureId | None = None
    hard: SearchPlan = Field(default_factory=lambda: SearchPlan(version="search-plan.v2"))


class QualityFixture(AskContract):
    version: Literal["semantic-quality.synthetic.v1"]
    notice: Text
    films: list[FixtureFilm] = Field(min_length=1, max_length=8)
    cases: list[FixtureQuestion] = Field(min_length=1, max_length=24)

    @model_validator(mode="after")
    def validate_labels(self):
        identities = {film.id for film in self.films}
        if len(identities) != len(self.films) or len({case.id for case in self.cases}) != len(self.cases):
            raise ValueError("Duplicate fixture identity")
        for film in self.films:
            film.document()  # The same privacy/content boundary, no provider.
        for case in self.cases:
            if has_private_input(case.question) or has_private_input(case.content_query):
                raise ValueError("Private input in synthetic fixture")
            if (len(case.allowed) != len(set(case.allowed)) or len(case.expected) != len(set(case.expected))
                    or not set(case.expected) <= set(case.allowed) <= identities
                    or case.reference is not None and case.reference not in identities):
                raise ValueError("Invalid expected fixture identities")
            plan = case.hard
            if any((plan.genres, plan.countries, plan.exclude_genres, plan.exclude_countries, plan.people)):
                raise ValueError("This fixture has no source truth for non-scalar hard conditions")
            # Independent fixture metadata oracle, not model-generated plans.
            allowed = set()
            for film in self.films:
                if case.reference == film.id or plan.view != "all" and film.watched != (plan.view == "watched"):
                    continue
                if plan.year_min is not None and film.year < plan.year_min or plan.year_max is not None and film.year > plan.year_max:
                    continue
                if plan.duration_min is not None and (film.minutes < plan.duration_min or plan.duration_min_exclusive and film.minutes == plan.duration_min):
                    continue
                if plan.duration_max is not None and (film.minutes > plan.duration_max or plan.duration_max_exclusive and film.minutes == plan.duration_max):
                    continue
                allowed.add(film.id)
            if set(case.allowed) != allowed:
                raise ValueError("Hard eligibility labels disagree with fixture metadata")
        return self


def load_fixture(path):
    """Only load a reviewed synthetic manifest; never read an application DB."""
    return QualityFixture.model_validate_json(path.read_text(encoding="utf-8"))


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
