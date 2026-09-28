from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AskContract(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


Term = Annotated[str, Field(min_length=1, max_length=100)]


class AskPlan(AskContract):
    genre: Term | None = None
    person: Term | None = None
    person_role: Literal["any", "director", "actor"] = "any"
    country: Term | None = None
    decade: Annotated[int, Field(strict=True, ge=1880, le=2190)] | None = None
    view: Literal["all", "watched", "unwatched"] = "all"
    sort: Literal["title", "year"] = "title"
    direction: Literal["asc", "desc"] = "asc"

    @model_validator(mode="after")
    def validate_constraints(self):
        if self.decade is not None and self.decade % 10:
            raise ValueError("Decade must start in a year divisible by ten")
        if self.person is None and self.person_role != "any":
            raise ValueError("A person role requires a person")
        return self


class AskInterpretation(AskContract):
    status: Literal["ready", "clarify", "unsupported"]
    plan: AskPlan | None

    @model_validator(mode="after")
    def validate_status(self):
        if (self.status == "ready") != (self.plan is not None):
            raise ValueError("Only a complete, supported request may have a plan")
        return self


class AskQuestion(AskContract):
    question: str = Field(min_length=1, max_length=600)
    locale: Literal["zh", "en"] = "zh"


class AskResolveRequest(AskContract):
    plan: AskPlan
    person_id: str | None = Field(default=None, pattern=r"^person_[0-9a-f]{32}$")


class AskQueryRequest(AskResolveRequest):
    confirmed: Literal[True]
    offset: int = Field(default=0, ge=0, le=100_000)
