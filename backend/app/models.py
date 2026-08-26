from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4
from sqlmodel import Field, SQLModel, JSON, Column


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def event_id() -> str:
    return f"evt_{uuid4().hex}"


class Job(SQLModel, table=True):
    id: str = Field(primary_key=True)
    type: str = Field(index=True)
    status: str = Field(default="queued", index=True)
    payload: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    progress: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    result: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    result_summary: Optional[str] = None
    error: Optional[str] = None
    attempts: int = Field(default=0)
    max_attempts: int = Field(default=1)
    priority: int = Field(default=0, index=True)
    dedupe_key: Optional[str] = Field(default=None, index=True)
    cancel_requested: bool = Field(default=False, index=True)
    created_at: str = Field(default_factory=utc_now_iso, index=True)
    updated_at: str = Field(default_factory=utc_now_iso)
    started_at: Optional[str] = None
    finished_at: Optional[str] = None


class EventRecord(SQLModel, table=True):
    __tablename__ = "events"

    id: str = Field(default_factory=event_id, primary_key=True)
    aggregate_type: str = Field(index=True)
    aggregate_id: Optional[str] = Field(default=None, index=True)
    type: str = Field(index=True)
    actor_type: str = Field(default="system", index=True)
    actor_id: Optional[str] = None
    command_id: Optional[str] = Field(default=None, index=True)
    correlation_id: Optional[str] = Field(default=None, index=True)
    causation_id: Optional[str] = Field(default=None, index=True)
    payload: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    context: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    schema_version: int = Field(default=1)
    occurred_at: str = Field(default_factory=utc_now_iso, index=True)


# Import domain models so SQLModel registers the full fresh Canonical schema.
from app.canonical_models import (  # noqa: E402, F401
    AnalysisResolutionReview,
    AnalysisRun,
    Assertion,
    AssertionEvidence,
    AssertionPredicate,
    AssertionProvenance,
    Concept,
    ConceptAlias,
    Credit,
    CreditProvenance,
    ExternalIdentity,
    ExternalScoreRefreshState,
    Evidence,
    Film,
    FilmCountry,
    FilmCountryProvenance,
    FilmExternalScore,
    FilmProfileState,
    FilmTitle,
    GraphEntity,
    IdentityReview,
    LibraryItem,
    LibraryItemLocatorHistory,
    LocalProfile,
    MediaAsset,
    OperationSnapshot,
    Person,
    SchemaMetadata,
    Setting,
    StructuredMetadataReview,
    Viewing,
)
