from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import CheckConstraint, Column, Index, UniqueConstraint, text
from sqlmodel import Field, JSON, SQLModel

from app.contracts.analysis_persistence import (
    analysis_resolution_review_id,
    analysis_run_id,
    assertion_evidence_id,
    assertion_id,
    assertion_provenance_id,
    evidence_id,
)


def canonical_utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


FRESH_SCHEMA_EPOCH = "fresh-canonical-v1"


def _opaque_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


class SchemaMetadata(SQLModel, table=True):
    __tablename__ = "schema_metadata"

    id: int = Field(default=1, primary_key=True)
    epoch: str = Field(unique=True)
    created_at: str = Field(default_factory=canonical_utc_now_iso)


class Setting(SQLModel, table=True):
    __tablename__ = "setting"

    key: str = Field(primary_key=True)
    value: Any = Field(sa_column=Column(JSON, nullable=False))
    updated_at: str = Field(default_factory=canonical_utc_now_iso, index=True)


class ProjectionState(SQLModel, table=True):
    __tablename__ = "projection_state"
    __table_args__ = (
        CheckConstraint(
            "status IN ('ready', 'rebuilding', 'failed')",
            name="ck_projection_state_status",
        ),
        CheckConstraint(
            "row_count >= 0 AND length(projection_version) > 0",
            name="ck_projection_state_values",
        ),
        CheckConstraint(
            "digest IS NULL OR (length(digest) = 64 AND digest NOT GLOB '*[^0-9a-f]*')",
            name="ck_projection_state_digest",
        ),
    )

    name: str = Field(primary_key=True)
    projection_version: str
    status: str = Field(default="ready", index=True)
    row_count: int = 0
    digest: str | None = None
    rebuilt_at: str | None = None
    updated_at: str = Field(default_factory=canonical_utc_now_iso)


class LibraryFilmReadModel(SQLModel, table=True):
    __tablename__ = "library_film_read_model"
    __table_args__ = (
        Index("ix_library_film_read_sort", "visible", "sort_title", "release_year"),
        CheckConstraint(
            "length(source_hash) = 64 AND source_hash NOT GLOB '*[^0-9a-f]*'",
            name="ck_library_film_read_hash",
        ),
    )

    film_id: str = Field(
        primary_key=True,
        foreign_key="film.id",
        ondelete="CASCADE",
    )
    sort_title: str = Field(index=True)
    release_year: int | None = Field(default=None, index=True)
    primary_item_id: str | None = Field(default=None, index=True)
    visible: bool = Field(default=True, index=True)
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    source_hash: str
    projection_version: str
    projected_at: str = Field(default_factory=canonical_utc_now_iso)


class FilmDetailReadModel(SQLModel, table=True):
    __tablename__ = "film_detail_read_model"
    __table_args__ = (
        CheckConstraint(
            "length(source_hash) = 64 AND source_hash NOT GLOB '*[^0-9a-f]*'",
            name="ck_film_detail_read_hash",
        ),
    )

    film_id: str = Field(
        primary_key=True,
        foreign_key="film.id",
        ondelete="CASCADE",
    )
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    source_hash: str
    projection_version: str
    projected_at: str = Field(default_factory=canonical_utc_now_iso)


class FilmSearchReadModel(SQLModel, table=True):
    __tablename__ = "film_search_read_model"
    __table_args__ = (
        Index("ix_film_search_read_title_year", "normalized_title", "release_year"),
        CheckConstraint(
            "length(source_hash) = 64 AND source_hash NOT GLOB '*[^0-9a-f]*'",
            name="ck_film_search_read_hash",
        ),
    )

    film_id: str = Field(
        primary_key=True,
        foreign_key="film.id",
        ondelete="CASCADE",
    )
    normalized_title: str = Field(index=True)
    release_year: int | None = Field(default=None, index=True)
    search_text: str
    source_hash: str
    projection_version: str
    projected_at: str = Field(default_factory=canonical_utc_now_iso)


class GraphNodeReadModel(SQLModel, table=True):
    __tablename__ = "graph_node_read_model"
    __table_args__ = (
        CheckConstraint(
            "entity_type IN ('film', 'person', 'concept')",
            name="ck_graph_node_read_entity_type",
        ),
        CheckConstraint(
            "length(source_hash) = 64 AND source_hash NOT GLOB '*[^0-9a-f]*'",
            name="ck_graph_node_read_hash",
        ),
        Index("ix_graph_node_read_type_label", "entity_type", "display_label"),
    )

    entity_id: str = Field(
        primary_key=True,
        foreign_key="graph_entity.id",
        ondelete="CASCADE",
    )
    entity_type: str = Field(index=True)
    display_label: str
    secondary_label: str | None = None
    owned: bool = Field(default=False, index=True)
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    source_hash: str
    projection_version: str
    projected_at: str = Field(default_factory=canonical_utc_now_iso)


class GraphEdgeReadModel(SQLModel, table=True):
    __tablename__ = "graph_edge_read_model"
    __table_args__ = (
        CheckConstraint(
            "edge_kind IN ('credit', 'assertion')",
            name="ck_graph_edge_read_kind",
        ),
        CheckConstraint(
            "length(source_hash) = 64 AND source_hash NOT GLOB '*[^0-9a-f]*'",
            name="ck_graph_edge_read_hash",
        ),
        Index("ix_graph_edge_read_subject_priority", "subject_entity_id", "priority", "edge_id"),
        Index("ix_graph_edge_read_object_priority", "object_entity_id", "priority", "edge_id"),
    )

    edge_id: str = Field(primary_key=True)
    edge_kind: str = Field(index=True)
    subject_entity_id: str = Field(
        foreign_key="graph_entity.id",
        ondelete="CASCADE",
        index=True,
    )
    object_entity_id: str = Field(
        foreign_key="graph_entity.id",
        ondelete="CASCADE",
        index=True,
    )
    relation: str = Field(index=True)
    priority: int = Field(default=100, index=True)
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    source_hash: str
    projection_version: str
    projected_at: str = Field(default_factory=canonical_utc_now_iso)


class GraphEntity(SQLModel, table=True):
    __tablename__ = "graph_entity"
    __table_args__ = (
        CheckConstraint(
            "entity_type IN ('film', 'person', 'concept')",
            name="ck_graph_entity_type",
        ),
        CheckConstraint(
            "lifecycle_status IN ('active', 'merged', 'tombstoned')",
            name="ck_graph_entity_lifecycle",
        ),
    )

    id: str = Field(primary_key=True)
    entity_type: str = Field(index=True)
    lifecycle_status: str = Field(default="active", index=True)
    merged_into_id: str | None = Field(
        default=None,
        foreign_key="graph_entity.id",
        ondelete="RESTRICT",
    )
    created_at: str = Field(default_factory=canonical_utc_now_iso)
    updated_at: str = Field(default_factory=canonical_utc_now_iso)


class LocalProfile(SQLModel, table=True):
    __tablename__ = "local_profile"

    id: str = Field(primary_key=True)
    profile_key: str = Field(unique=True, index=True)
    display_name: str | None = None
    created_at: str = Field(default_factory=canonical_utc_now_iso)
    updated_at: str = Field(default_factory=canonical_utc_now_iso)


class Film(SQLModel, table=True):
    __tablename__ = "film"
    __table_args__ = (
        CheckConstraint(
            "lifecycle_status IN ('active', 'merged', 'tombstoned')",
            name="ck_film_lifecycle",
        ),
        Index("ix_film_release_title", "release_year", "canonical_title"),
        Index("ix_film_merged_into_id", "merged_into_id"),
    )

    id: str = Field(
        primary_key=True,
        foreign_key="graph_entity.id",
        ondelete="RESTRICT",
    )
    canonical_title: str = Field(index=True)
    original_title: str | None = None
    release_date: str | None = None
    release_year: int | None = Field(default=None, index=True)
    runtime_minutes: int | None = None
    overview: str | None = None
    lifecycle_status: str = Field(default="active", index=True)
    merged_into_id: str | None = Field(
        default=None,
        foreign_key="film.id",
        ondelete="RESTRICT",
    )
    created_at: str = Field(default_factory=canonical_utc_now_iso)
    updated_at: str = Field(default_factory=canonical_utc_now_iso)


class ExternalIdentity(SQLModel, table=True):
    __tablename__ = "external_identity"
    __table_args__ = (
        UniqueConstraint("provider", "external_id", name="uq_external_identity_provider_id"),
        Index("ix_external_identity_entity_provider", "entity_id", "provider"),
        Index("ix_external_identity_provider_status", "provider", "identity_status"),
        CheckConstraint(
            "identity_status IN ('active', 'deprecated', 'disputed')",
            name="ck_external_identity_status",
        ),
    )

    id: str = Field(primary_key=True)
    entity_id: str = Field(
        foreign_key="graph_entity.id",
        ondelete="RESTRICT",
        index=True,
    )
    provider: str
    external_id: str
    identity_status: str = Field(default="active", index=True)
    verified_at: str | None = None
    provenance_kind: str
    provenance_ref: str | None = None
    created_at: str = Field(default_factory=canonical_utc_now_iso)
    updated_at: str = Field(default_factory=canonical_utc_now_iso)


class Person(SQLModel, table=True):
    __tablename__ = "person"
    __table_args__ = (
        CheckConstraint(
            "resolution_status IN ('provisional', 'verified', 'review_required')",
            name="ck_person_resolution",
        ),
        CheckConstraint(
            "lifecycle_status IN ('active', 'merged', 'tombstoned')",
            name="ck_person_lifecycle",
        ),
        Index("ix_person_normalized_name", "normalized_name"),
        Index("ix_person_merged_into_id", "merged_into_id"),
    )

    id: str = Field(
        primary_key=True,
        foreign_key="graph_entity.id",
        ondelete="RESTRICT",
    )
    canonical_name: str
    normalized_name: str
    sort_name: str | None = None
    resolution_status: str = Field(default="provisional", index=True)
    lifecycle_status: str = Field(default="active", index=True)
    merged_into_id: str | None = Field(
        default=None,
        foreign_key="person.id",
        ondelete="RESTRICT",
    )
    created_at: str = Field(default_factory=canonical_utc_now_iso)
    updated_at: str = Field(default_factory=canonical_utc_now_iso)


class Credit(SQLModel, table=True):
    __tablename__ = "credit"
    __table_args__ = (
        UniqueConstraint("semantic_key", name="uq_credit_semantic_key"),
        CheckConstraint(
            "billing_order IS NULL OR billing_order >= 0",
            name="ck_credit_billing_order",
        ),
        CheckConstraint("length(trim(department)) > 0", name="ck_credit_department"),
        CheckConstraint("length(trim(job)) > 0", name="ck_credit_job"),
        Index("ix_credit_film_department", "film_id", "department"),
        Index("ix_credit_person_job", "person_id", "job"),
    )

    id: str = Field(primary_key=True)
    film_id: str = Field(foreign_key="film.id", ondelete="RESTRICT", index=True)
    person_id: str = Field(foreign_key="person.id", ondelete="RESTRICT", index=True)
    department: str
    job: str
    character: str = ""
    billing_order: int | None = None
    semantic_key: str
    created_at: str = Field(default_factory=canonical_utc_now_iso)
    updated_at: str = Field(default_factory=canonical_utc_now_iso)


class CreditProvenance(SQLModel, table=True):
    __tablename__ = "credit_provenance"
    __table_args__ = (
        UniqueConstraint(
            "credit_id",
            "origin_kind",
            "origin_ref",
            name="uq_credit_provenance_origin",
        ),
        Index(
            "ix_credit_provenance_origin_active",
            "origin_kind",
            "origin_ref",
            "superseded_at",
        ),
    )

    id: str = Field(primary_key=True)
    credit_id: str = Field(foreign_key="credit.id", ondelete="RESTRICT", index=True)
    origin_kind: str
    origin_ref: str
    observed_at: str
    superseded_at: str | None = None


class Concept(SQLModel, table=True):
    __tablename__ = "concept"
    __table_args__ = (
        UniqueConstraint("kind", "canonical_key", name="uq_concept_kind_key"),
        CheckConstraint(
            "kind IN ('genre', 'theme', 'movement', 'visual_style', 'micro_genre')",
            name="ck_concept_kind",
        ),
        CheckConstraint(
            "lifecycle_status IN ('active', 'merged', 'tombstoned')",
            name="ck_concept_lifecycle",
        ),
        Index("ix_concept_kind_name", "kind", "canonical_name"),
        Index("ix_concept_merged_into_id", "merged_into_id"),
    )

    id: str = Field(
        primary_key=True,
        foreign_key="graph_entity.id",
        ondelete="RESTRICT",
    )
    kind: str
    canonical_key: str
    canonical_name: str
    description: str | None = None
    lifecycle_status: str = Field(default="active", index=True)
    merged_into_id: str | None = Field(
        default=None,
        foreign_key="concept.id",
        ondelete="RESTRICT",
    )
    created_at: str = Field(default_factory=canonical_utc_now_iso)
    updated_at: str = Field(default_factory=canonical_utc_now_iso)


class ConceptAlias(SQLModel, table=True):
    __tablename__ = "concept_alias"
    __table_args__ = (
        UniqueConstraint(
            "concept_id",
            "locale",
            "normalized_alias",
            name="uq_concept_alias_value",
        ),
        Index("ix_concept_alias_locale_value", "locale", "normalized_alias"),
    )

    id: str = Field(primary_key=True)
    concept_id: str = Field(foreign_key="concept.id", ondelete="RESTRICT", index=True)
    locale: str = "und"
    alias: str
    normalized_alias: str
    provenance_ref: str
    created_at: str = Field(default_factory=canonical_utc_now_iso)
    updated_at: str = Field(default_factory=canonical_utc_now_iso)


class FilmTitle(SQLModel, table=True):
    __tablename__ = "film_title"
    __table_args__ = (
        UniqueConstraint(
            "film_id",
            "locale",
            "title_type",
            "normalized_title",
            "origin_kind",
            "origin_ref",
            name="uq_film_title_source_value",
        ),
        CheckConstraint(
            "title_type IN ('canonical', 'original', 'localized', 'alternative')",
            name="ck_film_title_type",
        ),
        Index("ix_film_title_search", "normalized_title", "locale"),
        Index("ix_film_title_film_active", "film_id", "superseded_at"),
    )

    id: str = Field(primary_key=True)
    film_id: str = Field(foreign_key="film.id", ondelete="RESTRICT", index=True)
    locale: str = "und"
    title_type: str
    title: str
    normalized_title: str
    origin_kind: str
    origin_ref: str
    observed_at: str
    superseded_at: str | None = None


class FilmCountry(SQLModel, table=True):
    __tablename__ = "film_country"
    __table_args__ = (
        UniqueConstraint("film_id", "iso_3166_1", name="uq_film_country_code"),
        CheckConstraint(
            "length(iso_3166_1) = 2 AND iso_3166_1 = upper(iso_3166_1) "
            "AND iso_3166_1 GLOB '[A-Z][A-Z]'",
            name="ck_film_country_iso_3166_1",
        ),
        Index("ix_film_country_code", "iso_3166_1"),
    )

    id: str = Field(primary_key=True)
    film_id: str = Field(foreign_key="film.id", ondelete="RESTRICT", index=True)
    iso_3166_1: str
    created_at: str = Field(default_factory=canonical_utc_now_iso)
    updated_at: str = Field(default_factory=canonical_utc_now_iso)


class FilmCountryProvenance(SQLModel, table=True):
    __tablename__ = "film_country_provenance"
    __table_args__ = (
        UniqueConstraint(
            "film_country_id",
            "origin_kind",
            "origin_ref",
            name="uq_film_country_provenance_origin",
        ),
        Index(
            "ix_film_country_provenance_origin_active",
            "origin_kind",
            "origin_ref",
            "superseded_at",
        ),
    )

    id: str = Field(primary_key=True)
    film_country_id: str = Field(
        foreign_key="film_country.id",
        ondelete="RESTRICT",
        index=True,
    )
    origin_kind: str
    origin_ref: str
    observed_at: str
    superseded_at: str | None = None


class LibraryItem(SQLModel, table=True):
    __tablename__ = "library_item"
    __table_args__ = (
        CheckConstraint(
            "availability_status IN ('available', 'missing', 'ignored', 'retired')",
            name="ck_library_item_availability",
        ),
        CheckConstraint(
            "resolution_status IN ('unresolved', 'matched', 'review_required', 'failed')",
            name="ck_library_item_resolution",
        ),
        Index(
            "uq_library_item_active_source",
            "source_instance_id",
            "source_item_key",
            unique=True,
            sqlite_where=text("availability_status <> 'retired'"),
        ),
        Index(
            "ix_library_item_profile_availability_added",
            "profile_id",
            "availability_status",
            "added_at",
        ),
        Index("ix_library_item_source_resolution", "source_instance_id", "resolution_status"),
    )

    id: str = Field(primary_key=True)
    profile_id: str = Field(
        foreign_key="local_profile.id",
        ondelete="RESTRICT",
        index=True,
    )
    film_id: str = Field(foreign_key="film.id", ondelete="RESTRICT", index=True)
    source_type: str
    source_instance_id: str
    source_item_key: str
    display_name: str | None = None
    availability_status: str = Field(default="available", index=True)
    resolution_status: str = Field(default="unresolved", index=True)
    added_at: str | None = None
    last_seen_at: str | None = None
    missing_since: str | None = None
    retired_at: str | None = None
    metadata_source: str | None = None
    metadata_updated_at: str | None = None
    scrape_status: str = Field(default="pending")
    scrape_error: str | None = None
    scraped_at: str | None = None
    match_confidence: float | None = None
    created_at: str = Field(default_factory=canonical_utc_now_iso)
    updated_at: str = Field(default_factory=canonical_utc_now_iso)


class StructuredMetadataReview(SQLModel, table=True):
    __tablename__ = "structured_metadata_review"
    __table_args__ = (
        UniqueConstraint("review_key", name="uq_structured_metadata_review_key"),
        CheckConstraint(
            "field_kind IN ('title', 'country', 'person', 'credit', 'concept')",
            name="ck_structured_metadata_review_field",
        ),
        CheckConstraint(
            "status IN ('open', 'resolved', 'dismissed')",
            name="ck_structured_metadata_review_status",
        ),
        Index(
            "ix_structured_metadata_review_film_status",
            "film_id",
            "status",
        ),
        Index(
            "ix_structured_metadata_review_field_status",
            "field_kind",
            "status",
        ),
    )

    id: str = Field(primary_key=True)
    film_id: str = Field(foreign_key="film.id", ondelete="RESTRICT", index=True)
    library_item_id: str | None = Field(
        default=None,
        foreign_key="library_item.id",
        ondelete="RESTRICT",
        index=True,
    )
    field_kind: str
    reason_code: str
    raw_value: Any | None = Field(default=None, sa_column=Column(JSON))
    raw_value_hash: str
    origin_kind: str
    origin_ref: str
    review_key: str
    status: str = Field(default="open", index=True)
    created_at: str = Field(default_factory=canonical_utc_now_iso)
    updated_at: str = Field(default_factory=canonical_utc_now_iso)
    resolved_at: str | None = None


class AssertionPredicate(SQLModel, table=True):
    __tablename__ = "assertion_predicate"
    __table_args__ = (
        CheckConstraint(
            "subject_entity_type IN ('film', 'person', 'concept')",
            name="ck_assertion_predicate_subject_type",
        ),
        CheckConstraint(
            "object_entity_type IN ('film', 'person', 'concept')",
            name="ck_assertion_predicate_object_type",
        ),
        CheckConstraint(
            "object_concept_kind IS NULL OR object_concept_kind IN "
            "('genre', 'theme', 'movement', 'visual_style', 'micro_genre')",
            name="ck_assertion_predicate_concept_kind",
        ),
        CheckConstraint(
            "evidence_policy IN ('provenance_only', 'preferred', 'optional')",
            name="ck_assertion_predicate_evidence_policy",
        ),
        Index("ix_assertion_predicate_vocabulary", "vocabulary_version"),
    )

    key: str = Field(primary_key=True)
    vocabulary_version: str
    subject_entity_type: str
    object_entity_type: str
    object_concept_kind: str | None = None
    evidence_policy: str
    created_at: str = Field(default_factory=canonical_utc_now_iso)
    updated_at: str = Field(default_factory=canonical_utc_now_iso)


class AnalysisRun(SQLModel, table=True):
    __tablename__ = "analysis_run"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_analysis_run_idempotency_key"),
        CheckConstraint(
            "analysis_kind IN ('genealogy_v2')",
            name="ck_analysis_run_kind",
        ),
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')",
            name="ck_analysis_run_status",
        ),
        CheckConstraint(
            "length(trim(analysis_kind)) > 0 AND length(trim(provider)) > 0 "
            "AND length(trim(model)) > 0 AND length(trim(prompt_version)) > 0 "
            "AND length(trim(schema_version)) > 0 AND length(trim(resolver_version)) > 0 "
            "AND length(trim(policy_version)) > 0 AND length(trim(app_version)) > 0 "
            "AND length(analysis_kind) <= 80 AND length(provider) <= 80 "
            "AND length(model) <= 160 AND length(prompt_version) <= 80 "
            "AND length(schema_version) <= 80 AND length(resolver_version) <= 80 "
            "AND length(policy_version) <= 80 AND length(app_version) <= 80",
            name="ck_analysis_run_required_text",
        ),
        CheckConstraint(
            "length(input_hash) = 64 AND input_hash NOT GLOB '*[^0-9a-f]*' "
            "AND (output_hash IS NULL OR "
            "(length(output_hash) = 64 AND output_hash NOT GLOB '*[^0-9a-f]*')) "
            "AND length(idempotency_key) = 64 "
            "AND idempotency_key NOT GLOB '*[^0-9a-f]*'",
            name="ck_analysis_run_hashes",
        ),
        CheckConstraint(
            "input_tokens IS NULL OR input_tokens >= 0",
            name="ck_analysis_run_input_tokens",
        ),
        CheckConstraint(
            "output_tokens IS NULL OR output_tokens >= 0",
            name="ck_analysis_run_output_tokens",
        ),
        CheckConstraint(
            "(estimated_cost IS NULL AND currency IS NULL) OR "
            "(estimated_cost IS NOT NULL AND currency IS NOT NULL "
            "AND estimated_cost >= 0 AND length(currency) = 3 "
            "AND currency = upper(currency) AND currency GLOB '[A-Z][A-Z][A-Z]')",
            name="ck_analysis_run_cost_currency",
        ),
        CheckConstraint(
            "result_summary IS NULL OR length(result_summary) <= 1200",
            name="ck_analysis_run_summary",
        ),
        CheckConstraint(
            "error_message IS NULL OR length(error_message) <= 500",
            name="ck_analysis_run_error_message",
        ),
        CheckConstraint(
            "(error_category IS NULL OR length(error_category) <= 80) "
            "AND (error_code IS NULL OR length(error_code) <= 80) "
            "AND (correlation_id IS NULL OR length(correlation_id) <= 160) "
            "AND (job_id IS NULL OR length(job_id) <= 160)",
            name="ck_analysis_run_bounded_diagnostics",
        ),
        CheckConstraint(
            "(status = 'queued' AND attempt_count = 0 AND started_at IS NULL "
            "AND finished_at IS NULL AND output_hash IS NULL AND result_summary IS NULL) OR "
            "(status = 'running' AND attempt_count >= 1 AND started_at IS NOT NULL "
            "AND finished_at IS NULL) OR "
            "(status = 'succeeded' AND attempt_count >= 1 AND started_at IS NOT NULL "
            "AND finished_at IS NOT NULL AND output_hash IS NOT NULL "
            "AND result_summary IS NOT NULL AND length(trim(result_summary)) > 0) OR "
            "(status IN ('failed', 'cancelled') AND attempt_count >= 1 "
            "AND started_at IS NOT NULL AND finished_at IS NOT NULL)",
            name="ck_analysis_run_lifecycle",
        ),
        Index(
            "ix_analysis_run_film_kind_status_created",
            "film_id",
            "analysis_kind",
            "status",
            "created_at",
        ),
        Index("ix_analysis_run_correlation_id", "correlation_id"),
        Index("ix_analysis_run_job_id", "job_id"),
    )

    id: str = Field(default_factory=analysis_run_id, primary_key=True)
    film_id: str = Field(foreign_key="film.id", ondelete="RESTRICT", index=True)
    analysis_kind: str
    provider: str
    model: str
    prompt_version: str
    schema_version: str
    resolver_version: str
    policy_version: str
    app_version: str
    input_hash: str
    output_hash: str | None = None
    idempotency_key: str
    status: str = "queued"
    attempt_count: int = 0
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost: float | None = None
    currency: str | None = None
    correlation_id: str | None = None
    job_id: str | None = None
    result_summary: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    error_category: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: str = Field(default_factory=canonical_utc_now_iso)
    updated_at: str = Field(default_factory=canonical_utc_now_iso)


class Assertion(SQLModel, table=True):
    __tablename__ = "assertion"
    __table_args__ = (
        UniqueConstraint("assertion_key", name="uq_assertion_key"),
        CheckConstraint(
            "subject_entity_id <> object_entity_id",
            name="ck_assertion_not_self_referential",
        ),
        CheckConstraint(
            "length(qualifier_hash) = 64 AND qualifier_hash NOT GLOB '*[^0-9a-f]*' "
            "AND length(assertion_key) = 64 AND assertion_key NOT GLOB '*[^0-9a-f]*'",
            name="ck_assertion_hashes",
        ),
        CheckConstraint(
            "source_scope IN ('factual', 'curated', 'inferred')",
            name="ck_assertion_source_scope",
        ),
        CheckConstraint(
            "review_status IN ('proposed', 'accepted', 'rejected')",
            name="ck_assertion_review_status",
        ),
        CheckConstraint(
            "review_method IN ('none', 'import_policy', 'user')",
            name="ck_assertion_review_method",
        ),
        CheckConstraint(
            "(confidence IS NULL AND confidence_method IS NULL) OR "
            "(confidence IS NOT NULL AND confidence_method IS NOT NULL "
            "AND confidence >= 0 AND confidence <= 1 "
            "AND length(trim(confidence_method)) > 0)",
            name="ck_assertion_confidence",
        ),
        CheckConstraint(
            "rationale IS NULL OR length(rationale) <= 600",
            name="ck_assertion_rationale",
        ),
        CheckConstraint(
            "(confidence_method IS NULL OR length(confidence_method) <= 80) "
            "AND (review_policy_version IS NULL OR length(review_policy_version) <= 80)",
            name="ck_assertion_bounded_methods",
        ),
        CheckConstraint(
            "(review_status = 'proposed' AND review_method = 'none' "
            "AND reviewed_by_profile_id IS NULL AND reviewed_at IS NULL "
            "AND review_policy_version IS NULL) OR "
            "(review_status = 'accepted' AND review_method = 'import_policy' "
            "AND reviewed_by_profile_id IS NULL AND reviewed_at IS NOT NULL "
            "AND review_policy_version IS NOT NULL "
            "AND length(trim(review_policy_version)) > 0) OR "
            "(review_status IN ('accepted', 'rejected') AND review_method = 'user' "
            "AND reviewed_by_profile_id IS NOT NULL AND reviewed_at IS NOT NULL "
            "AND review_policy_version IS NULL)",
            name="ck_assertion_review_decision",
        ),
        Index(
            "ix_assertion_subject_predicate_review",
            "subject_entity_id",
            "predicate",
            "review_status",
        ),
        Index(
            "ix_assertion_object_predicate_review",
            "object_entity_id",
            "predicate",
            "review_status",
        ),
        Index("ix_assertion_scope_review", "source_scope", "review_status"),
    )

    id: str = Field(default_factory=assertion_id, primary_key=True)
    subject_entity_id: str = Field(
        foreign_key="graph_entity.id",
        ondelete="RESTRICT",
        index=True,
    )
    object_entity_id: str = Field(
        foreign_key="graph_entity.id",
        ondelete="RESTRICT",
        index=True,
    )
    predicate: str = Field(foreign_key="assertion_predicate.key", ondelete="RESTRICT")
    qualifiers: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    qualifier_hash: str
    assertion_key: str
    source_scope: str
    review_status: str = "proposed"
    review_method: str = "none"
    review_policy_version: str | None = None
    confidence: float | None = None
    confidence_method: str | None = None
    rationale: str | None = None
    reviewed_by_profile_id: str | None = Field(
        default=None,
        foreign_key="local_profile.id",
        ondelete="RESTRICT",
    )
    reviewed_at: str | None = None
    first_seen_at: str
    last_seen_at: str
    superseded_at: str | None = None
    created_at: str = Field(default_factory=canonical_utc_now_iso)
    updated_at: str = Field(default_factory=canonical_utc_now_iso)


class Evidence(SQLModel, table=True):
    __tablename__ = "evidence"
    __table_args__ = (
        UniqueConstraint("evidence_key", name="uq_evidence_key"),
        CheckConstraint(
            "evidence_type IN ('catalog', 'web', 'dataset')",
            name="ck_evidence_type",
        ),
        CheckConstraint(
            "length(evidence_key) = 64 AND evidence_key NOT GLOB '*[^0-9a-f]*' "
            "AND length(content_hash) = 64 AND content_hash NOT GLOB '*[^0-9a-f]*'",
            name="ck_evidence_hashes",
        ),
        CheckConstraint(
            "length(source_uri) <= 2048 AND "
            "(lower(source_uri) LIKE 'http://%' OR lower(source_uri) LIKE 'https://%')",
            name="ck_evidence_http_uri",
        ),
        CheckConstraint(
            "length(trim(source_title)) > 0 AND length(source_title) <= 300 "
            "AND length(trim(claim)) > 0 AND length(claim) <= 400 "
            "AND (publisher IS NULL OR length(publisher) <= 160) "
            "AND length(trim(verification_policy_version)) > 0 "
            "AND length(verification_policy_version) <= 80",
            name="ck_evidence_bounded_text",
        ),
        Index("ix_evidence_content_hash", "content_hash"),
        Index("ix_evidence_source_uri", "source_uri"),
    )

    id: str = Field(default_factory=evidence_id, primary_key=True)
    evidence_key: str
    evidence_type: str
    source_title: str
    source_uri: str
    publisher: str | None = None
    claim: str
    published_at: str | None = None
    retrieved_at: str
    content_hash: str
    verification_policy_version: str
    created_at: str = Field(default_factory=canonical_utc_now_iso)
    updated_at: str = Field(default_factory=canonical_utc_now_iso)


class AssertionEvidence(SQLModel, table=True):
    __tablename__ = "assertion_evidence"
    __table_args__ = (
        UniqueConstraint(
            "assertion_id",
            "evidence_id",
            "stance",
            name="uq_assertion_evidence_stance",
        ),
        CheckConstraint(
            "stance IN ('supports', 'contradicts', 'context')",
            name="ck_assertion_evidence_stance",
        ),
        CheckConstraint(
            "link_status IN ('active', 'revoked')",
            name="ck_assertion_evidence_status",
        ),
        CheckConstraint(
            "(link_status = 'active' AND revoked_at IS NULL) OR "
            "(link_status = 'revoked' AND revoked_at IS NOT NULL)",
            name="ck_assertion_evidence_revocation",
        ),
        Index("ix_assertion_evidence_evidence_id", "evidence_id"),
    )

    id: str = Field(default_factory=assertion_evidence_id, primary_key=True)
    assertion_id: str = Field(
        foreign_key="assertion.id",
        ondelete="RESTRICT",
        index=True,
    )
    evidence_id: str = Field(foreign_key="evidence.id", ondelete="RESTRICT")
    stance: str = "supports"
    link_status: str = "active"
    created_at: str = Field(default_factory=canonical_utc_now_iso)
    revoked_at: str | None = None


class AssertionProvenance(SQLModel, table=True):
    __tablename__ = "assertion_provenance"
    __table_args__ = (
        UniqueConstraint(
            "assertion_id",
            "origin_kind",
            "origin_ref",
            name="uq_assertion_provenance_origin",
        ),
        CheckConstraint(
            "origin_kind IN ('nfo', 'tmdb', 'user', 'analysis_run', 'rule')",
            name="ck_assertion_provenance_origin_kind",
        ),
        CheckConstraint(
            "origin_scope IN ('factual', 'curated', 'inferred')",
            name="ck_assertion_provenance_origin_scope",
        ),
        CheckConstraint(
            "(origin_kind = 'analysis_run' AND analysis_run_id IS NOT NULL) OR "
            "(origin_kind <> 'analysis_run' AND analysis_run_id IS NULL)",
            name="ck_assertion_provenance_analysis_run",
        ),
        CheckConstraint(
            "source_payload_hash IS NULL OR (length(source_payload_hash) = 64 "
            "AND source_payload_hash NOT GLOB '*[^0-9a-f]*')",
            name="ck_assertion_provenance_payload_hash",
        ),
        CheckConstraint(
            "length(trim(origin_ref)) > 0 AND length(origin_ref) <= 300 "
            "AND (source_field IS NULL OR length(source_field) <= 80)",
            name="ck_assertion_provenance_origin_ref",
        ),
        Index("ix_assertion_provenance_analysis_run_id", "analysis_run_id"),
        Index("ix_assertion_provenance_origin_ref", "origin_ref"),
        Index("ix_assertion_provenance_assertion_active", "assertion_id", "superseded_at"),
    )

    id: str = Field(default_factory=assertion_provenance_id, primary_key=True)
    assertion_id: str = Field(
        foreign_key="assertion.id",
        ondelete="RESTRICT",
        index=True,
    )
    origin_kind: str
    origin_scope: str
    origin_ref: str
    analysis_run_id: str | None = Field(
        default=None,
        foreign_key="analysis_run.id",
        ondelete="RESTRICT",
    )
    source_field: str | None = None
    source_payload_hash: str | None = None
    first_observed_at: str
    last_observed_at: str
    superseded_at: str | None = None


class AnalysisResolutionReview(SQLModel, table=True):
    __tablename__ = "analysis_resolution_review"
    __table_args__ = (
        UniqueConstraint("review_key", name="uq_analysis_resolution_review_key"),
        CheckConstraint(
            "candidate_kind IN ('entity_reference', 'evidence', 'assertion', 'output')",
            name="ck_analysis_resolution_review_candidate_kind",
        ),
        CheckConstraint(
            "reason_code IN ('unresolved_reference', 'ambiguous_reference', "
            "'identity_conflict', 'predicate_type_mismatch', 'evidence_uri_blocked', "
            "'evidence_retrieval_failed', 'evidence_policy_rejected', 'invalid_candidate')",
            name="ck_analysis_resolution_review_reason",
        ),
        CheckConstraint(
            "status IN ('open', 'resolved', 'dismissed')",
            name="ck_analysis_resolution_review_status",
        ),
        CheckConstraint(
            "length(CAST(candidate_summary AS TEXT)) <= 4096",
            name="ck_analysis_resolution_review_candidate_size",
        ),
        CheckConstraint(
            "length(candidate_hash) = 64 AND candidate_hash NOT GLOB '*[^0-9a-f]*' "
            "AND length(review_key) = 64 AND review_key NOT GLOB '*[^0-9a-f]*'",
            name="ck_analysis_resolution_review_hashes",
        ),
        CheckConstraint(
            "(status = 'open' AND resolved_at IS NULL AND resolved_entity_id IS NULL) OR "
            "(status IN ('resolved', 'dismissed') AND resolved_at IS NOT NULL)",
            name="ck_analysis_resolution_review_lifecycle",
        ),
        Index("ix_analysis_resolution_review_run_status", "analysis_run_id", "status"),
        Index("ix_analysis_resolution_review_film_status", "film_id", "status"),
        Index("ix_analysis_resolution_review_reason_status", "reason_code", "status"),
    )

    id: str = Field(default_factory=analysis_resolution_review_id, primary_key=True)
    analysis_run_id: str = Field(
        foreign_key="analysis_run.id",
        ondelete="RESTRICT",
        index=True,
    )
    film_id: str = Field(foreign_key="film.id", ondelete="RESTRICT", index=True)
    predicate: str | None = Field(
        default=None,
        foreign_key="assertion_predicate.key",
        ondelete="RESTRICT",
    )
    candidate_kind: str
    reason_code: str
    candidate_summary: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False),
    )
    candidate_hash: str
    review_key: str
    status: str = "open"
    resolved_entity_id: str | None = Field(
        default=None,
        foreign_key="graph_entity.id",
        ondelete="RESTRICT",
    )
    created_at: str = Field(default_factory=canonical_utc_now_iso)
    updated_at: str = Field(default_factory=canonical_utc_now_iso)
    resolved_at: str | None = None


class LibraryItemLocatorHistory(SQLModel, table=True):
    __tablename__ = "library_item_locator_history"
    __table_args__ = (
        UniqueConstraint(
            "library_item_id",
            "source_instance_id",
            "source_item_key",
            name="uq_library_item_locator_history",
        ),
    )

    id: str = Field(primary_key=True)
    library_item_id: str = Field(
        foreign_key="library_item.id",
        ondelete="RESTRICT",
        index=True,
    )
    source_instance_id: str
    source_item_key: str
    observed_from: str
    observed_to: str | None = None
    reason: str


class MediaAsset(SQLModel, table=True):
    __tablename__ = "media_asset"
    __table_args__ = (
        CheckConstraint(
            "((library_item_id IS NULL) <> (film_id IS NULL))",
            name="ck_media_asset_owner_xor",
        ),
        CheckConstraint(
            "availability_status IN ('present', 'missing', 'unknown', 'retired')",
            name="ck_media_asset_availability",
        ),
        Index(
            "uq_media_asset_library_owner_locator",
            "library_item_id",
            "asset_kind",
            "normalized_locator_hash",
            unique=True,
            sqlite_where=text("library_item_id IS NOT NULL"),
        ),
        Index(
            "uq_media_asset_film_owner_locator",
            "film_id",
            "asset_kind",
            "normalized_locator_hash",
            unique=True,
            sqlite_where=text("film_id IS NOT NULL"),
        ),
        Index(
            "ix_media_asset_library_kind_availability",
            "library_item_id",
            "asset_kind",
            "availability_status",
        ),
        Index("ix_media_asset_content_fingerprint", "content_fingerprint"),
    )

    id: str = Field(primary_key=True)
    library_item_id: str | None = Field(
        default=None,
        foreign_key="library_item.id",
        ondelete="RESTRICT",
    )
    film_id: str | None = Field(default=None, foreign_key="film.id", ondelete="RESTRICT")
    asset_kind: str
    locator_kind: str
    locator: str
    normalized_locator_hash: str
    availability_status: str = Field(default="unknown")
    file_size: int | None = None
    file_mtime: float | None = None
    platform_file_id: str | None = Field(default=None, index=True)
    content_fingerprint: str | None = None
    content_hash: str | None = Field(default=None, index=True)
    width: int | None = None
    height: int | None = None
    codec: str | None = None
    bitrate: int | None = None
    duration_seconds: float | None = None
    fps: float | None = None
    dynamic_range: str | None = None
    bit_depth: int | None = None
    stream_metadata: list[dict[str, Any]] | None = Field(default=None, sa_column=Column(JSON))
    source: str
    last_observed_at: str | None = None
    missing_since: str | None = None
    created_at: str = Field(default_factory=canonical_utc_now_iso)
    updated_at: str = Field(default_factory=canonical_utc_now_iso)


class IdentityReview(SQLModel, table=True):
    __tablename__ = "identity_review"
    __table_args__ = (
        UniqueConstraint("review_key", name="uq_identity_review_key"),
        CheckConstraint("status IN ('open', 'resolved', 'dismissed')", name="ck_identity_review_status"),
        Index("ix_identity_review_film_status", "film_id", "status"),
        Index("ix_identity_review_item_status", "library_item_id", "status"),
    )

    id: str = Field(default_factory=lambda: _opaque_id("irev"), primary_key=True)
    film_id: str | None = Field(default=None, foreign_key="film.id", ondelete="RESTRICT")
    library_item_id: str | None = Field(
        default=None,
        foreign_key="library_item.id",
        ondelete="RESTRICT",
    )
    source_instance_id: str
    source_ref: str
    reason_code: str
    candidate_hash: str
    review_key: str
    status: str = Field(default="open", index=True)
    created_at: str = Field(default_factory=canonical_utc_now_iso)
    updated_at: str = Field(default_factory=canonical_utc_now_iso)
    resolved_at: str | None = None


class FilmProfileState(SQLModel, table=True):
    __tablename__ = "film_profile_state"
    __table_args__ = (
        CheckConstraint("rating IS NULL OR (rating >= 1 AND rating <= 5)", name="ck_film_profile_rating"),
    )

    profile_id: str = Field(
        primary_key=True,
        foreign_key="local_profile.id",
        ondelete="RESTRICT",
    )
    film_id: str = Field(primary_key=True, foreign_key="film.id", ondelete="RESTRICT")
    favorite: bool = Field(default=False, index=True)
    rating: int | None = Field(default=None, ge=1, le=5)
    notes: str | None = None
    created_at: str = Field(default_factory=canonical_utc_now_iso)
    updated_at: str = Field(default_factory=canonical_utc_now_iso)


class Viewing(SQLModel, table=True):
    __tablename__ = "viewing"
    __table_args__ = (
        CheckConstraint(
            "watched_at_precision IN ('timestamp', 'date', 'year', 'unknown')",
            name="ck_viewing_precision",
        ),
        CheckConstraint(
            "review_status IN ('confirmed', 'needs_review', 'rejected')",
            name="ck_viewing_review_status",
        ),
        UniqueConstraint(
            "profile_id",
            "source",
            "source_record_id",
            name="uq_viewing_source_record",
        ),
        Index("ix_viewing_profile_watched_at", "profile_id", "watched_at"),
        Index("ix_viewing_profile_film_watched_at", "profile_id", "film_id", "watched_at"),
    )

    id: str = Field(primary_key=True)
    profile_id: str = Field(
        foreign_key="local_profile.id",
        ondelete="RESTRICT",
        index=True,
    )
    film_id: str = Field(foreign_key="film.id", ondelete="RESTRICT", index=True)
    watched_at: str | None = None
    watched_at_precision: str = "unknown"
    source: str
    source_record_id: str | None = None
    review_status: str = Field(default="confirmed", index=True)
    created_at: str = Field(default_factory=canonical_utc_now_iso)
    updated_at: str = Field(default_factory=canonical_utc_now_iso)
    deleted_at: str | None = Field(default=None, index=True)


class FilmExternalScore(SQLModel, table=True):
    __tablename__ = "film_external_score"
    __table_args__ = (
        UniqueConstraint(
            "film_id",
            "source",
            "kind",
            "list_name",
            "edition",
            name="uq_film_external_score_identity",
        ),
        CheckConstraint("kind IN ('rating', 'rank')", name="ck_film_external_score_kind"),
        CheckConstraint(
            "(kind = 'rating' AND value IS NOT NULL AND scale IS NOT NULL AND rank IS NULL) OR "
            "(kind = 'rank' AND rank IS NOT NULL AND value IS NULL AND scale IS NULL)",
            name="ck_film_external_score_value",
        ),
        Index("ix_film_external_score_film_source", "film_id", "source"),
    )

    id: str = Field(default_factory=lambda: _opaque_id("score"), primary_key=True)
    film_id: str = Field(foreign_key="film.id", ondelete="RESTRICT", index=True)
    source: str
    label: str
    kind: str
    value: float | None = None
    scale: float | None = None
    rank: int | None = None
    previous_rank: int | None = None
    votes: int | None = None
    list_name: str = ""
    edition: str = ""
    source_uri: str | None = None
    matched_by: str | None = None
    confidence: float | None = None
    fetched_at: str
    expires_at: str | None = None
    created_at: str = Field(default_factory=canonical_utc_now_iso)
    updated_at: str = Field(default_factory=canonical_utc_now_iso)


class ExternalScoreRefreshState(SQLModel, table=True):
    __tablename__ = "external_score_refresh_state"
    __table_args__ = (
        UniqueConstraint("film_id", "source", name="uq_external_score_refresh_film_source"),
        CheckConstraint(
            "status IN ('idle', 'running', 'succeeded', 'failed')",
            name="ck_external_score_refresh_status",
        ),
    )

    id: str = Field(default_factory=lambda: _opaque_id("sref"), primary_key=True)
    film_id: str = Field(foreign_key="film.id", ondelete="RESTRICT", index=True)
    source: str
    status: str = Field(default="idle", index=True)
    error_code: str | None = None
    error_message: str | None = None
    refreshed_at: str | None = None
    created_at: str = Field(default_factory=canonical_utc_now_iso)
    updated_at: str = Field(default_factory=canonical_utc_now_iso)


class OperationSnapshot(SQLModel, table=True):
    __tablename__ = "operation_snapshot"
    __table_args__ = (
        CheckConstraint(
            "aggregate_type IN ('film', 'library_item')",
            name="ck_operation_snapshot_aggregate_type",
        ),
        CheckConstraint(
            "status IN ('available', 'restored', 'expired')",
            name="ck_operation_snapshot_status",
        ),
        UniqueConstraint("event_id", name="uq_operation_snapshot_event"),
        Index("ix_operation_snapshot_aggregate", "aggregate_type", "aggregate_id", "created_at"),
    )

    id: str = Field(default_factory=lambda: _opaque_id("snap"), primary_key=True)
    event_id: str = Field(foreign_key="events.id", ondelete="RESTRICT", index=True)
    aggregate_type: str
    aggregate_id: str
    operation_kind: str
    before_state: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    after_state: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    optimistic_hash: str
    backup_manifest_ref: str | None = None
    status: str = Field(default="available", index=True)
    created_at: str = Field(default_factory=canonical_utc_now_iso)
    restored_at: str | None = None
