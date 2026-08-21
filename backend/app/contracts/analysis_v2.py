from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class StrictContract(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class AnalysisPredicate(StrEnum):
    INFLUENCED_BY = "INFLUENCED_BY"
    REMAKE_OF = "REMAKE_OF"
    ADAPTED_FROM = "ADAPTED_FROM"
    VISUALLY_SIMILAR_TO = "VISUALLY_SIMILAR_TO"
    HAS_THEME = "HAS_THEME"
    HAS_MOVEMENT = "HAS_MOVEMENT"
    HAS_VISUAL_STYLE = "HAS_VISUAL_STYLE"
    HAS_MICRO_GENRE = "HAS_MICRO_GENRE"


class AnalysisEntityReference(StrictContract):
    entity_type: Literal["film", "person", "concept"]
    entity_id: str | None = Field(default=None, pattern=r"^(film|person|concept)_[0-9a-f]{32}$")
    provider: str | None = Field(default=None, min_length=1, max_length=80)
    external_id: str | None = Field(default=None, min_length=1, max_length=160)
    display_name: str | None = Field(default=None, min_length=1, max_length=300)
    release_year: int | None = Field(default=None, ge=1888, le=2200)

    @model_validator(mode="after")
    def require_traceable_reference(self):
        if (self.provider is None) != (self.external_id is None):
            raise ValueError("provider and external_id must be supplied together")
        if self.entity_id or self.provider:
            return self
        if not self.display_name:
            raise ValueError("reference requires an entity ID, external identity, or display name")
        if self.entity_type == "film" and self.release_year is None:
            raise ValueError("unresolved film references require display_name and release_year")
        return self


class AnalysisQualifier(StrictContract):
    relationship_type: str | None = Field(default=None, max_length=80)
    direction_note: str | None = Field(default=None, max_length=160)
    period_start_year: int | None = Field(default=None, ge=1888, le=2200)
    period_end_year: int | None = Field(default=None, ge=1888, le=2200)

    @model_validator(mode="after")
    def validate_period(self):
        if (
            self.period_start_year is not None
            and self.period_end_year is not None
            and self.period_start_year > self.period_end_year
        ):
            raise ValueError("period_start_year must not be after period_end_year")
        return self


class AnalysisEvidenceCandidate(StrictContract):
    source_title: str = Field(min_length=1, max_length=300)
    source_uri: HttpUrl
    publisher: str | None = Field(default=None, max_length=160)
    claim: str = Field(min_length=1, max_length=400)
    stance: Literal["supports", "contradicts", "context"] = "supports"


class AnalysisAssertionCandidate(StrictContract):
    predicate: AnalysisPredicate
    target: AnalysisEntityReference
    source_scope: Literal["inferred"] = "inferred"
    rationale: str = Field(min_length=1, max_length=600)
    qualifiers: AnalysisQualifier | None = None
    evidence_candidates: list[AnalysisEvidenceCandidate] = Field(default_factory=list, max_length=5)


class AnalysisV2Input(StrictContract):
    schema_version: Literal["analysis-input.v2"] = "analysis-input.v2"
    film_id: str = Field(pattern=r"^film_[0-9a-f]{32}$")
    canonical_title: str = Field(min_length=1, max_length=300)
    original_title: str | None = Field(default=None, max_length=300)
    localized_titles: list[str] = Field(default_factory=list, max_length=20)
    release_year: int | None = Field(default=None, ge=1888, le=2200)
    runtime_minutes: int | None = Field(default=None, ge=1, le=2000)
    overview: str | None = Field(default=None, max_length=5000)
    genres: list[str] = Field(default_factory=list, max_length=50)
    countries: list[str] = Field(default_factory=list, max_length=50)
    external_identities: dict[str, str] = Field(default_factory=dict, max_length=20)


class AnalysisV2Output(StrictContract):
    schema_version: Literal["analysis-output.v2"] = "analysis-output.v2"
    subject_film_id: str = Field(pattern=r"^film_[0-9a-f]{32}$")
    summary: str = Field(min_length=1, max_length=1200)
    assertions: list[AnalysisAssertionCandidate] = Field(default_factory=list, max_length=50)
    unresolved_references: list[AnalysisEntityReference] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def reject_exact_duplicate_candidates(self):
        keys: set[tuple[str, str, str, str]] = set()
        for assertion in self.assertions:
            target = assertion.target
            target_key = target.entity_id or (
                f"{target.provider}:{target.external_id}"
                if target.provider
                else f"{target.display_name}:{target.release_year or ''}"
            )
            qualifier_key = assertion.qualifiers.model_dump_json() if assertion.qualifiers else ""
            key = (assertion.predicate.value, target.entity_type, target_key, qualifier_key)
            if key in keys:
                raise ValueError("analysis output contains duplicate assertion candidates")
            keys.add(key)
        return self


class EvaluationExpectedAssertion(StrictContract):
    predicate: AnalysisPredicate
    target: AnalysisEntityReference
    label: Literal["required", "acceptable", "forbidden"]
    note: str | None = Field(default=None, max_length=400)


class AnalysisEvaluationCase(StrictContract):
    case_id: str = Field(pattern=r"^eval_[a-z0-9][a-z0-9_-]{2,63}$")
    language: Literal["zh", "en", "mixed", "other"]
    tags: list[Literal[
        "same_title",
        "cold_title",
        "non_latin_title",
        "cross_decade",
        "remake",
        "adaptation",
        "visual_style",
        "influence",
    ]] = Field(default_factory=list, min_length=1)
    input: AnalysisV2Input
    expected_assertions: list[EvaluationExpectedAssertion] = Field(default_factory=list)
    annotator_count: int = Field(ge=1, le=20)
    adjudication_status: Literal["draft", "adjudicated"]


class AnalysisEvaluationDataset(StrictContract):
    format_version: Literal["analysis-eval.v1"] = "analysis-eval.v1"
    dataset_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,80}$")
    description: str = Field(min_length=1, max_length=1000)
    cases: list[AnalysisEvaluationCase] = Field(min_length=30, max_length=50)

    @model_validator(mode="after")
    def require_unique_cases_and_coverage(self):
        case_ids = [case.case_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("evaluation case IDs must be unique")
        tags = {tag for case in self.cases for tag in case.tags}
        required = {"same_title", "cold_title", "non_latin_title", "cross_decade"}
        if not required.issubset(tags):
            raise ValueError("evaluation set is missing required identity coverage tags")
        languages = {case.language for case in self.cases}
        if not {"zh", "en"}.issubset(languages):
            raise ValueError("evaluation set must include Chinese and English cases")
        return self
