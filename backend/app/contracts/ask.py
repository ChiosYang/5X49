from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator, model_validator


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

    duration_min: Annotated[int, Field(strict=True, ge=1, le=10000)] | None = None
    duration_max: Annotated[int, Field(strict=True, ge=1, le=10000)] | None = None
    duration_min_inclusive: Annotated[bool, Field(strict=True)] = True
    duration_max_inclusive: Annotated[bool, Field(strict=True)] = True
    rating_min: Annotated[int, Field(strict=True, ge=1, le=5)] | None = None
    rating_max: Annotated[int, Field(strict=True, ge=1, le=5)] | None = None

    @model_validator(mode="after")
    def validate_constraints(self):
        if self.decade is not None and self.decade % 10:
            raise ValueError("Decade must start in a year divisible by ten")
        if self.person is None and self.person_role != "any":
            raise ValueError("A person role requires a person")
        for prefix in ("duration", "rating"):
            lower, upper = getattr(self, prefix + "_min"), getattr(self, prefix + "_max")
            if lower is not None and upper is not None:
                if lower > upper or (prefix == "duration" and lower == upper
                                    and not (self.duration_min_inclusive and self.duration_max_inclusive)):
                    raise ValueError("Range must not be reversed or empty")
        for bound in ("min", "max"):
            if getattr(self, "duration_" + bound) is None and not getattr(self, "duration_" + bound + "_inclusive"):
                raise ValueError("An exclusive comparison requires a duration bound")
        return self


class AskInterpretation(AskContract):
    status: Literal["ready", "clarify", "unsupported"]
    plan: AskPlan | None
    reason: Literal["negation", "similarity", "recommendation", "unsupported_filter", "multiple_values",
                    "non_search", "ambiguous_rating", "ambiguous_duration", "ambiguous_request"] | None = None
    _observation: dict | None = PrivateAttr(default=None)

    @model_validator(mode="after")
    def validate_status(self):
        if (self.status == "ready") != (self.plan is not None):
            raise ValueError("Only a complete, supported request may have a plan")
        if self.status == "ready" and self.reason is not None:
            raise ValueError("A ready plan cannot include an unresolved requirement")
        return self


class AskQuestion(AskContract):
    question: str = Field(min_length=1, max_length=600)
    locale: Literal["zh", "en"] = "zh"
    provider_consent: Literal[True]
    provider_disclosure: str = Field(pattern=r"^ask_target_[0-9a-f]{64}$")

    @field_validator("provider_consent", mode="before")
    @classmethod
    def literal_consent(cls, value):
        if value is not True:
            raise ValueError("Explicit boolean provider consent is required")
        return value


class AskResolveRequest(AskContract):
    plan: AskPlan
    person_id: str | None = Field(default=None, pattern=r"^person_[0-9a-f]{32}$")


class AskQueryRequest(AskResolveRequest):
    confirmed: Literal[True]

    @field_validator("confirmed", mode="before")
    @classmethod
    def literal_confirmation(cls, value):
        if value is not True:
            raise ValueError("Explicit boolean confirmation is required")
        return value
    offset: int = Field(default=0, ge=0, le=100_000)
