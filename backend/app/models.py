from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4
from sqlalchemy import CheckConstraint, Index, UniqueConstraint
from sqlmodel import Field, SQLModel, JSON, Column


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def event_id() -> str:
    return f"evt_{uuid4().hex}"


class WorkflowRun(SQLModel, table=True):
    __tablename__ = "workflow_run"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')",
            name="ck_workflow_run_status",
        ),
        CheckConstraint(
            "subject_type IN ('library', 'film', 'library_item', 'system')",
            name="ck_workflow_run_subject_type",
        ),
        CheckConstraint(
            "length(input_hash) = 64 AND input_hash NOT GLOB '*[^0-9a-f]*'",
            name="ck_workflow_run_input_hash",
        ),
        Index("ix_workflow_run_status_created", "status", "created_at"),
        Index("ix_workflow_run_dedupe_status", "dedupe_key", "status"),
    )

    id: str = Field(default_factory=lambda: f"wf_{uuid4().hex}", primary_key=True)
    type: str = Field(index=True)
    definition_version: str
    subject_type: str = Field(index=True)
    subject_id: Optional[str] = Field(default=None, index=True)
    input_hash: str
    dedupe_key: Optional[str] = Field(default=None, index=True)
    status: str = Field(default="queued", index=True)
    current_step_key: Optional[str] = None
    cancel_requested: bool = Field(default=False, index=True)
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    created_at: str = Field(default_factory=utc_now_iso, index=True)
    updated_at: str = Field(default_factory=utc_now_iso)
    started_at: Optional[str] = None
    finished_at: Optional[str] = None


class WorkflowStep(SQLModel, table=True):
    __tablename__ = "workflow_step"
    __table_args__ = (
        UniqueConstraint("workflow_run_id", "step_key", name="uq_workflow_step_key"),
        UniqueConstraint("workflow_run_id", "position", name="uq_workflow_step_position"),
        CheckConstraint(
            "status IN ('pending', 'queued', 'running', 'succeeded', 'failed', 'cancelled')",
            name="ck_workflow_step_status",
        ),
        CheckConstraint("position >= 0 AND attempt >= 0 AND max_attempts >= 1", name="ck_workflow_step_counts"),
        CheckConstraint(
            "length(input_hash) = 64 AND input_hash NOT GLOB '*[^0-9a-f]*' AND "
            "(output_hash IS NULL OR (length(output_hash) = 64 AND output_hash NOT GLOB '*[^0-9a-f]*'))",
            name="ck_workflow_step_hashes",
        ),
        CheckConstraint(
            "compensation_status IN ('none', 'pending', 'running', 'succeeded', 'failed')",
            name="ck_workflow_step_compensation",
        ),
        Index("ix_workflow_step_run_status", "workflow_run_id", "status", "position"),
    )

    id: str = Field(default_factory=lambda: f"wstep_{uuid4().hex}", primary_key=True)
    workflow_run_id: str = Field(
        foreign_key="workflow_run.id",
        ondelete="CASCADE",
        index=True,
    )
    step_key: str
    position: int
    status: str = Field(default="pending", index=True)
    attempt: int = 0
    max_attempts: int = 1
    retry_policy: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    input_hash: str
    output_hash: Optional[str] = None
    result_summary: Optional[str] = None
    compensation_status: str = "none"
    lease_expires_at: Optional[str] = None
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)
    started_at: Optional[str] = None
    finished_at: Optional[str] = None


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
    workflow_run_id: Optional[str] = Field(
        default=None,
        foreign_key="workflow_run.id",
        ondelete="RESTRICT",
        index=True,
    )
    workflow_step_id: Optional[str] = Field(
        default=None,
        foreign_key="workflow_step.id",
        ondelete="RESTRICT",
        index=True,
    )


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
    ExploreFacetReadModel,
    ExploreFilmReadModel,
    Film,
    FilmCountry,
    FilmCountryProvenance,
    FilmExternalScore,
    FilmDetailReadModel,
    FilmSearchReadModel,
    FilmProfileState,
    FilmTitle,
    GraphEntity,
    GraphEdgeReadModel,
    GraphNodeReadModel,
    IdentityReview,
    LibraryItem,
    LibraryFilmReadModel,
    LibraryItemLocatorHistory,
    LocalProfile,
    MediaAsset,
    OperationSnapshot,
    Person,
    ProjectionState,
    SchemaMetadata,
    Setting,
    StructuredMetadataReview,
    Viewing,
)
