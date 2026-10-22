"""Frozen public-film fixture and graded metrics. No network or library DB reads."""
from collections import Counter
from hashlib import sha256
import json
from math import log2
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlparse

from pydantic import Field, model_validator

from app.contracts.ask import AskContract
from app.contracts.search_plan import SearchPlan
from app.contracts.structured_metadata import normalize_metadata_text
from app.services.semantic_search import ContentDocument, ContentSource, SemanticError
from app.services.search_privacy import has_private_input

Id = Annotated[str, Field(pattern=r"^film_[0-9a-f]{32}$")]
Qid = Annotated[str, Field(pattern=r"^Q[1-9][0-9]*$")]
Text = Annotated[str, Field(strict=True, min_length=1, max_length=1200)]
Key = Annotated[str, Field(pattern=r"^[a-zA-Z0-9_-]{1,100}$")]


def identity(qid):
    return "film_" + sha256(("5X49:public-movie:" + qid).encode()).hexdigest()[:32]


class Source(AskContract):
    id: Key
    url: Text
    revision: str | None
    retrieved: Literal["2026-10-22"]
    license: Text
    kind: Literal["structured_metadata", "primary_film_source"]

    @model_validator(mode="after")
    def safe_source(self):
        parsed = urlparse(self.url)
        if (parsed.scheme != "https" or parsed.username or parsed.password or parsed.port
                or parsed.hostname not in {"www.wikidata.org", "www.criterion.com", "a24films.com",
                    "www.focusfeatures.com", "www.bfi.org.uk", "player.bfi.org.uk",
                    "www.sonypictures.com", "www.neonrated.com", "bleeckerstreetmedia.com",
                    "www.magpictures.com"}):
            raise ValueError("Invalid public source URL")
        return self


class ScalarFact(AskContract):
    status: Literal["accepted", "missing", "conflicted"]
    value: Annotated[int, Field(strict=True, ge=1, le=10000)] | None
    sources: list[Key] = Field(max_length=8)
    reason: Text

    @model_validator(mode="after")
    def complete(self):
        if (self.status == "accepted") != (self.value is not None):
            raise ValueError("Unknown/conflicted scalar cannot be matched")
        if self.status == "accepted" and not self.sources:
            raise ValueError("Accepted facts require provenance")
        return self


class FacetFact(AskContract):
    status: Literal["accepted", "missing", "conflicted"]
    value: list[Annotated[str, Field(strict=True, min_length=1, max_length=100)]] = Field(max_length=20)
    sources: list[Key] = Field(max_length=8)
    reason: Text

    @model_validator(mode="after")
    def complete(self):
        if (self.status == "accepted") != bool(self.value) or len(set(self.value)) != len(self.value):
            raise ValueError("Unknown/conflicted facet cannot be matched")
        return self


class Title(AskContract):
    locale: Annotated[str, Field(pattern=r"^[a-z-]{2,10}$")]
    value: Annotated[str, Field(strict=True, min_length=1, max_length=300)]
    source: Key


class Paraphrase(AskContract):
    en: Text
    zh: Text
    sources: list[Key] = Field(min_length=1, max_length=5)


class RuntimeObservation(AskContract):
    source: Key
    value: Annotated[int, Field(strict=True, ge=1, le=10000)] | Annotated[float, Field(strict=True, gt=0, le=600000, allow_inf_nan=False)]
    unit: Literal["minutes", "seconds"]


class PublicFilm(AskContract):
    id: Id
    key: Key
    qid: Qid
    titles: list[Title] = Field(min_length=2, max_length=60)
    title_en: Text
    title_zh: Text
    document_text: Annotated[str, Field(strict=True, min_length=1, max_length=512)]
    paraphrase: Paraphrase
    year: ScalarFact
    minutes: ScalarFact
    runtime_observations: list[RuntimeObservation] = Field(max_length=8)
    countries: FacetFact
    directors: FacetFact
    genres: FacetFact

    def document(self):
        # Exactly one public input is shared by lexical and dense methods.
        return ContentDocument(self.id, self.title_en, (),
            (ContentSource("overview", self.document_text, "rule"),))

    @model_validator(mode="after")
    def valid(self):
        if self.id != identity(self.qid):
            raise ValueError("Film identity must derive from its fixed public QID")
        names = {t.value for t in self.titles}
        if self.title_en not in names or self.title_zh not in names:
            raise ValueError("Unverified display title")
        if self.document_text != f"{self.title_en} / {self.title_zh}. {self.paraphrase.en} {self.paraphrase.zh}":
            raise ValueError("Embedding text differs from the shared factual document")
        if self.year.status == "accepted" and not 1870 <= self.year.value <= 2100:
            raise ValueError("Invalid film year")
        minute_values = {o.value for o in self.runtime_observations if o.unit == "minutes"}
        if ((self.minutes.status == "accepted" and minute_values != {self.minutes.value})
                or self.minutes.status == "conflicted" and len(minute_values) < 2):
            raise ValueError("Runtime status disagrees with its observations")
        self.document()
        if len(self.document().chunks) != 1:
            raise ValueError("Public run requires one encoding per film")
        for name in names:
            if has_private_input(name):
                raise ValueError("Private title input")
        return self


class PublicPerson(AskContract):
    qid: Qid
    name: Text
    aliases: list[Text] = Field(min_length=1, max_length=50)
    source: Key


class Qrel(AskContract):
    film_id: Id
    grade: Annotated[int, Field(strict=True, ge=1, le=3)]
    reason: Text
    sources: list[Key] = Field(min_length=1, max_length=6)


class PublicCase(AskContract):
    id: Key
    locale: Literal["en", "zh"]
    kind: Literal["identity", "plot_fact", "theme", "hard_conditions", "no_answer"]
    question: Annotated[str, Field(strict=True, min_length=1, max_length=600)]
    reference_id: Id | None
    hard: SearchPlan
    qrels: list[Qrel] = Field(max_length=24)
    zero_grade_reason: Text
    expected_ids: list[Id] = Field(max_length=24)
    allowed_ids: list[Id] = Field(max_length=24)
    qrels_status: Literal["provisional-curated-not-human-gold", "source-backed-objective"]
    split: Literal["test"]
    translation_group: Key
    embedding_query: Annotated[str, Field(strict=True, min_length=1, max_length=600)] | None


CONFIGURATION = {
    "model": "nvidia/nemotron-3.5-embed-8b:free", "provider": "nvidia/bf16", "dimensions": 4096,
    "model_created": 1792591666,
    "provider_fingerprint": "368d665ce45b20e515a3f00a79de6cb3b2d15465210d85a68c70aae794718044",
    "input_type": {"document": "passage", "query": "query"}, "minimum_similarity": .35, "rrf_k": 60,
    "hybrid_weights": {"dense": 1, "lexical": 1},
    "lexical_policy": "existing-semantic-search-NFKC-English-words-CJK-bigrams-v1",
    "same_document_text_for_all_methods": True, "maximum_requests": 42, "maximum_encoded_texts": 42,
    "expected_document_encodings": 24, "expected_query_encodings": 14, "maximum_reserved_tokens": 20000,
    "cost_ceiling_usd": "0", "fallbacks": False, "automatic_retries": 0, "chat_requests": 0, "rerank_requests": 0,
    "nvidia_input_logging_accepted": True, "production_enabled": False, "tuning_on_this_test_set": False,
    "sent_fields": ["films[].document_text", "cases[].embedding_query (non-null only)"],
    "local_only_fields": ["source URLs/revisions", "stable IDs", "qrels/reasons", "hard fact records",
                          "title aliases beyond document text", "private library (never read)"],
}


def hard_ids(films, people, plan):
    """Independent fixture oracle. The real executor is cross-checked in tests."""
    if plan.view != "all" or any(p.role != "director" for p in plan.people):
        raise ValueError("Public fixture has no watch history or actor truth")
    chosen = []
    for clause in plan.people:
        matches = [p.qid for p in people if normalize_metadata_text(clause.name) in
            {normalize_metadata_text(n) for n in [p.name, *p.aliases]}]
        if len(matches) != 1:
            raise ValueError("Ambiguous/unknown director literal")
        chosen.append((matches[0], clause.exclude))
    selected = set()
    for film in films:
        keep = True
        for field in ("genres", "countries"):
            fact = getattr(film, field)
            known = {normalize_metadata_text(v) for v in fact.value}
            for exclusion in (False, True):
                wanted = {normalize_metadata_text(v) for v in getattr(plan, ("exclude_" if exclusion else "") + field)}
                if wanted and (fact.status != "accepted" or bool(wanted & known) == exclusion):
                    keep = False
        for qid, exclusion in chosen:
            if film.directors.status != "accepted" or (qid in film.directors.value) == exclusion:
                keep = False
        for field, name in (("year", "year"), ("minutes", "duration")):
            lo, hi = getattr(plan, name + "_min"), getattr(plan, name + "_max")
            fact = getattr(film, field)
            if lo is not None or hi is not None:
                if fact.status != "accepted":
                    keep = False
                    continue
                if lo is not None and (fact.value < lo or getattr(plan, name + "_min_exclusive", False) and fact.value == lo):
                    keep = False
                if hi is not None and (fact.value > hi or getattr(plan, name + "_max_exclusive", False) and fact.value == hi):
                    keep = False
        if keep:
            selected.add(film.id)
    return selected


class PublicFixture(AskContract):
    version: Literal["semantic-quality.public-movies.v1"]
    notice: Text
    created: Literal["2026-10-22"]
    license_policy: Text
    qrels_status: Literal["provisional-curated-not-human-gold"]
    default_unlisted_grade: Literal[0]
    year_policy: Text
    runtime_policy: Text
    films: list[PublicFilm] = Field(min_length=24, max_length=24)
    people: list[PublicPerson] = Field(min_length=2, max_length=2)
    cases: list[PublicCase] = Field(min_length=24, max_length=24)
    sources: list[Source] = Field(min_length=48, max_length=60)
    configuration: dict

    def inputs(self):
        return frozenset([(film.document_text, False) for film in self.films]
            + [(case.embedding_query, True) for case in self.cases if case.embedding_query is not None])

    @model_validator(mode="after")
    def fixed_scope(self):
        if json.dumps(self.configuration, sort_keys=True, allow_nan=False) != json.dumps(CONFIGURATION, sort_keys=True):
            raise ValueError("Retrieval, routing or authorization config differs from the frozen protocol")
        ids = {f.id for f in self.films}
        source_ids = {s.id for s in self.sources}
        if (len(ids) != 24 or len({f.qid for f in self.films}) != 24 or len({f.key for f in self.films}) != 24
                or len({c.id for c in self.cases}) != 24 or len(source_ids) != len(self.sources)):
            raise ValueError("Duplicate public identity")
        if (Counter(c.locale for c in self.cases) != {"en": 12, "zh": 12}
                or Counter(c.kind for c in self.cases) != {"identity": 4, "plot_fact": 6, "theme": 8, "hard_conditions": 4, "no_answer": 2}
                or sum(c.reference_id is not None for c in self.cases) != 2):
            raise ValueError("Question sampling changed")
        for film in self.films:
            refs = [t.source for t in film.titles] + film.paraphrase.sources
            refs += [o.source for o in film.runtime_observations]
            refs += [s for fact in (film.year, film.minutes, film.genres, film.countries, film.directors) for s in fact.sources]
            if set(refs) - source_ids:
                raise ValueError("Missing field provenance")
        for person in self.people:
            if person.source not in source_ids or any(has_private_input(n) for n in [person.name, *person.aliases]):
                raise ValueError("Invalid public director provenance")
        for case in self.cases:
            if has_private_input(case.question) or case.embedding_query is not None and has_private_input(case.embedding_query):
                raise ValueError("Private query input")
            should_embed = case.kind not in {"identity", "hard_conditions"} and case.reference_id is None
            if (case.embedding_query != (case.question if should_embed else None)
                    or case.reference_id is not None and (case.kind != "theme" or case.reference_id not in ids)
                    or case.qrels_status != ("provisional-curated-not-human-gold" if case.kind == "theme" else "source-backed-objective")):
                raise ValueError("Invalid question routing/judgment status")
            grades = {r.film_id: r.grade for r in case.qrels}
            if (len(grades) != len(case.qrels) or set(grades) - ids or case.reference_id in grades
                    or set(s for q in case.qrels for s in q.sources) - source_ids
                    or set(case.expected_ids) != {i for i, grade in grades.items() if grade >= 2}
                    or len(set(case.expected_ids)) != len(case.expected_ids)
                    or len(set(case.allowed_ids)) != len(case.allowed_ids)):
                raise ValueError("Invalid qrels/expected identities")
            if case.kind == "hard_conditions":
                allowed = hard_ids(self.films, self.people, case.hard)
                if set(case.expected_ids) != allowed:
                    raise ValueError("Hard-condition truth differs from metadata")
            elif case.kind == "identity":
                wanted = normalize_metadata_text(case.question)
                allowed = {f.id for f in self.films if wanted in {normalize_metadata_text(t.value) for t in f.titles}}
                if set(case.expected_ids) != allowed or len(allowed) != 1:
                    raise ValueError("Identity truth differs from source-backed titles")
            else:
                allowed = ids - {case.reference_id}
            if set(case.allowed_ids) != allowed or not set(case.expected_ids) <= allowed:
                raise ValueError("Invalid hard eligibility")
            if case.kind == "no_answer" and grades:
                raise ValueError("No-answer questions cannot have positive qrels")
            if case.kind != "hard_conditions" and case.hard != SearchPlan(version="search-plan.v2"):
                raise ValueError("Unstated hard filters")
        if (len(self.inputs()) != 38 or sum(query for _, query in self.inputs()) != 14
                or sum(len(text.encode()) + 256 for text, _ in self.inputs()) > 20000):
            raise ValueError("Public run exceeds the bounded encoding manifest")
        return self


def load_fixture(path: Path):
    return PublicFixture.model_validate_json(path.read_text(encoding="utf-8"))


def score(case: PublicCase, actual):
    if not isinstance(actual, list) or any(not isinstance(i, str) for i in actual):
        raise ValueError("Invalid ranked identity")
    if len(actual) != len(set(actual)):
        raise ValueError("Duplicate/invalid ranked identities")
    allowed = set(case.allowed_ids)
    grades = {q.film_id: q.grade for q in case.qrels}
    expected = set(case.expected_ids)
    ideal = sorted(grades.values(), reverse=True)[:10]
    dcg = sum((2 ** grades.get(i, 0) - 1) / log2(rank + 2) for rank, i in enumerate(actual[:10]))
    idcg = sum((2 ** grade - 1) / log2(rank + 2) for rank, grade in enumerate(ideal))
    return {"id": case.id, "kind": case.kind, "locale": case.locale,
        "actual_ids": actual, "expected_ids": case.expected_ids,
        "top1_hit": bool(actual) and actual[0] in expected if expected else not actual,
        "recall_at_3": len(set(actual[:3]) & expected) / len(expected) if expected else int(not actual),
        "ndcg_at_10": dcg / idcg if idcg else int(not actual),
        "exact_set": set(actual) == expected,
        "hard_condition_violations": sorted(set(actual) - allowed),
        "no_answer_false_positive": case.kind == "no_answer" and bool(actual),
        "qrels_status": case.qrels_status}


def summarize(rows):
    def group(items):
        return {"cases": len(items), "top1_hit_rate": sum(r["top1_hit"] for r in items) / len(items),
            "recall_at_3": sum(r["recall_at_3"] for r in items) / len(items),
            "ndcg_at_10": sum(r["ndcg_at_10"] for r in items) / len(items),
            "exact_set_rate": sum(r["exact_set"] for r in items) / len(items),
            "hard_condition_violations": sum(len(r["hard_condition_violations"]) for r in items),
            "no_answer_false_positives": sum(r["no_answer_false_positive"] for r in items)}
    if not rows:
        raise ValueError("No evaluation rows")
    return {"all_cases": group(rows),
        "semantic_cases": group([r for r in rows if r["kind"] not in {"identity", "hard_conditions"}]),
        "semantic_by_locale": {locale: group([r for r in rows if r["locale"] == locale and
            r["kind"] not in {"identity", "hard_conditions"}]) for locale in ("en", "zh")},
        "by_kind": {kind: group([r for r in rows if r["kind"] == kind]) for kind in sorted({r["kind"] for r in rows})},
        "by_locale": {locale: group([r for r in rows if r["locale"] == locale]) for locale in ("en", "zh")},
        "results": rows}
