from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, field_validator, model_validator


class ViewingWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    watched_at: StrictStr | None = None
    rating: StrictInt | None = Field(default=None, ge=1, le=5)
    notes: StrictStr | None = Field(default=None, max_length=10_000)
    revision: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    idempotency_key: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{16,64}$")

    @field_validator("notes")
    @classmethod
    def validate_notes(cls, value):
        if value is not None and "\0" in value:
            raise ValueError("notes must not contain NUL")
        return value if value and value.strip() else None

    @model_validator(mode="after")
    def require_review_retry_key(self):
        if self.model_fields_set & {"rating", "notes"} and not self.idempotency_key:
            raise ValueError("review writes require an idempotency_key")
        return self

    def changes(self):
        return self.model_dump(include={"watched_at", "rating", "notes"}, exclude_unset=True)


class ViewingCreate(ViewingWrite):
    watched_at: StrictStr | None
