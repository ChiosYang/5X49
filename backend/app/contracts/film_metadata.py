from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, model_validator

MetadataField = Literal["title", "original_title", "year", "overview"]


class MetadataChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["set", "reset"]
    value: StrictStr | StrictInt | None = None

    @model_validator(mode="after")
    def explicit_value(self):
        if (self.action == "set") != ("value" in self.model_fields_set):
            raise ValueError("set requires value; reset must omit value")
        return self


class MetadataUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: str = Field(pattern=r"^[0-9a-f]{64}$")
    idempotency_key: str = Field(pattern=r"^[A-Za-z0-9_-]{16,64}$")
    changes: dict[MetadataField, MetadataChange] = Field(min_length=1, max_length=4)

    @model_validator(mode="after")
    def valid_fields(self):
        for key, change in self.changes.items():
            if change.action == "reset":
                continue
            value = change.value
            if key == "year":
                if value is not None and (type(value) is not int or not 1870 <= value <= 2100):
                    raise ValueError("year must be null or an integer from 1870 to 2100")
            else:
                if value is not None and not isinstance(value, str):
                    raise ValueError(f"{key} must be text or null")
                value = value.strip() if value is not None else None
                maximum = 10000 if key == "overview" else 300
                if value is not None and len(value) > maximum:
                    raise ValueError(f"{key} exceeds {maximum} characters")
                if key == "title" and not value:
                    raise ValueError("title must not be blank")
                change.value = value or None
        return self
