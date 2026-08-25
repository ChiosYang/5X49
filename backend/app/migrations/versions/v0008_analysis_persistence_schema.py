from __future__ import annotations

import json

from sqlalchemy import Connection, text

from app.contracts.analysis_persistence import predicate_seed_rows
from app.migrations.runner import Migration


SEED_TIMESTAMP = "2026-08-25T00:00:00Z"
PREDICATE_ROWS = predicate_seed_rows()

SCHEMA_STATEMENTS = (
    """CREATE TABLE IF NOT EXISTS assertion_predicate (
        key VARCHAR PRIMARY KEY NOT NULL,
        vocabulary_version VARCHAR NOT NULL,
        subject_entity_type VARCHAR NOT NULL,
        object_entity_type VARCHAR NOT NULL,
        object_concept_kind VARCHAR,
        evidence_policy VARCHAR NOT NULL,
        created_at VARCHAR NOT NULL,
        updated_at VARCHAR NOT NULL,
        CONSTRAINT ck_assertion_predicate_subject_type
            CHECK (subject_entity_type IN ('film', 'person', 'concept')),
        CONSTRAINT ck_assertion_predicate_object_type
            CHECK (object_entity_type IN ('film', 'person', 'concept')),
        CONSTRAINT ck_assertion_predicate_concept_kind
            CHECK (object_concept_kind IS NULL OR object_concept_kind IN
                ('genre', 'theme', 'movement', 'visual_style', 'micro_genre')),
        CONSTRAINT ck_assertion_predicate_evidence_policy
            CHECK (evidence_policy IN ('provenance_only', 'preferred', 'optional'))
    )""",
    "CREATE INDEX IF NOT EXISTS ix_assertion_predicate_vocabulary ON assertion_predicate(vocabulary_version)",
    """CREATE TABLE IF NOT EXISTS analysis_run (
        id VARCHAR PRIMARY KEY NOT NULL,
        film_id VARCHAR NOT NULL,
        analysis_kind VARCHAR NOT NULL,
        provider VARCHAR NOT NULL,
        model VARCHAR NOT NULL,
        prompt_version VARCHAR NOT NULL,
        schema_version VARCHAR NOT NULL,
        resolver_version VARCHAR NOT NULL,
        policy_version VARCHAR NOT NULL,
        app_version VARCHAR NOT NULL,
        input_hash VARCHAR NOT NULL,
        output_hash VARCHAR,
        idempotency_key VARCHAR NOT NULL,
        status VARCHAR NOT NULL,
        attempt_count INTEGER NOT NULL,
        input_tokens INTEGER,
        output_tokens INTEGER,
        estimated_cost FLOAT,
        currency VARCHAR,
        correlation_id VARCHAR,
        job_id VARCHAR,
        result_summary VARCHAR,
        started_at VARCHAR,
        finished_at VARCHAR,
        error_category VARCHAR,
        error_code VARCHAR,
        error_message VARCHAR,
        created_at VARCHAR NOT NULL,
        updated_at VARCHAR NOT NULL,
        CONSTRAINT uq_analysis_run_idempotency_key UNIQUE(idempotency_key),
        CONSTRAINT ck_analysis_run_kind CHECK (analysis_kind IN ('genealogy_v2')),
        CONSTRAINT ck_analysis_run_status
            CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')),
        CONSTRAINT ck_analysis_run_required_text CHECK (
            length(trim(analysis_kind)) > 0 AND length(trim(provider)) > 0
            AND length(trim(model)) > 0 AND length(trim(prompt_version)) > 0
            AND length(trim(schema_version)) > 0 AND length(trim(resolver_version)) > 0
            AND length(trim(policy_version)) > 0 AND length(trim(app_version)) > 0
            AND length(analysis_kind) <= 80 AND length(provider) <= 80
            AND length(model) <= 160 AND length(prompt_version) <= 80
            AND length(schema_version) <= 80 AND length(resolver_version) <= 80
            AND length(policy_version) <= 80 AND length(app_version) <= 80
        ),
        CONSTRAINT ck_analysis_run_hashes CHECK (
            length(input_hash) = 64 AND input_hash NOT GLOB '*[^0-9a-f]*'
            AND (output_hash IS NULL OR
                (length(output_hash) = 64 AND output_hash NOT GLOB '*[^0-9a-f]*'))
            AND length(idempotency_key) = 64
            AND idempotency_key NOT GLOB '*[^0-9a-f]*'
        ),
        CONSTRAINT ck_analysis_run_input_tokens CHECK (input_tokens IS NULL OR input_tokens >= 0),
        CONSTRAINT ck_analysis_run_output_tokens CHECK (output_tokens IS NULL OR output_tokens >= 0),
        CONSTRAINT ck_analysis_run_cost_currency CHECK (
            (estimated_cost IS NULL AND currency IS NULL) OR
            (estimated_cost IS NOT NULL AND currency IS NOT NULL
                AND estimated_cost >= 0 AND length(currency) = 3
                AND currency = upper(currency) AND currency GLOB '[A-Z][A-Z][A-Z]')
        ),
        CONSTRAINT ck_analysis_run_summary CHECK (result_summary IS NULL OR length(result_summary) <= 1200),
        CONSTRAINT ck_analysis_run_error_message CHECK (error_message IS NULL OR length(error_message) <= 500),
        CONSTRAINT ck_analysis_run_bounded_diagnostics CHECK (
            (error_category IS NULL OR length(error_category) <= 80)
            AND (error_code IS NULL OR length(error_code) <= 80)
            AND (correlation_id IS NULL OR length(correlation_id) <= 160)
            AND (job_id IS NULL OR length(job_id) <= 160)
        ),
        CONSTRAINT ck_analysis_run_lifecycle CHECK (
            (status = 'queued' AND attempt_count = 0 AND started_at IS NULL
                AND finished_at IS NULL AND output_hash IS NULL AND result_summary IS NULL) OR
            (status = 'running' AND attempt_count >= 1 AND started_at IS NOT NULL
                AND finished_at IS NULL) OR
            (status = 'succeeded' AND attempt_count >= 1 AND started_at IS NOT NULL
                AND finished_at IS NOT NULL AND output_hash IS NOT NULL
                AND result_summary IS NOT NULL AND length(trim(result_summary)) > 0) OR
            (status IN ('failed', 'cancelled') AND attempt_count >= 1
                AND started_at IS NOT NULL AND finished_at IS NOT NULL)
        ),
        FOREIGN KEY(film_id) REFERENCES film(id) ON DELETE RESTRICT
    )""",
    "CREATE INDEX IF NOT EXISTS ix_analysis_run_film_id ON analysis_run(film_id)",
    """CREATE INDEX IF NOT EXISTS ix_analysis_run_film_kind_status_created
        ON analysis_run(film_id, analysis_kind, status, created_at)""",
    "CREATE INDEX IF NOT EXISTS ix_analysis_run_correlation_id ON analysis_run(correlation_id)",
    "CREATE INDEX IF NOT EXISTS ix_analysis_run_job_id ON analysis_run(job_id)",
    """CREATE TABLE IF NOT EXISTS assertion (
        id VARCHAR PRIMARY KEY NOT NULL,
        subject_entity_id VARCHAR NOT NULL,
        object_entity_id VARCHAR NOT NULL,
        predicate VARCHAR NOT NULL,
        qualifiers JSON NOT NULL,
        qualifier_hash VARCHAR NOT NULL,
        assertion_key VARCHAR NOT NULL,
        source_scope VARCHAR NOT NULL,
        review_status VARCHAR NOT NULL,
        review_method VARCHAR NOT NULL,
        review_policy_version VARCHAR,
        confidence FLOAT,
        confidence_method VARCHAR,
        rationale VARCHAR,
        reviewed_by_profile_id VARCHAR,
        reviewed_at VARCHAR,
        first_seen_at VARCHAR NOT NULL,
        last_seen_at VARCHAR NOT NULL,
        superseded_at VARCHAR,
        created_at VARCHAR NOT NULL,
        updated_at VARCHAR NOT NULL,
        CONSTRAINT uq_assertion_key UNIQUE(assertion_key),
        CONSTRAINT ck_assertion_not_self_referential CHECK (subject_entity_id <> object_entity_id),
        CONSTRAINT ck_assertion_hashes CHECK (
            length(qualifier_hash) = 64 AND qualifier_hash NOT GLOB '*[^0-9a-f]*'
            AND length(assertion_key) = 64 AND assertion_key NOT GLOB '*[^0-9a-f]*'
        ),
        CONSTRAINT ck_assertion_source_scope CHECK (source_scope IN ('factual', 'curated', 'inferred')),
        CONSTRAINT ck_assertion_review_status CHECK (review_status IN ('proposed', 'accepted', 'rejected')),
        CONSTRAINT ck_assertion_review_method CHECK (review_method IN ('none', 'import_policy', 'user')),
        CONSTRAINT ck_assertion_confidence CHECK (
            (confidence IS NULL AND confidence_method IS NULL) OR
            (confidence IS NOT NULL AND confidence_method IS NOT NULL
                AND confidence >= 0 AND confidence <= 1 AND length(trim(confidence_method)) > 0)
        ),
        CONSTRAINT ck_assertion_rationale CHECK (rationale IS NULL OR length(rationale) <= 600),
        CONSTRAINT ck_assertion_bounded_methods CHECK (
            (confidence_method IS NULL OR length(confidence_method) <= 80)
            AND (review_policy_version IS NULL OR length(review_policy_version) <= 80)
        ),
        CONSTRAINT ck_assertion_review_decision CHECK (
            (review_status = 'proposed' AND review_method = 'none'
                AND reviewed_by_profile_id IS NULL AND reviewed_at IS NULL
                AND review_policy_version IS NULL) OR
            (review_status = 'accepted' AND review_method = 'import_policy'
                AND reviewed_by_profile_id IS NULL AND reviewed_at IS NOT NULL
                AND review_policy_version IS NOT NULL
                AND length(trim(review_policy_version)) > 0) OR
            (review_status IN ('accepted', 'rejected') AND review_method = 'user'
                AND reviewed_by_profile_id IS NOT NULL AND reviewed_at IS NOT NULL
                AND review_policy_version IS NULL)
        ),
        FOREIGN KEY(subject_entity_id) REFERENCES graph_entity(id) ON DELETE RESTRICT,
        FOREIGN KEY(object_entity_id) REFERENCES graph_entity(id) ON DELETE RESTRICT,
        FOREIGN KEY(predicate) REFERENCES assertion_predicate(key) ON DELETE RESTRICT,
        FOREIGN KEY(reviewed_by_profile_id) REFERENCES local_profile(id) ON DELETE RESTRICT
    )""",
    "CREATE INDEX IF NOT EXISTS ix_assertion_subject_entity_id ON assertion(subject_entity_id)",
    "CREATE INDEX IF NOT EXISTS ix_assertion_object_entity_id ON assertion(object_entity_id)",
    """CREATE INDEX IF NOT EXISTS ix_assertion_subject_predicate_review
        ON assertion(subject_entity_id, predicate, review_status)""",
    """CREATE INDEX IF NOT EXISTS ix_assertion_object_predicate_review
        ON assertion(object_entity_id, predicate, review_status)""",
    "CREATE INDEX IF NOT EXISTS ix_assertion_scope_review ON assertion(source_scope, review_status)",
    """CREATE TABLE IF NOT EXISTS evidence (
        id VARCHAR PRIMARY KEY NOT NULL,
        evidence_key VARCHAR NOT NULL,
        evidence_type VARCHAR NOT NULL,
        source_title VARCHAR NOT NULL,
        source_uri VARCHAR NOT NULL,
        publisher VARCHAR,
        claim VARCHAR NOT NULL,
        published_at VARCHAR,
        retrieved_at VARCHAR NOT NULL,
        content_hash VARCHAR NOT NULL,
        verification_policy_version VARCHAR NOT NULL,
        created_at VARCHAR NOT NULL,
        updated_at VARCHAR NOT NULL,
        CONSTRAINT uq_evidence_key UNIQUE(evidence_key),
        CONSTRAINT ck_evidence_type CHECK (evidence_type IN ('catalog', 'web', 'dataset')),
        CONSTRAINT ck_evidence_hashes CHECK (
            length(evidence_key) = 64 AND evidence_key NOT GLOB '*[^0-9a-f]*'
            AND length(content_hash) = 64 AND content_hash NOT GLOB '*[^0-9a-f]*'
        ),
        CONSTRAINT ck_evidence_http_uri CHECK (
            length(source_uri) <= 2048 AND
            (lower(source_uri) LIKE 'http://%' OR lower(source_uri) LIKE 'https://%')
        ),
        CONSTRAINT ck_evidence_bounded_text CHECK (
            length(trim(source_title)) > 0 AND length(source_title) <= 300
            AND length(trim(claim)) > 0 AND length(claim) <= 400
            AND (publisher IS NULL OR length(publisher) <= 160)
            AND length(trim(verification_policy_version)) > 0
            AND length(verification_policy_version) <= 80
        )
    )""",
    "CREATE INDEX IF NOT EXISTS ix_evidence_content_hash ON evidence(content_hash)",
    "CREATE INDEX IF NOT EXISTS ix_evidence_source_uri ON evidence(source_uri)",
    """CREATE TABLE IF NOT EXISTS assertion_evidence (
        id VARCHAR PRIMARY KEY NOT NULL,
        assertion_id VARCHAR NOT NULL,
        evidence_id VARCHAR NOT NULL,
        stance VARCHAR NOT NULL,
        link_status VARCHAR NOT NULL,
        created_at VARCHAR NOT NULL,
        revoked_at VARCHAR,
        CONSTRAINT uq_assertion_evidence_stance UNIQUE(assertion_id, evidence_id, stance),
        CONSTRAINT ck_assertion_evidence_stance CHECK (stance IN ('supports', 'contradicts', 'context')),
        CONSTRAINT ck_assertion_evidence_status CHECK (link_status IN ('active', 'revoked')),
        CONSTRAINT ck_assertion_evidence_revocation CHECK (
            (link_status = 'active' AND revoked_at IS NULL) OR
            (link_status = 'revoked' AND revoked_at IS NOT NULL)
        ),
        FOREIGN KEY(assertion_id) REFERENCES assertion(id) ON DELETE RESTRICT,
        FOREIGN KEY(evidence_id) REFERENCES evidence(id) ON DELETE RESTRICT
    )""",
    "CREATE INDEX IF NOT EXISTS ix_assertion_evidence_assertion_id ON assertion_evidence(assertion_id)",
    "CREATE INDEX IF NOT EXISTS ix_assertion_evidence_evidence_id ON assertion_evidence(evidence_id)",
    """CREATE TABLE IF NOT EXISTS assertion_provenance (
        id VARCHAR PRIMARY KEY NOT NULL,
        assertion_id VARCHAR NOT NULL,
        origin_kind VARCHAR NOT NULL,
        origin_scope VARCHAR NOT NULL,
        origin_ref VARCHAR NOT NULL,
        analysis_run_id VARCHAR,
        source_field VARCHAR,
        source_payload_hash VARCHAR,
        first_observed_at VARCHAR NOT NULL,
        last_observed_at VARCHAR NOT NULL,
        superseded_at VARCHAR,
        CONSTRAINT uq_assertion_provenance_origin UNIQUE(assertion_id, origin_kind, origin_ref),
        CONSTRAINT ck_assertion_provenance_origin_kind
            CHECK (origin_kind IN ('nfo', 'tmdb', 'migration', 'user', 'analysis_run', 'rule')),
        CONSTRAINT ck_assertion_provenance_origin_scope
            CHECK (origin_scope IN ('factual', 'curated', 'inferred')),
        CONSTRAINT ck_assertion_provenance_analysis_run CHECK (
            (origin_kind = 'analysis_run' AND analysis_run_id IS NOT NULL) OR
            (origin_kind <> 'analysis_run' AND analysis_run_id IS NULL)
        ),
        CONSTRAINT ck_assertion_provenance_payload_hash CHECK (
            source_payload_hash IS NULL OR (length(source_payload_hash) = 64
                AND source_payload_hash NOT GLOB '*[^0-9a-f]*')
        ),
        CONSTRAINT ck_assertion_provenance_origin_ref CHECK (
            length(trim(origin_ref)) > 0 AND length(origin_ref) <= 300
            AND (source_field IS NULL OR length(source_field) <= 80)
        ),
        FOREIGN KEY(assertion_id) REFERENCES assertion(id) ON DELETE RESTRICT,
        FOREIGN KEY(analysis_run_id) REFERENCES analysis_run(id) ON DELETE RESTRICT
    )""",
    "CREATE INDEX IF NOT EXISTS ix_assertion_provenance_assertion_id ON assertion_provenance(assertion_id)",
    "CREATE INDEX IF NOT EXISTS ix_assertion_provenance_analysis_run_id ON assertion_provenance(analysis_run_id)",
    "CREATE INDEX IF NOT EXISTS ix_assertion_provenance_origin_ref ON assertion_provenance(origin_ref)",
    """CREATE INDEX IF NOT EXISTS ix_assertion_provenance_assertion_active
        ON assertion_provenance(assertion_id, superseded_at)""",
    """CREATE TABLE IF NOT EXISTS analysis_resolution_review (
        id VARCHAR PRIMARY KEY NOT NULL,
        analysis_run_id VARCHAR NOT NULL,
        film_id VARCHAR NOT NULL,
        predicate VARCHAR,
        candidate_kind VARCHAR NOT NULL,
        reason_code VARCHAR NOT NULL,
        candidate_summary JSON NOT NULL,
        candidate_hash VARCHAR NOT NULL,
        review_key VARCHAR NOT NULL,
        status VARCHAR NOT NULL,
        resolved_entity_id VARCHAR,
        created_at VARCHAR NOT NULL,
        updated_at VARCHAR NOT NULL,
        resolved_at VARCHAR,
        CONSTRAINT uq_analysis_resolution_review_key UNIQUE(review_key),
        CONSTRAINT ck_analysis_resolution_review_candidate_kind
            CHECK (candidate_kind IN ('entity_reference', 'evidence', 'assertion', 'output')),
        CONSTRAINT ck_analysis_resolution_review_reason CHECK (
            reason_code IN ('unresolved_reference', 'ambiguous_reference',
                'identity_conflict', 'predicate_type_mismatch', 'evidence_uri_blocked',
                'evidence_retrieval_failed', 'evidence_policy_rejected', 'invalid_candidate')
        ),
        CONSTRAINT ck_analysis_resolution_review_status
            CHECK (status IN ('open', 'resolved', 'dismissed')),
        CONSTRAINT ck_analysis_resolution_review_candidate_size
            CHECK (length(CAST(candidate_summary AS TEXT)) <= 4096),
        CONSTRAINT ck_analysis_resolution_review_hashes CHECK (
            length(candidate_hash) = 64 AND candidate_hash NOT GLOB '*[^0-9a-f]*'
            AND length(review_key) = 64 AND review_key NOT GLOB '*[^0-9a-f]*'
        ),
        CONSTRAINT ck_analysis_resolution_review_lifecycle CHECK (
            (status = 'open' AND resolved_at IS NULL AND resolved_entity_id IS NULL) OR
            (status IN ('resolved', 'dismissed') AND resolved_at IS NOT NULL)
        ),
        FOREIGN KEY(analysis_run_id) REFERENCES analysis_run(id) ON DELETE RESTRICT,
        FOREIGN KEY(film_id) REFERENCES film(id) ON DELETE RESTRICT,
        FOREIGN KEY(predicate) REFERENCES assertion_predicate(key) ON DELETE RESTRICT,
        FOREIGN KEY(resolved_entity_id) REFERENCES graph_entity(id) ON DELETE RESTRICT
    )""",
    """CREATE INDEX IF NOT EXISTS ix_analysis_resolution_review_analysis_run_id
        ON analysis_resolution_review(analysis_run_id)""",
    "CREATE INDEX IF NOT EXISTS ix_analysis_resolution_review_film_id ON analysis_resolution_review(film_id)",
    """CREATE INDEX IF NOT EXISTS ix_analysis_resolution_review_run_status
        ON analysis_resolution_review(analysis_run_id, status)""",
    """CREATE INDEX IF NOT EXISTS ix_analysis_resolution_review_film_status
        ON analysis_resolution_review(film_id, status)""",
    """CREATE INDEX IF NOT EXISTS ix_analysis_resolution_review_reason_status
        ON analysis_resolution_review(reason_code, status)""",
)

CHECKSUM_MATERIAL = "\n-- statement --\n".join(SCHEMA_STATEMENTS) + "\n-- seeds --\n" + json.dumps(
    PREDICATE_ROWS,
    ensure_ascii=True,
    sort_keys=True,
    separators=(",", ":"),
)


def upgrade(connection: Connection) -> None:
    for statement in SCHEMA_STATEMENTS:
        connection.execute(text(statement))
    for row in PREDICATE_ROWS:
        connection.execute(
            text(
                "INSERT INTO assertion_predicate "
                "(key, vocabulary_version, subject_entity_type, object_entity_type, "
                "object_concept_kind, evidence_policy, created_at, updated_at) "
                "VALUES (:key, :vocabulary_version, :subject_entity_type, :object_entity_type, "
                ":object_concept_kind, :evidence_policy, :created_at, :updated_at)"
            ),
            {**row, "created_at": SEED_TIMESTAMP, "updated_at": SEED_TIMESTAMP},
        )


MIGRATION = Migration(
    version=8,
    name="analysis_persistence_schema",
    checksum_material=CHECKSUM_MATERIAL,
    upgrade=upgrade,
)
