"""Submission-only interpretation; restored searches never perform inference."""
from typing import Annotated, Literal

from pydantic import Field

from app.contracts.ask import AskContract, AskInterpretation, AskPlan, AskQuestion, AskResolveRequest, Term


class DiscoveryQuestion(AskQuestion):
    allow_ai: Annotated[bool, Field(strict=True)] = False


class DiscoveryInterpretation(AskInterpretation):
    confidence: Annotated[float, Field(strict=True, ge=0, le=1, allow_inf_nan=False)]
    unhandled: list[Term] = Field(max_length=10)


class DiscoveryQuery(AskResolveRequest):
    question: str = Field(min_length=1, max_length=600)
    edited: Annotated[bool, Field(strict=True)] = False
    offset: int = Field(default=0, ge=0, le=100_000)
