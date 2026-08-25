from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import CheckConstraint, Column, Index, UniqueConstraint, text
from sqlmodel import Field, JSON, SQLModel


def canonical_utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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


class LegacyMovieAlias(SQLModel, table=True):
    __tablename__ = "legacy_movie_alias"

    legacy_movie_id: str = Field(primary_key=True)
    film_id: str = Field(foreign_key="film.id", ondelete="RESTRICT", index=True)
    library_item_id: str = Field(
        foreign_key="library_item.id",
        ondelete="RESTRICT",
        unique=True,
        index=True,
    )
    legacy_library_status: str | None = None
    created_at: str = Field(default_factory=canonical_utc_now_iso)
    updated_at: str = Field(default_factory=canonical_utc_now_iso)


class IdentityReview(SQLModel, table=True):
    __tablename__ = "identity_review"
    __table_args__ = (
        UniqueConstraint("legacy_movie_id", "reason", name="uq_identity_review_legacy_reason"),
        CheckConstraint("status IN ('open', 'resolved', 'dismissed')", name="ck_identity_review_status"),
    )

    id: str = Field(primary_key=True)
    legacy_movie_id: str = Field(index=True)
    tmdb_film_id: str | None = Field(default=None, foreign_key="film.id", ondelete="RESTRICT")
    imdb_film_id: str | None = Field(default=None, foreign_key="film.id", ondelete="RESTRICT")
    reason: str
    status: str = Field(default="open", index=True)
    created_at: str = Field(default_factory=canonical_utc_now_iso)
    updated_at: str = Field(default_factory=canonical_utc_now_iso)


class CanonicalBackfillRun(SQLModel, table=True):
    __tablename__ = "canonical_backfill_run"

    run_key: str = Field(primary_key=True)
    status: str
    counts: dict[str, int] = Field(sa_column=Column(JSON))
    warning_count: int = 0
    conflict_count: int = 0
    started_at: str
    finished_at: str | None = None


class FilmProfileState(SQLModel, table=True):
    __tablename__ = "film_profile_state"

    profile_id: str = Field(
        primary_key=True,
        foreign_key="local_profile.id",
        ondelete="RESTRICT",
    )
    film_id: str = Field(primary_key=True, foreign_key="film.id", ondelete="RESTRICT")
    favorite: bool = Field(default=False, index=True)
    created_at: str = Field(default_factory=canonical_utc_now_iso)
    updated_at: str = Field(default_factory=canonical_utc_now_iso)


class Viewing(SQLModel, table=True):
    __tablename__ = "viewing"
    __table_args__ = (
        CheckConstraint("rating IS NULL OR (rating >= 1 AND rating <= 5)", name="ck_viewing_rating"),
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
    rating: int | None = Field(default=None, ge=1, le=5)
    review: str | None = None
    tags: list[str] | None = Field(default=None, sa_column=Column(JSON))
    mood: str | None = None
    favorite_scene: str | None = None
    source: str
    source_record_id: str | None = None
    review_status: str = Field(default="confirmed", index=True)
    created_at: str = Field(default_factory=canonical_utc_now_iso)
    updated_at: str = Field(default_factory=canonical_utc_now_iso)
    deleted_at: str | None = Field(default=None, index=True)
