"""Local identity bindings layered over the immutable factual v2 contract.

The original contract remains byte-identical for historical evaluation replay.
Models still receive that factual contract; film IDs are resolved locally.
"""
from typing import Annotated

from pydantic import Field, model_serializer, model_validator

from app.contracts.search_plan import SearchPerson, SearchPlan as FactualSearchPlan

FilmKey = Annotated[str, Field(strict=True, pattern=r"^film_[0-9a-f]{32}$")]


class SearchPlan(FactualSearchPlan):
    film_ids: list[FilmKey] = Field(default_factory=list, max_length=8)
    exclude_film_ids: list[FilmKey] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def unique_film_bindings(self):
        for values in (self.film_ids, self.exclude_film_ids):
            if len(values) != len(set(values)):
                raise ValueError("Duplicate film identities")
        return self

    @model_serializer(mode="wrap")
    def compatible_payload(self, handler):
        payload = handler(self)
        # Preserve existing v2 payloads when no local film binding was needed.
        for field in ("film_ids", "exclude_film_ids"):
            if not payload.get(field):
                payload.pop(field, None)
        return payload
