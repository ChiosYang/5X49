CREATE TABLE workflow_run (
	id VARCHAR NOT NULL,
	type VARCHAR NOT NULL,
	definition_version VARCHAR NOT NULL,
	subject_type VARCHAR NOT NULL,
	subject_id VARCHAR,
	input_hash VARCHAR NOT NULL,
	dedupe_key VARCHAR,
	status VARCHAR NOT NULL,
	current_step_key VARCHAR,
	cancel_requested BOOLEAN NOT NULL,
	error_code VARCHAR,
	error_message VARCHAR,
	created_at VARCHAR NOT NULL,
	updated_at VARCHAR NOT NULL,
	started_at VARCHAR,
	finished_at VARCHAR,
	PRIMARY KEY (id),
	CONSTRAINT ck_workflow_run_status CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')),
	CONSTRAINT ck_workflow_run_subject_type CHECK (subject_type IN ('library', 'film', 'library_item', 'system')),
	CONSTRAINT ck_workflow_run_input_hash CHECK (length(input_hash) = 64 AND input_hash NOT GLOB '*[^0-9a-f]*')
);

CREATE INDEX ix_workflow_run_cancel_requested ON workflow_run (cancel_requested);

CREATE INDEX ix_workflow_run_created_at ON workflow_run (created_at);

CREATE INDEX ix_workflow_run_dedupe_key ON workflow_run (dedupe_key);

CREATE INDEX ix_workflow_run_dedupe_status ON workflow_run (dedupe_key, status);

CREATE INDEX ix_workflow_run_status ON workflow_run (status);

CREATE INDEX ix_workflow_run_status_created ON workflow_run (status, created_at);

CREATE INDEX ix_workflow_run_subject_id ON workflow_run (subject_id);

CREATE INDEX ix_workflow_run_subject_type ON workflow_run (subject_type);

CREATE INDEX ix_workflow_run_type ON workflow_run (type);

CREATE TABLE workflow_step (
	id VARCHAR NOT NULL,
	workflow_run_id VARCHAR NOT NULL,
	step_key VARCHAR NOT NULL,
	position INTEGER NOT NULL,
	status VARCHAR NOT NULL,
	attempt INTEGER NOT NULL,
	max_attempts INTEGER NOT NULL,
	retry_policy JSON NOT NULL,
	input_hash VARCHAR NOT NULL,
	output_hash VARCHAR,
	result_summary VARCHAR,
	compensation_status VARCHAR NOT NULL,
	lease_expires_at VARCHAR,
	created_at VARCHAR NOT NULL,
	updated_at VARCHAR NOT NULL,
	started_at VARCHAR,
	finished_at VARCHAR,
	PRIMARY KEY (id),
	CONSTRAINT uq_workflow_step_key UNIQUE (workflow_run_id, step_key),
	CONSTRAINT uq_workflow_step_position UNIQUE (workflow_run_id, position),
	CONSTRAINT ck_workflow_step_status CHECK (status IN ('pending', 'queued', 'running', 'succeeded', 'failed', 'cancelled')),
	CONSTRAINT ck_workflow_step_counts CHECK (position >= 0 AND attempt >= 0 AND max_attempts >= 1),
	CONSTRAINT ck_workflow_step_hashes CHECK (length(input_hash) = 64 AND input_hash NOT GLOB '*[^0-9a-f]*' AND (output_hash IS NULL OR (length(output_hash) = 64 AND output_hash NOT GLOB '*[^0-9a-f]*'))),
	CONSTRAINT ck_workflow_step_compensation CHECK (compensation_status IN ('none', 'pending', 'running', 'succeeded', 'failed')),
	FOREIGN KEY(workflow_run_id) REFERENCES workflow_run (id) ON DELETE CASCADE
);

CREATE INDEX ix_workflow_step_run_status ON workflow_step (workflow_run_id, status, position);

CREATE INDEX ix_workflow_step_status ON workflow_step (status);

CREATE INDEX ix_workflow_step_workflow_run_id ON workflow_step (workflow_run_id);

ALTER TABLE job ADD COLUMN workflow_run_id VARCHAR REFERENCES workflow_run(id) ON DELETE RESTRICT;

ALTER TABLE job ADD COLUMN workflow_step_id VARCHAR REFERENCES workflow_step(id) ON DELETE RESTRICT;

CREATE INDEX ix_job_workflow_run_id ON job (workflow_run_id);

CREATE INDEX ix_job_workflow_step_id ON job (workflow_step_id);
