"""Bounded factual query plans. These are data, never SQL or model instructions."""
from typing import Annotated, Literal

from pydantic import Field, model_validator

from app.contracts.ask import AskContract, Term

Year = Annotated[int, Field(strict=True, ge=1870, le=2100)]
Minutes = Annotated[int, Field(strict=True, ge=1, le=10000)]


class SearchPerson(AskContract):
    name: Term
    role: Literal["any", "actor", "director"] = "any"
    exclude: Annotated[bool, Field(strict=True)] = False


class SearchPlan(AskContract):
    version: Literal["search-plan.v2"]
    genres: list[Term] = Field(default_factory=list, max_length=10)
    countries: list[Term] = Field(default_factory=list, max_length=10)
    exclude_genres: list[Term] = Field(default_factory=list, max_length=10)
    exclude_countries: list[Term] = Field(default_factory=list, max_length=10)
    people: list[SearchPerson] = Field(default_factory=list, max_length=8)
    year_min: Year | None = None
    year_max: Year | None = None
    duration_min: Minutes | None = None
    duration_max: Minutes | None = None
    duration_min_exclusive: Annotated[bool, Field(strict=True)] = False
    duration_max_exclusive: Annotated[bool, Field(strict=True)] = False
    view: Literal["all", "watched", "unwatched"] = "all"
    sort: Literal["title", "year"] = "title"
    direction: Literal["asc", "desc"] = "asc"

    @model_validator(mode="after")
    def valid_ranges(self):
        for name in ("year", "duration"):
            lower, upper = getattr(self, name + "_min"), getattr(self, name + "_max")
            if lower is not None and upper is not None and lower > upper:
                raise ValueError("Reversed range")
        if self.duration_min is None and self.duration_min_exclusive or self.duration_max is None and self.duration_max_exclusive:
            raise ValueError("Exclusive bounds require a value")
        if (self.duration_min == self.duration_max and self.duration_min is not None
                and (self.duration_min_exclusive or self.duration_max_exclusive)):
            raise ValueError("Empty exclusive range")
        for name in ("genres", "countries", "exclude_genres", "exclude_countries"):
            values = getattr(self, name)
            if len(values) != len(set(values)):
                raise ValueError("Duplicate facet values")
        people = [(p.name.casefold(), p.role, p.exclude) for p in self.people]
        if len(people) != len(set(people)):
            raise ValueError("Duplicate person clauses")
        return self


class SearchInterpretation(AskContract):
    status: Literal["ready", "clarify", "unsupported"]
    plan: SearchPlan | None
    confidence: Annotated[float, Field(strict=True, ge=0, le=1, allow_inf_nan=False)]
    unhandled: list[Term] = Field(max_length=10)

    @model_validator(mode="after")
    def valid_status(self):
        if (self.status == "ready") != (self.plan is not None):
            raise ValueError("Only a complete request may have a plan")
        return self
