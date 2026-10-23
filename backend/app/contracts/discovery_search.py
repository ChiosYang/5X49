"""Submission-only interpretation; restored searches never perform inference."""
from typing import Annotated, Literal

from pydantic import Field

from app.contracts.ask import AskContract, AskInterpretation, AskPlan, AskQuestion, AskResolveRequest, Term
from app.contracts.bound_search_plan import SearchPlan


class DiscoveryQuestion(AskQuestion):
    allow_ai: Annotated[bool, Field(strict=True)] = False
    people_ids: dict[str, Annotated[str, Field(pattern=r"^person_[0-9a-f]{32}$")]] = Field(default_factory=dict, max_length=8)
    reference_id: Annotated[str, Field(pattern=r"^film_[0-9a-f]{32}$")] | None = None
    evaluation_only: Annotated[bool, Field(strict=True)] = False
    edited_plan: SearchPlan | None = None
    request_id: Annotated[str, Field(pattern=r"^rq_[0-9a-f]{32}$")] | None = None


class DiscoveryInterpretation(AskInterpretation):
    confidence: Annotated[float, Field(strict=True, ge=0, le=1, allow_inf_nan=False)]
    unhandled: list[Term] = Field(max_length=10)


class DiscoveryQuery(AskResolveRequest):
    plan: AskPlan | SearchPlan
    people_ids: dict[str, Annotated[str, Field(pattern=r"^person_[0-9a-f]{32}$")]] = Field(default_factory=dict, max_length=8)
    question: str = Field(min_length=1, max_length=600)
    edited: Annotated[bool, Field(strict=True)] = False
    offset: int = Field(default=0, ge=0, le=100_000)
    semantic_snapshot: Annotated[str, Field(pattern=r"^ds_[0-9a-f]{32}$")] | None = None
    semantic_order: Literal["relevance", "title", "year"] = "relevance"


class DiscoveryIndexAction(AskContract):
    action: Literal["begin", "status", "step", "resume", "cancel"]
    job_id: Annotated[str, Field(pattern=r"^idx_[0-9a-f]{32}$")] | None = None


class DiscoveryCancel(AskContract):
    request_id: Annotated[str, Field(pattern=r"^rq_[0-9a-f]{32}$")]
