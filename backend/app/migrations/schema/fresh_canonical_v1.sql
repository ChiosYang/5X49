CREATE TABLE assertion_predicate (
	"key" VARCHAR NOT NULL,
	vocabulary_version VARCHAR NOT NULL,
	subject_entity_type VARCHAR NOT NULL,
	object_entity_type VARCHAR NOT NULL,
	object_concept_kind VARCHAR,
	evidence_policy VARCHAR NOT NULL,
	created_at VARCHAR NOT NULL,
	updated_at VARCHAR NOT NULL,
	PRIMARY KEY ("key"),
	CONSTRAINT ck_assertion_predicate_subject_type CHECK (subject_entity_type IN ('film', 'person', 'concept')),
	CONSTRAINT ck_assertion_predicate_object_type CHECK (object_entity_type IN ('film', 'person', 'concept')),
	CONSTRAINT ck_assertion_predicate_concept_kind CHECK (object_concept_kind IS NULL OR object_concept_kind IN ('genre', 'theme', 'movement', 'visual_style', 'micro_genre')),
	CONSTRAINT ck_assertion_predicate_evidence_policy CHECK (evidence_policy IN ('provenance_only', 'preferred', 'optional'))
);

CREATE TABLE events (
	id VARCHAR NOT NULL,
	aggregate_type VARCHAR NOT NULL,
	aggregate_id VARCHAR,
	type VARCHAR NOT NULL,
	actor_type VARCHAR NOT NULL,
	actor_id VARCHAR,
	command_id VARCHAR,
	correlation_id VARCHAR,
	causation_id VARCHAR,
	payload JSON,
	context JSON,
	schema_version INTEGER NOT NULL,
	occurred_at VARCHAR NOT NULL,
	PRIMARY KEY (id)
);

CREATE TABLE evidence (
	id VARCHAR NOT NULL,
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
	PRIMARY KEY (id),
	CONSTRAINT uq_evidence_key UNIQUE (evidence_key),
	CONSTRAINT ck_evidence_type CHECK (evidence_type IN ('catalog', 'web', 'dataset')),
	CONSTRAINT ck_evidence_hashes CHECK (length(evidence_key) = 64 AND evidence_key NOT GLOB '*[^0-9a-f]*' AND length(content_hash) = 64 AND content_hash NOT GLOB '*[^0-9a-f]*'),
	CONSTRAINT ck_evidence_http_uri CHECK (length(source_uri) <= 2048 AND (lower(source_uri) LIKE 'http://%' OR lower(source_uri) LIKE 'https://%')),
	CONSTRAINT ck_evidence_bounded_text CHECK (length(trim(source_title)) > 0 AND length(source_title) <= 300 AND length(trim(claim)) > 0 AND length(claim) <= 400 AND (publisher IS NULL OR length(publisher) <= 160) AND length(trim(verification_policy_version)) > 0 AND length(verification_policy_version) <= 80)
);

CREATE TABLE graph_entity (
	id VARCHAR NOT NULL,
	entity_type VARCHAR NOT NULL,
	lifecycle_status VARCHAR NOT NULL,
	merged_into_id VARCHAR,
	created_at VARCHAR NOT NULL,
	updated_at VARCHAR NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT ck_graph_entity_type CHECK (entity_type IN ('film', 'person', 'concept')),
	CONSTRAINT ck_graph_entity_lifecycle CHECK (lifecycle_status IN ('active', 'merged', 'tombstoned')),
	FOREIGN KEY(merged_into_id) REFERENCES graph_entity (id) ON DELETE RESTRICT
);

CREATE TABLE job (
	id VARCHAR NOT NULL,
	type VARCHAR NOT NULL,
	status VARCHAR NOT NULL,
	payload JSON,
	progress JSON,
	result JSON,
	result_summary VARCHAR,
	error VARCHAR,
	attempts INTEGER NOT NULL,
	max_attempts INTEGER NOT NULL,
	priority INTEGER NOT NULL,
	dedupe_key VARCHAR,
	cancel_requested BOOLEAN NOT NULL,
	created_at VARCHAR NOT NULL,
	updated_at VARCHAR NOT NULL,
	started_at VARCHAR,
	finished_at VARCHAR,
	PRIMARY KEY (id)
);

CREATE TABLE local_profile (
	id VARCHAR NOT NULL,
	profile_key VARCHAR NOT NULL,
	display_name VARCHAR,
	created_at VARCHAR NOT NULL,
	updated_at VARCHAR NOT NULL,
	PRIMARY KEY (id)
);

CREATE TABLE schema_metadata (
	id INTEGER NOT NULL,
	epoch VARCHAR NOT NULL,
	created_at VARCHAR NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (epoch)
);

CREATE TABLE setting (
	"key" VARCHAR NOT NULL,
	value JSON NOT NULL,
	updated_at VARCHAR NOT NULL,
	PRIMARY KEY ("key")
);

CREATE TABLE assertion (
	id VARCHAR NOT NULL,
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
	PRIMARY KEY (id),
	CONSTRAINT uq_assertion_key UNIQUE (assertion_key),
	CONSTRAINT ck_assertion_not_self_referential CHECK (subject_entity_id <> object_entity_id),
	CONSTRAINT ck_assertion_hashes CHECK (length(qualifier_hash) = 64 AND qualifier_hash NOT GLOB '*[^0-9a-f]*' AND length(assertion_key) = 64 AND assertion_key NOT GLOB '*[^0-9a-f]*'),
	CONSTRAINT ck_assertion_source_scope CHECK (source_scope IN ('factual', 'curated', 'inferred')),
	CONSTRAINT ck_assertion_review_status CHECK (review_status IN ('proposed', 'accepted', 'rejected')),
	CONSTRAINT ck_assertion_review_method CHECK (review_method IN ('none', 'import_policy', 'user')),
	CONSTRAINT ck_assertion_confidence CHECK ((confidence IS NULL AND confidence_method IS NULL) OR (confidence IS NOT NULL AND confidence_method IS NOT NULL AND confidence >= 0 AND confidence <= 1 AND length(trim(confidence_method)) > 0)),
	CONSTRAINT ck_assertion_rationale CHECK (rationale IS NULL OR length(rationale) <= 600),
	CONSTRAINT ck_assertion_bounded_methods CHECK ((confidence_method IS NULL OR length(confidence_method) <= 80) AND (review_policy_version IS NULL OR length(review_policy_version) <= 80)),
	CONSTRAINT ck_assertion_review_decision CHECK ((review_status = 'proposed' AND review_method = 'none' AND reviewed_by_profile_id IS NULL AND reviewed_at IS NULL AND review_policy_version IS NULL) OR (review_status = 'accepted' AND review_method = 'import_policy' AND reviewed_by_profile_id IS NULL AND reviewed_at IS NOT NULL AND review_policy_version IS NOT NULL AND length(trim(review_policy_version)) > 0) OR (review_status IN ('accepted', 'rejected') AND review_method = 'user' AND reviewed_by_profile_id IS NOT NULL AND reviewed_at IS NOT NULL AND review_policy_version IS NULL)),
	FOREIGN KEY(subject_entity_id) REFERENCES graph_entity (id) ON DELETE RESTRICT,
	FOREIGN KEY(object_entity_id) REFERENCES graph_entity (id) ON DELETE RESTRICT,
	FOREIGN KEY(predicate) REFERENCES assertion_predicate ("key") ON DELETE RESTRICT,
	FOREIGN KEY(reviewed_by_profile_id) REFERENCES local_profile (id) ON DELETE RESTRICT
);

CREATE TABLE concept (
	id VARCHAR NOT NULL,
	kind VARCHAR NOT NULL,
	canonical_key VARCHAR NOT NULL,
	canonical_name VARCHAR NOT NULL,
	description VARCHAR,
	lifecycle_status VARCHAR NOT NULL,
	merged_into_id VARCHAR,
	created_at VARCHAR NOT NULL,
	updated_at VARCHAR NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_concept_kind_key UNIQUE (kind, canonical_key),
	CONSTRAINT ck_concept_kind CHECK (kind IN ('genre', 'theme', 'movement', 'visual_style', 'micro_genre')),
	CONSTRAINT ck_concept_lifecycle CHECK (lifecycle_status IN ('active', 'merged', 'tombstoned')),
	FOREIGN KEY(id) REFERENCES graph_entity (id) ON DELETE RESTRICT,
	FOREIGN KEY(merged_into_id) REFERENCES concept (id) ON DELETE RESTRICT
);

CREATE TABLE external_identity (
	id VARCHAR NOT NULL,
	entity_id VARCHAR NOT NULL,
	provider VARCHAR NOT NULL,
	external_id VARCHAR NOT NULL,
	identity_status VARCHAR NOT NULL,
	verified_at VARCHAR,
	provenance_kind VARCHAR NOT NULL,
	provenance_ref VARCHAR,
	created_at VARCHAR NOT NULL,
	updated_at VARCHAR NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_external_identity_provider_id UNIQUE (provider, external_id),
	CONSTRAINT ck_external_identity_status CHECK (identity_status IN ('active', 'deprecated', 'disputed')),
	FOREIGN KEY(entity_id) REFERENCES graph_entity (id) ON DELETE RESTRICT
);

CREATE TABLE film (
	id VARCHAR NOT NULL,
	canonical_title VARCHAR NOT NULL,
	original_title VARCHAR,
	release_date VARCHAR,
	release_year INTEGER,
	runtime_minutes INTEGER,
	overview VARCHAR,
	lifecycle_status VARCHAR NOT NULL,
	merged_into_id VARCHAR,
	created_at VARCHAR NOT NULL,
	updated_at VARCHAR NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT ck_film_lifecycle CHECK (lifecycle_status IN ('active', 'merged', 'tombstoned')),
	FOREIGN KEY(id) REFERENCES graph_entity (id) ON DELETE RESTRICT,
	FOREIGN KEY(merged_into_id) REFERENCES film (id) ON DELETE RESTRICT
);

CREATE TABLE operation_snapshot (
	id VARCHAR NOT NULL,
	event_id VARCHAR NOT NULL,
	aggregate_type VARCHAR NOT NULL,
	aggregate_id VARCHAR NOT NULL,
	operation_kind VARCHAR NOT NULL,
	before_state JSON NOT NULL,
	after_state JSON NOT NULL,
	optimistic_hash VARCHAR NOT NULL,
	backup_manifest_ref VARCHAR,
	status VARCHAR NOT NULL,
	created_at VARCHAR NOT NULL,
	restored_at VARCHAR,
	PRIMARY KEY (id),
	CONSTRAINT ck_operation_snapshot_aggregate_type CHECK (aggregate_type IN ('film', 'library_item')),
	CONSTRAINT ck_operation_snapshot_status CHECK (status IN ('available', 'restored', 'expired')),
	CONSTRAINT uq_operation_snapshot_event UNIQUE (event_id),
	FOREIGN KEY(event_id) REFERENCES events (id) ON DELETE RESTRICT
);

CREATE TABLE person (
	id VARCHAR NOT NULL,
	canonical_name VARCHAR NOT NULL,
	normalized_name VARCHAR NOT NULL,
	sort_name VARCHAR,
	resolution_status VARCHAR NOT NULL,
	lifecycle_status VARCHAR NOT NULL,
	merged_into_id VARCHAR,
	created_at VARCHAR NOT NULL,
	updated_at VARCHAR NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT ck_person_resolution CHECK (resolution_status IN ('provisional', 'verified', 'review_required')),
	CONSTRAINT ck_person_lifecycle CHECK (lifecycle_status IN ('active', 'merged', 'tombstoned')),
	FOREIGN KEY(id) REFERENCES graph_entity (id) ON DELETE RESTRICT,
	FOREIGN KEY(merged_into_id) REFERENCES person (id) ON DELETE RESTRICT
);

CREATE TABLE analysis_run (
	id VARCHAR NOT NULL,
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
	PRIMARY KEY (id),
	CONSTRAINT uq_analysis_run_idempotency_key UNIQUE (idempotency_key),
	CONSTRAINT ck_analysis_run_kind CHECK (analysis_kind IN ('genealogy_v2')),
	CONSTRAINT ck_analysis_run_status CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')),
	CONSTRAINT ck_analysis_run_required_text CHECK (length(trim(analysis_kind)) > 0 AND length(trim(provider)) > 0 AND length(trim(model)) > 0 AND length(trim(prompt_version)) > 0 AND length(trim(schema_version)) > 0 AND length(trim(resolver_version)) > 0 AND length(trim(policy_version)) > 0 AND length(trim(app_version)) > 0 AND length(analysis_kind) <= 80 AND length(provider) <= 80 AND length(model) <= 160 AND length(prompt_version) <= 80 AND length(schema_version) <= 80 AND length(resolver_version) <= 80 AND length(policy_version) <= 80 AND length(app_version) <= 80),
	CONSTRAINT ck_analysis_run_hashes CHECK (length(input_hash) = 64 AND input_hash NOT GLOB '*[^0-9a-f]*' AND (output_hash IS NULL OR (length(output_hash) = 64 AND output_hash NOT GLOB '*[^0-9a-f]*')) AND length(idempotency_key) = 64 AND idempotency_key NOT GLOB '*[^0-9a-f]*'),
	CONSTRAINT ck_analysis_run_input_tokens CHECK (input_tokens IS NULL OR input_tokens >= 0),
	CONSTRAINT ck_analysis_run_output_tokens CHECK (output_tokens IS NULL OR output_tokens >= 0),
	CONSTRAINT ck_analysis_run_cost_currency CHECK ((estimated_cost IS NULL AND currency IS NULL) OR (estimated_cost IS NOT NULL AND currency IS NOT NULL AND estimated_cost >= 0 AND length(currency) = 3 AND currency = upper(currency) AND currency GLOB '[A-Z][A-Z][A-Z]')),
	CONSTRAINT ck_analysis_run_summary CHECK (result_summary IS NULL OR length(result_summary) <= 1200),
	CONSTRAINT ck_analysis_run_error_message CHECK (error_message IS NULL OR length(error_message) <= 500),
	CONSTRAINT ck_analysis_run_bounded_diagnostics CHECK ((error_category IS NULL OR length(error_category) <= 80) AND (error_code IS NULL OR length(error_code) <= 80) AND (correlation_id IS NULL OR length(correlation_id) <= 160) AND (job_id IS NULL OR length(job_id) <= 160)),
	CONSTRAINT ck_analysis_run_lifecycle CHECK ((status = 'queued' AND attempt_count = 0 AND started_at IS NULL AND finished_at IS NULL AND output_hash IS NULL AND result_summary IS NULL) OR (status = 'running' AND attempt_count >= 1 AND started_at IS NOT NULL AND finished_at IS NULL) OR (status = 'succeeded' AND attempt_count >= 1 AND started_at IS NOT NULL AND finished_at IS NOT NULL AND output_hash IS NOT NULL AND result_summary IS NOT NULL AND length(trim(result_summary)) > 0) OR (status IN ('failed', 'cancelled') AND attempt_count >= 1 AND started_at IS NOT NULL AND finished_at IS NOT NULL)),
	FOREIGN KEY(film_id) REFERENCES film (id) ON DELETE RESTRICT
);

CREATE TABLE assertion_evidence (
	id VARCHAR NOT NULL,
	assertion_id VARCHAR NOT NULL,
	evidence_id VARCHAR NOT NULL,
	stance VARCHAR NOT NULL,
	link_status VARCHAR NOT NULL,
	created_at VARCHAR NOT NULL,
	revoked_at VARCHAR,
	PRIMARY KEY (id),
	CONSTRAINT uq_assertion_evidence_stance UNIQUE (assertion_id, evidence_id, stance),
	CONSTRAINT ck_assertion_evidence_stance CHECK (stance IN ('supports', 'contradicts', 'context')),
	CONSTRAINT ck_assertion_evidence_status CHECK (link_status IN ('active', 'revoked')),
	CONSTRAINT ck_assertion_evidence_revocation CHECK ((link_status = 'active' AND revoked_at IS NULL) OR (link_status = 'revoked' AND revoked_at IS NOT NULL)),
	FOREIGN KEY(assertion_id) REFERENCES assertion (id) ON DELETE RESTRICT,
	FOREIGN KEY(evidence_id) REFERENCES evidence (id) ON DELETE RESTRICT
);

CREATE TABLE concept_alias (
	id VARCHAR NOT NULL,
	concept_id VARCHAR NOT NULL,
	locale VARCHAR NOT NULL,
	alias VARCHAR NOT NULL,
	normalized_alias VARCHAR NOT NULL,
	provenance_ref VARCHAR NOT NULL,
	created_at VARCHAR NOT NULL,
	updated_at VARCHAR NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_concept_alias_value UNIQUE (concept_id, locale, normalized_alias),
	FOREIGN KEY(concept_id) REFERENCES concept (id) ON DELETE RESTRICT
);

CREATE TABLE credit (
	id VARCHAR NOT NULL,
	film_id VARCHAR NOT NULL,
	person_id VARCHAR NOT NULL,
	department VARCHAR NOT NULL,
	job VARCHAR NOT NULL,
	character VARCHAR NOT NULL,
	billing_order INTEGER,
	semantic_key VARCHAR NOT NULL,
	created_at VARCHAR NOT NULL,
	updated_at VARCHAR NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_credit_semantic_key UNIQUE (semantic_key),
	CONSTRAINT ck_credit_billing_order CHECK (billing_order IS NULL OR billing_order >= 0),
	CONSTRAINT ck_credit_department CHECK (length(trim(department)) > 0),
	CONSTRAINT ck_credit_job CHECK (length(trim(job)) > 0),
	FOREIGN KEY(film_id) REFERENCES film (id) ON DELETE RESTRICT,
	FOREIGN KEY(person_id) REFERENCES person (id) ON DELETE RESTRICT
);

CREATE TABLE external_score_refresh_state (
	id VARCHAR NOT NULL,
	film_id VARCHAR NOT NULL,
	source VARCHAR NOT NULL,
	status VARCHAR NOT NULL,
	error_code VARCHAR,
	error_message VARCHAR,
	refreshed_at VARCHAR,
	created_at VARCHAR NOT NULL,
	updated_at VARCHAR NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_external_score_refresh_film_source UNIQUE (film_id, source),
	CONSTRAINT ck_external_score_refresh_status CHECK (status IN ('idle', 'running', 'succeeded', 'failed')),
	FOREIGN KEY(film_id) REFERENCES film (id) ON DELETE RESTRICT
);

CREATE TABLE film_country (
	id VARCHAR NOT NULL,
	film_id VARCHAR NOT NULL,
	iso_3166_1 VARCHAR NOT NULL,
	created_at VARCHAR NOT NULL,
	updated_at VARCHAR NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_film_country_code UNIQUE (film_id, iso_3166_1),
	CONSTRAINT ck_film_country_iso_3166_1 CHECK (length(iso_3166_1) = 2 AND iso_3166_1 = upper(iso_3166_1) AND iso_3166_1 GLOB '[A-Z][A-Z]'),
	FOREIGN KEY(film_id) REFERENCES film (id) ON DELETE RESTRICT
);

CREATE TABLE film_external_score (
	id VARCHAR NOT NULL,
	film_id VARCHAR NOT NULL,
	source VARCHAR NOT NULL,
	label VARCHAR NOT NULL,
	kind VARCHAR NOT NULL,
	value FLOAT,
	scale FLOAT,
	rank INTEGER,
	previous_rank INTEGER,
	votes INTEGER,
	list_name VARCHAR NOT NULL,
	edition VARCHAR NOT NULL,
	source_uri VARCHAR,
	matched_by VARCHAR,
	confidence FLOAT,
	fetched_at VARCHAR NOT NULL,
	expires_at VARCHAR,
	created_at VARCHAR NOT NULL,
	updated_at VARCHAR NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_film_external_score_identity UNIQUE (film_id, source, kind, list_name, edition),
	CONSTRAINT ck_film_external_score_kind CHECK (kind IN ('rating', 'rank')),
	CONSTRAINT ck_film_external_score_value CHECK ((kind = 'rating' AND value IS NOT NULL AND scale IS NOT NULL AND rank IS NULL) OR (kind = 'rank' AND rank IS NOT NULL AND value IS NULL AND scale IS NULL)),
	FOREIGN KEY(film_id) REFERENCES film (id) ON DELETE RESTRICT
);

CREATE TABLE film_profile_state (
	profile_id VARCHAR NOT NULL,
	film_id VARCHAR NOT NULL,
	favorite BOOLEAN NOT NULL,
	rating INTEGER,
	notes VARCHAR,
	created_at VARCHAR NOT NULL,
	updated_at VARCHAR NOT NULL,
	PRIMARY KEY (profile_id, film_id),
	CONSTRAINT ck_film_profile_rating CHECK (rating IS NULL OR (rating >= 1 AND rating <= 5)),
	FOREIGN KEY(profile_id) REFERENCES local_profile (id) ON DELETE RESTRICT,
	FOREIGN KEY(film_id) REFERENCES film (id) ON DELETE RESTRICT
);

CREATE TABLE film_title (
	id VARCHAR NOT NULL,
	film_id VARCHAR NOT NULL,
	locale VARCHAR NOT NULL,
	title_type VARCHAR NOT NULL,
	title VARCHAR NOT NULL,
	normalized_title VARCHAR NOT NULL,
	origin_kind VARCHAR NOT NULL,
	origin_ref VARCHAR NOT NULL,
	observed_at VARCHAR NOT NULL,
	superseded_at VARCHAR,
	PRIMARY KEY (id),
	CONSTRAINT uq_film_title_source_value UNIQUE (film_id, locale, title_type, normalized_title, origin_kind, origin_ref),
	CONSTRAINT ck_film_title_type CHECK (title_type IN ('canonical', 'original', 'localized', 'alternative')),
	FOREIGN KEY(film_id) REFERENCES film (id) ON DELETE RESTRICT
);

CREATE TABLE library_item (
	id VARCHAR NOT NULL,
	profile_id VARCHAR NOT NULL,
	film_id VARCHAR NOT NULL,
	source_type VARCHAR NOT NULL,
	source_instance_id VARCHAR NOT NULL,
	source_item_key VARCHAR NOT NULL,
	display_name VARCHAR,
	availability_status VARCHAR NOT NULL,
	resolution_status VARCHAR NOT NULL,
	added_at VARCHAR,
	last_seen_at VARCHAR,
	missing_since VARCHAR,
	retired_at VARCHAR,
	metadata_source VARCHAR,
	metadata_updated_at VARCHAR,
	scrape_status VARCHAR NOT NULL,
	scrape_error VARCHAR,
	scraped_at VARCHAR,
	match_confidence FLOAT,
	created_at VARCHAR NOT NULL,
	updated_at VARCHAR NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT ck_library_item_availability CHECK (availability_status IN ('available', 'missing', 'ignored', 'retired')),
	CONSTRAINT ck_library_item_resolution CHECK (resolution_status IN ('unresolved', 'matched', 'review_required', 'failed')),
	FOREIGN KEY(profile_id) REFERENCES local_profile (id) ON DELETE RESTRICT,
	FOREIGN KEY(film_id) REFERENCES film (id) ON DELETE RESTRICT
);

CREATE TABLE viewing (
	id VARCHAR NOT NULL,
	profile_id VARCHAR NOT NULL,
	film_id VARCHAR NOT NULL,
	watched_at VARCHAR,
	watched_at_precision VARCHAR NOT NULL,
	source VARCHAR NOT NULL,
	source_record_id VARCHAR,
	review_status VARCHAR NOT NULL,
	created_at VARCHAR NOT NULL,
	updated_at VARCHAR NOT NULL,
	deleted_at VARCHAR,
	PRIMARY KEY (id),
	CONSTRAINT ck_viewing_precision CHECK (watched_at_precision IN ('timestamp', 'date', 'year', 'unknown')),
	CONSTRAINT ck_viewing_review_status CHECK (review_status IN ('confirmed', 'needs_review', 'rejected')),
	CONSTRAINT uq_viewing_source_record UNIQUE (profile_id, source, source_record_id),
	FOREIGN KEY(profile_id) REFERENCES local_profile (id) ON DELETE RESTRICT,
	FOREIGN KEY(film_id) REFERENCES film (id) ON DELETE RESTRICT
);

CREATE TABLE analysis_resolution_review (
	id VARCHAR NOT NULL,
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
	PRIMARY KEY (id),
	CONSTRAINT uq_analysis_resolution_review_key UNIQUE (review_key),
	CONSTRAINT ck_analysis_resolution_review_candidate_kind CHECK (candidate_kind IN ('entity_reference', 'evidence', 'assertion', 'output')),
	CONSTRAINT ck_analysis_resolution_review_reason CHECK (reason_code IN ('unresolved_reference', 'ambiguous_reference', 'identity_conflict', 'predicate_type_mismatch', 'evidence_uri_blocked', 'evidence_retrieval_failed', 'evidence_policy_rejected', 'invalid_candidate')),
	CONSTRAINT ck_analysis_resolution_review_status CHECK (status IN ('open', 'resolved', 'dismissed')),
	CONSTRAINT ck_analysis_resolution_review_candidate_size CHECK (length(CAST(candidate_summary AS TEXT)) <= 4096),
	CONSTRAINT ck_analysis_resolution_review_hashes CHECK (length(candidate_hash) = 64 AND candidate_hash NOT GLOB '*[^0-9a-f]*' AND length(review_key) = 64 AND review_key NOT GLOB '*[^0-9a-f]*'),
	CONSTRAINT ck_analysis_resolution_review_lifecycle CHECK ((status = 'open' AND resolved_at IS NULL AND resolved_entity_id IS NULL) OR (status IN ('resolved', 'dismissed') AND resolved_at IS NOT NULL)),
	FOREIGN KEY(analysis_run_id) REFERENCES analysis_run (id) ON DELETE RESTRICT,
	FOREIGN KEY(film_id) REFERENCES film (id) ON DELETE RESTRICT,
	FOREIGN KEY(predicate) REFERENCES assertion_predicate ("key") ON DELETE RESTRICT,
	FOREIGN KEY(resolved_entity_id) REFERENCES graph_entity (id) ON DELETE RESTRICT
);

CREATE TABLE assertion_provenance (
	id VARCHAR NOT NULL,
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
	PRIMARY KEY (id),
	CONSTRAINT uq_assertion_provenance_origin UNIQUE (assertion_id, origin_kind, origin_ref),
	CONSTRAINT ck_assertion_provenance_origin_kind CHECK (origin_kind IN ('nfo', 'tmdb', 'user', 'analysis_run', 'rule')),
	CONSTRAINT ck_assertion_provenance_origin_scope CHECK (origin_scope IN ('factual', 'curated', 'inferred')),
	CONSTRAINT ck_assertion_provenance_analysis_run CHECK ((origin_kind = 'analysis_run' AND analysis_run_id IS NOT NULL) OR (origin_kind <> 'analysis_run' AND analysis_run_id IS NULL)),
	CONSTRAINT ck_assertion_provenance_payload_hash CHECK (source_payload_hash IS NULL OR (length(source_payload_hash) = 64 AND source_payload_hash NOT GLOB '*[^0-9a-f]*')),
	CONSTRAINT ck_assertion_provenance_origin_ref CHECK (length(trim(origin_ref)) > 0 AND length(origin_ref) <= 300 AND (source_field IS NULL OR length(source_field) <= 80)),
	FOREIGN KEY(assertion_id) REFERENCES assertion (id) ON DELETE RESTRICT,
	FOREIGN KEY(analysis_run_id) REFERENCES analysis_run (id) ON DELETE RESTRICT
);

CREATE TABLE credit_provenance (
	id VARCHAR NOT NULL,
	credit_id VARCHAR NOT NULL,
	origin_kind VARCHAR NOT NULL,
	origin_ref VARCHAR NOT NULL,
	observed_at VARCHAR NOT NULL,
	superseded_at VARCHAR,
	PRIMARY KEY (id),
	CONSTRAINT uq_credit_provenance_origin UNIQUE (credit_id, origin_kind, origin_ref),
	FOREIGN KEY(credit_id) REFERENCES credit (id) ON DELETE RESTRICT
);

CREATE TABLE film_country_provenance (
	id VARCHAR NOT NULL,
	film_country_id VARCHAR NOT NULL,
	origin_kind VARCHAR NOT NULL,
	origin_ref VARCHAR NOT NULL,
	observed_at VARCHAR NOT NULL,
	superseded_at VARCHAR,
	PRIMARY KEY (id),
	CONSTRAINT uq_film_country_provenance_origin UNIQUE (film_country_id, origin_kind, origin_ref),
	FOREIGN KEY(film_country_id) REFERENCES film_country (id) ON DELETE RESTRICT
);

CREATE TABLE identity_review (
	id VARCHAR NOT NULL,
	film_id VARCHAR,
	library_item_id VARCHAR,
	source_instance_id VARCHAR NOT NULL,
	source_ref VARCHAR NOT NULL,
	reason_code VARCHAR NOT NULL,
	candidate_hash VARCHAR NOT NULL,
	review_key VARCHAR NOT NULL,
	status VARCHAR NOT NULL,
	created_at VARCHAR NOT NULL,
	updated_at VARCHAR NOT NULL,
	resolved_at VARCHAR,
	PRIMARY KEY (id),
	CONSTRAINT uq_identity_review_key UNIQUE (review_key),
	CONSTRAINT ck_identity_review_status CHECK (status IN ('open', 'resolved', 'dismissed')),
	FOREIGN KEY(film_id) REFERENCES film (id) ON DELETE RESTRICT,
	FOREIGN KEY(library_item_id) REFERENCES library_item (id) ON DELETE RESTRICT
);

CREATE TABLE library_item_locator_history (
	id VARCHAR NOT NULL,
	library_item_id VARCHAR NOT NULL,
	source_instance_id VARCHAR NOT NULL,
	source_item_key VARCHAR NOT NULL,
	observed_from VARCHAR NOT NULL,
	observed_to VARCHAR,
	reason VARCHAR NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_library_item_locator_history UNIQUE (library_item_id, source_instance_id, source_item_key),
	FOREIGN KEY(library_item_id) REFERENCES library_item (id) ON DELETE RESTRICT
);

CREATE TABLE media_asset (
	id VARCHAR NOT NULL,
	library_item_id VARCHAR,
	film_id VARCHAR,
	asset_kind VARCHAR NOT NULL,
	locator_kind VARCHAR NOT NULL,
	locator VARCHAR NOT NULL,
	normalized_locator_hash VARCHAR NOT NULL,
	availability_status VARCHAR NOT NULL,
	file_size INTEGER,
	file_mtime FLOAT,
	platform_file_id VARCHAR,
	content_fingerprint VARCHAR,
	content_hash VARCHAR,
	width INTEGER,
	height INTEGER,
	codec VARCHAR,
	bitrate INTEGER,
	duration_seconds FLOAT,
	fps FLOAT,
	dynamic_range VARCHAR,
	bit_depth INTEGER,
	stream_metadata JSON,
	source VARCHAR NOT NULL,
	last_observed_at VARCHAR,
	missing_since VARCHAR,
	created_at VARCHAR NOT NULL,
	updated_at VARCHAR NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT ck_media_asset_owner_xor CHECK (((library_item_id IS NULL) <> (film_id IS NULL))),
	CONSTRAINT ck_media_asset_availability CHECK (availability_status IN ('present', 'missing', 'unknown', 'retired')),
	FOREIGN KEY(library_item_id) REFERENCES library_item (id) ON DELETE RESTRICT,
	FOREIGN KEY(film_id) REFERENCES film (id) ON DELETE RESTRICT
);

CREATE TABLE structured_metadata_review (
	id VARCHAR NOT NULL,
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
	PRIMARY KEY (id),
	CONSTRAINT uq_structured_metadata_review_key UNIQUE (review_key),
	CONSTRAINT ck_structured_metadata_review_field CHECK (field_kind IN ('title', 'country', 'person', 'credit', 'concept')),
	CONSTRAINT ck_structured_metadata_review_status CHECK (status IN ('open', 'resolved', 'dismissed')),
	FOREIGN KEY(film_id) REFERENCES film (id) ON DELETE RESTRICT,
	FOREIGN KEY(library_item_id) REFERENCES library_item (id) ON DELETE RESTRICT
);

CREATE INDEX ix_analysis_resolution_review_analysis_run_id ON analysis_resolution_review (analysis_run_id);

CREATE INDEX ix_analysis_resolution_review_film_id ON analysis_resolution_review (film_id);

CREATE INDEX ix_analysis_resolution_review_film_status ON analysis_resolution_review (film_id, status);

CREATE INDEX ix_analysis_resolution_review_reason_status ON analysis_resolution_review (reason_code, status);

CREATE INDEX ix_analysis_resolution_review_run_status ON analysis_resolution_review (analysis_run_id, status);

CREATE INDEX ix_analysis_run_correlation_id ON analysis_run (correlation_id);

CREATE INDEX ix_analysis_run_film_id ON analysis_run (film_id);

CREATE INDEX ix_analysis_run_film_kind_status_created ON analysis_run (film_id, analysis_kind, status, created_at);

CREATE INDEX ix_analysis_run_job_id ON analysis_run (job_id);

CREATE INDEX ix_assertion_object_entity_id ON assertion (object_entity_id);

CREATE INDEX ix_assertion_object_predicate_review ON assertion (object_entity_id, predicate, review_status);

CREATE INDEX ix_assertion_scope_review ON assertion (source_scope, review_status);

CREATE INDEX ix_assertion_subject_entity_id ON assertion (subject_entity_id);

CREATE INDEX ix_assertion_subject_predicate_review ON assertion (subject_entity_id, predicate, review_status);

CREATE INDEX ix_assertion_evidence_assertion_id ON assertion_evidence (assertion_id);

CREATE INDEX ix_assertion_evidence_evidence_id ON assertion_evidence (evidence_id);

CREATE INDEX ix_assertion_predicate_vocabulary ON assertion_predicate (vocabulary_version);

CREATE INDEX ix_assertion_provenance_analysis_run_id ON assertion_provenance (analysis_run_id);

CREATE INDEX ix_assertion_provenance_assertion_active ON assertion_provenance (assertion_id, superseded_at);

CREATE INDEX ix_assertion_provenance_assertion_id ON assertion_provenance (assertion_id);

CREATE INDEX ix_assertion_provenance_origin_ref ON assertion_provenance (origin_ref);

CREATE INDEX ix_concept_kind_name ON concept (kind, canonical_name);

CREATE INDEX ix_concept_lifecycle_status ON concept (lifecycle_status);

CREATE INDEX ix_concept_merged_into_id ON concept (merged_into_id);

CREATE INDEX ix_concept_alias_concept_id ON concept_alias (concept_id);

CREATE INDEX ix_concept_alias_locale_value ON concept_alias (locale, normalized_alias);

CREATE INDEX ix_credit_film_department ON credit (film_id, department);

CREATE INDEX ix_credit_film_id ON credit (film_id);

CREATE INDEX ix_credit_person_id ON credit (person_id);

CREATE INDEX ix_credit_person_job ON credit (person_id, job);

CREATE INDEX ix_credit_provenance_credit_id ON credit_provenance (credit_id);

CREATE INDEX ix_credit_provenance_origin_active ON credit_provenance (origin_kind, origin_ref, superseded_at);

CREATE INDEX ix_events_actor_type ON events (actor_type);

CREATE INDEX ix_events_aggregate_id ON events (aggregate_id);

CREATE INDEX ix_events_aggregate_type ON events (aggregate_type);

CREATE INDEX ix_events_causation_id ON events (causation_id);

CREATE INDEX ix_events_command_id ON events (command_id);

CREATE INDEX ix_events_correlation_id ON events (correlation_id);

CREATE INDEX ix_events_occurred_at ON events (occurred_at);

CREATE INDEX ix_events_type ON events (type);

CREATE INDEX ix_evidence_content_hash ON evidence (content_hash);

CREATE INDEX ix_evidence_source_uri ON evidence (source_uri);

CREATE INDEX ix_external_identity_entity_id ON external_identity (entity_id);

CREATE INDEX ix_external_identity_entity_provider ON external_identity (entity_id, provider);

CREATE INDEX ix_external_identity_identity_status ON external_identity (identity_status);

CREATE INDEX ix_external_identity_provider_status ON external_identity (provider, identity_status);

CREATE INDEX ix_external_score_refresh_state_film_id ON external_score_refresh_state (film_id);

CREATE INDEX ix_external_score_refresh_state_status ON external_score_refresh_state (status);

CREATE INDEX ix_film_canonical_title ON film (canonical_title);

CREATE INDEX ix_film_lifecycle_status ON film (lifecycle_status);

CREATE INDEX ix_film_merged_into_id ON film (merged_into_id);

CREATE INDEX ix_film_release_title ON film (release_year, canonical_title);

CREATE INDEX ix_film_release_year ON film (release_year);

CREATE INDEX ix_film_country_code ON film_country (iso_3166_1);

CREATE INDEX ix_film_country_film_id ON film_country (film_id);

CREATE INDEX ix_film_country_provenance_film_country_id ON film_country_provenance (film_country_id);

CREATE INDEX ix_film_country_provenance_origin_active ON film_country_provenance (origin_kind, origin_ref, superseded_at);

CREATE INDEX ix_film_external_score_film_id ON film_external_score (film_id);

CREATE INDEX ix_film_external_score_film_source ON film_external_score (film_id, source);

CREATE INDEX ix_film_profile_state_favorite ON film_profile_state (favorite);

CREATE INDEX ix_film_title_film_active ON film_title (film_id, superseded_at);

CREATE INDEX ix_film_title_film_id ON film_title (film_id);

CREATE INDEX ix_film_title_search ON film_title (normalized_title, locale);

CREATE INDEX ix_graph_entity_entity_type ON graph_entity (entity_type);

CREATE INDEX ix_graph_entity_lifecycle_status ON graph_entity (lifecycle_status);

CREATE INDEX ix_identity_review_film_status ON identity_review (film_id, status);

CREATE INDEX ix_identity_review_item_status ON identity_review (library_item_id, status);

CREATE INDEX ix_identity_review_status ON identity_review (status);

CREATE INDEX ix_job_cancel_requested ON job (cancel_requested);

CREATE INDEX ix_job_created_at ON job (created_at);

CREATE INDEX ix_job_dedupe_key ON job (dedupe_key);

CREATE INDEX ix_job_priority ON job (priority);

CREATE INDEX ix_job_status ON job (status);

CREATE INDEX ix_job_type ON job (type);

CREATE INDEX ix_library_item_availability_status ON library_item (availability_status);

CREATE INDEX ix_library_item_film_id ON library_item (film_id);

CREATE INDEX ix_library_item_profile_availability_added ON library_item (profile_id, availability_status, added_at);

CREATE INDEX ix_library_item_profile_id ON library_item (profile_id);

CREATE INDEX ix_library_item_resolution_status ON library_item (resolution_status);

CREATE INDEX ix_library_item_source_resolution ON library_item (source_instance_id, resolution_status);

CREATE UNIQUE INDEX uq_library_item_active_source ON library_item (source_instance_id, source_item_key) WHERE availability_status <> 'retired';

CREATE INDEX ix_library_item_locator_history_library_item_id ON library_item_locator_history (library_item_id);

CREATE UNIQUE INDEX ix_local_profile_profile_key ON local_profile (profile_key);

CREATE INDEX ix_media_asset_content_fingerprint ON media_asset (content_fingerprint);

CREATE INDEX ix_media_asset_content_hash ON media_asset (content_hash);

CREATE INDEX ix_media_asset_library_kind_availability ON media_asset (library_item_id, asset_kind, availability_status);

CREATE INDEX ix_media_asset_platform_file_id ON media_asset (platform_file_id);

CREATE UNIQUE INDEX uq_media_asset_film_owner_locator ON media_asset (film_id, asset_kind, normalized_locator_hash) WHERE film_id IS NOT NULL;

CREATE UNIQUE INDEX uq_media_asset_library_owner_locator ON media_asset (library_item_id, asset_kind, normalized_locator_hash) WHERE library_item_id IS NOT NULL;

CREATE INDEX ix_operation_snapshot_aggregate ON operation_snapshot (aggregate_type, aggregate_id, created_at);

CREATE INDEX ix_operation_snapshot_event_id ON operation_snapshot (event_id);

CREATE INDEX ix_operation_snapshot_status ON operation_snapshot (status);

CREATE INDEX ix_person_lifecycle_status ON person (lifecycle_status);

CREATE INDEX ix_person_merged_into_id ON person (merged_into_id);

CREATE INDEX ix_person_normalized_name ON person (normalized_name);

CREATE INDEX ix_person_resolution_status ON person (resolution_status);

CREATE INDEX ix_setting_updated_at ON setting (updated_at);

CREATE INDEX ix_structured_metadata_review_field_status ON structured_metadata_review (field_kind, status);

CREATE INDEX ix_structured_metadata_review_film_id ON structured_metadata_review (film_id);

CREATE INDEX ix_structured_metadata_review_film_status ON structured_metadata_review (film_id, status);

CREATE INDEX ix_structured_metadata_review_library_item_id ON structured_metadata_review (library_item_id);

CREATE INDEX ix_structured_metadata_review_status ON structured_metadata_review (status);

CREATE INDEX ix_viewing_deleted_at ON viewing (deleted_at);

CREATE INDEX ix_viewing_film_id ON viewing (film_id);

CREATE INDEX ix_viewing_profile_film_watched_at ON viewing (profile_id, film_id, watched_at);

CREATE INDEX ix_viewing_profile_id ON viewing (profile_id);

CREATE INDEX ix_viewing_profile_watched_at ON viewing (profile_id, watched_at);

CREATE INDEX ix_viewing_review_status ON viewing (review_status);
