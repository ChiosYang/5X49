from __future__ import annotations

from sqlalchemy import Connection, text

from app.migrations.runner import Migration


SCHEMA_STATEMENTS = (
    """CREATE TABLE IF NOT EXISTS person (
        id VARCHAR PRIMARY KEY NOT NULL,
        canonical_name VARCHAR NOT NULL,
        normalized_name VARCHAR NOT NULL,
        sort_name VARCHAR,
        resolution_status VARCHAR NOT NULL,
        lifecycle_status VARCHAR NOT NULL,
        merged_into_id VARCHAR,
        created_at VARCHAR NOT NULL,
        updated_at VARCHAR NOT NULL,
        CONSTRAINT ck_person_resolution
            CHECK (resolution_status IN ('provisional', 'verified', 'review_required')),
        CONSTRAINT ck_person_lifecycle
            CHECK (lifecycle_status IN ('active', 'merged', 'tombstoned')),
        FOREIGN KEY(id) REFERENCES graph_entity(id) ON DELETE RESTRICT,
        FOREIGN KEY(merged_into_id) REFERENCES person(id) ON DELETE RESTRICT
    )""",
    "CREATE INDEX IF NOT EXISTS ix_person_normalized_name ON person(normalized_name)",
    "CREATE INDEX IF NOT EXISTS ix_person_resolution_status ON person(resolution_status)",
    "CREATE INDEX IF NOT EXISTS ix_person_lifecycle_status ON person(lifecycle_status)",
    "CREATE INDEX IF NOT EXISTS ix_person_merged_into_id ON person(merged_into_id)",
    """CREATE TABLE IF NOT EXISTS credit (
        id VARCHAR PRIMARY KEY NOT NULL,
        film_id VARCHAR NOT NULL,
        person_id VARCHAR NOT NULL,
        department VARCHAR NOT NULL,
        job VARCHAR NOT NULL,
        character VARCHAR NOT NULL,
        billing_order INTEGER,
        semantic_key VARCHAR NOT NULL,
        created_at VARCHAR NOT NULL,
        updated_at VARCHAR NOT NULL,
        CONSTRAINT uq_credit_semantic_key UNIQUE(semantic_key),
        CONSTRAINT ck_credit_billing_order
            CHECK (billing_order IS NULL OR billing_order >= 0),
        CONSTRAINT ck_credit_department CHECK (length(trim(department)) > 0),
        CONSTRAINT ck_credit_job CHECK (length(trim(job)) > 0),
        FOREIGN KEY(film_id) REFERENCES film(id) ON DELETE RESTRICT,
        FOREIGN KEY(person_id) REFERENCES person(id) ON DELETE RESTRICT
    )""",
    "CREATE INDEX IF NOT EXISTS ix_credit_film_id ON credit(film_id)",
    "CREATE INDEX IF NOT EXISTS ix_credit_person_id ON credit(person_id)",
    "CREATE INDEX IF NOT EXISTS ix_credit_film_department ON credit(film_id, department)",
    "CREATE INDEX IF NOT EXISTS ix_credit_person_job ON credit(person_id, job)",
    """CREATE TABLE IF NOT EXISTS credit_provenance (
        id VARCHAR PRIMARY KEY NOT NULL,
        credit_id VARCHAR NOT NULL,
        origin_kind VARCHAR NOT NULL,
        origin_ref VARCHAR NOT NULL,
        observed_at VARCHAR NOT NULL,
        superseded_at VARCHAR,
        CONSTRAINT uq_credit_provenance_origin UNIQUE(credit_id, origin_kind, origin_ref),
        FOREIGN KEY(credit_id) REFERENCES credit(id) ON DELETE RESTRICT
    )""",
    "CREATE INDEX IF NOT EXISTS ix_credit_provenance_credit_id ON credit_provenance(credit_id)",
    """CREATE INDEX IF NOT EXISTS ix_credit_provenance_origin_active
        ON credit_provenance(origin_kind, origin_ref, superseded_at)""",
    """CREATE TABLE IF NOT EXISTS concept (
        id VARCHAR PRIMARY KEY NOT NULL,
        kind VARCHAR NOT NULL,
        canonical_key VARCHAR NOT NULL,
        canonical_name VARCHAR NOT NULL,
        description VARCHAR,
        lifecycle_status VARCHAR NOT NULL,
        merged_into_id VARCHAR,
        created_at VARCHAR NOT NULL,
        updated_at VARCHAR NOT NULL,
        CONSTRAINT uq_concept_kind_key UNIQUE(kind, canonical_key),
        CONSTRAINT ck_concept_kind
            CHECK (kind IN ('genre', 'theme', 'movement', 'visual_style', 'micro_genre')),
        CONSTRAINT ck_concept_lifecycle
            CHECK (lifecycle_status IN ('active', 'merged', 'tombstoned')),
        FOREIGN KEY(id) REFERENCES graph_entity(id) ON DELETE RESTRICT,
        FOREIGN KEY(merged_into_id) REFERENCES concept(id) ON DELETE RESTRICT
    )""",
    "CREATE INDEX IF NOT EXISTS ix_concept_lifecycle_status ON concept(lifecycle_status)",
    "CREATE INDEX IF NOT EXISTS ix_concept_kind_name ON concept(kind, canonical_name)",
    "CREATE INDEX IF NOT EXISTS ix_concept_merged_into_id ON concept(merged_into_id)",
    """CREATE TABLE IF NOT EXISTS concept_alias (
        id VARCHAR PRIMARY KEY NOT NULL,
        concept_id VARCHAR NOT NULL,
        locale VARCHAR NOT NULL,
        alias VARCHAR NOT NULL,
        normalized_alias VARCHAR NOT NULL,
        provenance_ref VARCHAR NOT NULL,
        created_at VARCHAR NOT NULL,
        updated_at VARCHAR NOT NULL,
        CONSTRAINT uq_concept_alias_value UNIQUE(concept_id, locale, normalized_alias),
        FOREIGN KEY(concept_id) REFERENCES concept(id) ON DELETE RESTRICT
    )""",
    "CREATE INDEX IF NOT EXISTS ix_concept_alias_concept_id ON concept_alias(concept_id)",
    "CREATE INDEX IF NOT EXISTS ix_concept_alias_locale_value ON concept_alias(locale, normalized_alias)",
    """CREATE TABLE IF NOT EXISTS film_title (
        id VARCHAR PRIMARY KEY NOT NULL,
        film_id VARCHAR NOT NULL,
        locale VARCHAR NOT NULL,
        title_type VARCHAR NOT NULL,
        title VARCHAR NOT NULL,
        normalized_title VARCHAR NOT NULL,
        origin_kind VARCHAR NOT NULL,
        origin_ref VARCHAR NOT NULL,
        observed_at VARCHAR NOT NULL,
        superseded_at VARCHAR,
        CONSTRAINT uq_film_title_source_value UNIQUE(film_id, locale, title_type, normalized_title, origin_kind, origin_ref),
        CONSTRAINT ck_film_title_type
            CHECK (title_type IN ('canonical', 'original', 'localized', 'alternative')),
        FOREIGN KEY(film_id) REFERENCES film(id) ON DELETE RESTRICT
    )""",
    "CREATE INDEX IF NOT EXISTS ix_film_title_film_id ON film_title(film_id)",
    "CREATE INDEX IF NOT EXISTS ix_film_title_search ON film_title(normalized_title, locale)",
    "CREATE INDEX IF NOT EXISTS ix_film_title_film_active ON film_title(film_id, superseded_at)",
    """CREATE TABLE IF NOT EXISTS film_country (
        id VARCHAR PRIMARY KEY NOT NULL,
        film_id VARCHAR NOT NULL,
        iso_3166_1 VARCHAR NOT NULL,
        created_at VARCHAR NOT NULL,
        updated_at VARCHAR NOT NULL,
        CONSTRAINT uq_film_country_code UNIQUE(film_id, iso_3166_1),
        CONSTRAINT ck_film_country_iso_3166_1
            CHECK (length(iso_3166_1) = 2 AND iso_3166_1 = upper(iso_3166_1)
                AND iso_3166_1 GLOB '[A-Z][A-Z]'),
        FOREIGN KEY(film_id) REFERENCES film(id) ON DELETE RESTRICT
    )""",
    "CREATE INDEX IF NOT EXISTS ix_film_country_film_id ON film_country(film_id)",
    "CREATE INDEX IF NOT EXISTS ix_film_country_code ON film_country(iso_3166_1)",
    """CREATE TABLE IF NOT EXISTS film_country_provenance (
        id VARCHAR PRIMARY KEY NOT NULL,
        film_country_id VARCHAR NOT NULL,
        origin_kind VARCHAR NOT NULL,
        origin_ref VARCHAR NOT NULL,
        observed_at VARCHAR NOT NULL,
        superseded_at VARCHAR,
        CONSTRAINT uq_film_country_provenance_origin UNIQUE(film_country_id, origin_kind, origin_ref),
        FOREIGN KEY(film_country_id) REFERENCES film_country(id) ON DELETE RESTRICT
    )""",
    """CREATE INDEX IF NOT EXISTS ix_film_country_provenance_film_country_id
        ON film_country_provenance(film_country_id)""",
    """CREATE INDEX IF NOT EXISTS ix_film_country_provenance_origin_active
        ON film_country_provenance(origin_kind, origin_ref, superseded_at)""",
    """CREATE TABLE IF NOT EXISTS structured_metadata_review (
        id VARCHAR PRIMARY KEY NOT NULL,
        film_id VARCHAR NOT NULL,
        library_item_id VARCHAR,
        field_kind VARCHAR NOT NULL,
        reason_code VARCHAR NOT NULL,
        raw_value JSON,
        raw_value_hash VARCHAR NOT NULL,
        origin_kind VARCHAR NOT NULL,
        origin_ref VARCHAR NOT NULL,
        review_key VARCHAR NOT NULL,
        status VARCHAR NOT NULL,
        created_at VARCHAR NOT NULL,
        updated_at VARCHAR NOT NULL,
        resolved_at VARCHAR,
        CONSTRAINT uq_structured_metadata_review_key UNIQUE(review_key),
        CONSTRAINT ck_structured_metadata_review_field
            CHECK (field_kind IN ('title', 'country', 'person', 'credit', 'concept')),
        CONSTRAINT ck_structured_metadata_review_status
            CHECK (status IN ('open', 'resolved', 'dismissed')),
        FOREIGN KEY(film_id) REFERENCES film(id) ON DELETE RESTRICT,
        FOREIGN KEY(library_item_id) REFERENCES library_item(id) ON DELETE RESTRICT
    )""",
    "CREATE INDEX IF NOT EXISTS ix_structured_metadata_review_film_id ON structured_metadata_review(film_id)",
    """CREATE INDEX IF NOT EXISTS ix_structured_metadata_review_library_item_id
        ON structured_metadata_review(library_item_id)""",
    "CREATE INDEX IF NOT EXISTS ix_structured_metadata_review_status ON structured_metadata_review(status)",
    """CREATE INDEX IF NOT EXISTS ix_structured_metadata_review_film_status
        ON structured_metadata_review(film_id, status)""",
    """CREATE INDEX IF NOT EXISTS ix_structured_metadata_review_field_status
        ON structured_metadata_review(field_kind, status)""",
)

CHECKSUM_MATERIAL = "\n-- statement --\n".join(SCHEMA_STATEMENTS)


def upgrade(connection: Connection) -> None:
    for statement in SCHEMA_STATEMENTS:
        connection.execute(text(statement))


MIGRATION = Migration(
    version=6,
    name="structured_metadata_schema",
    checksum_material=CHECKSUM_MATERIAL,
    upgrade=upgrade,
)
