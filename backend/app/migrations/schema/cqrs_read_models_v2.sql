CREATE TABLE projection_state (
	name VARCHAR NOT NULL,
	projection_version VARCHAR NOT NULL,
	status VARCHAR NOT NULL,
	row_count INTEGER NOT NULL,
	digest VARCHAR,
	rebuilt_at VARCHAR,
	updated_at VARCHAR NOT NULL,
	PRIMARY KEY (name),
	CONSTRAINT ck_projection_state_status CHECK (status IN ('ready', 'rebuilding', 'failed')),
	CONSTRAINT ck_projection_state_values CHECK (row_count >= 0 AND length(projection_version) > 0),
	CONSTRAINT ck_projection_state_digest CHECK (digest IS NULL OR (length(digest) = 64 AND digest NOT GLOB '*[^0-9a-f]*'))
);

CREATE INDEX ix_projection_state_status ON projection_state (status);

CREATE TABLE library_film_read_model (
	film_id VARCHAR NOT NULL,
	sort_title VARCHAR NOT NULL,
	release_year INTEGER,
	primary_item_id VARCHAR,
	visible BOOLEAN NOT NULL,
	payload JSON NOT NULL,
	source_hash VARCHAR NOT NULL,
	projection_version VARCHAR NOT NULL,
	projected_at VARCHAR NOT NULL,
	PRIMARY KEY (film_id),
	CONSTRAINT ck_library_film_read_hash CHECK (length(source_hash) = 64 AND source_hash NOT GLOB '*[^0-9a-f]*'),
	FOREIGN KEY(film_id) REFERENCES film (id) ON DELETE CASCADE
);

CREATE INDEX ix_library_film_read_model_primary_item_id ON library_film_read_model (primary_item_id);

CREATE INDEX ix_library_film_read_model_release_year ON library_film_read_model (release_year);

CREATE INDEX ix_library_film_read_model_sort_title ON library_film_read_model (sort_title);

CREATE INDEX ix_library_film_read_model_visible ON library_film_read_model (visible);

CREATE INDEX ix_library_film_read_sort ON library_film_read_model (visible, sort_title, release_year);

CREATE TABLE film_detail_read_model (
	film_id VARCHAR NOT NULL,
	payload JSON NOT NULL,
	source_hash VARCHAR NOT NULL,
	projection_version VARCHAR NOT NULL,
	projected_at VARCHAR NOT NULL,
	PRIMARY KEY (film_id),
	CONSTRAINT ck_film_detail_read_hash CHECK (length(source_hash) = 64 AND source_hash NOT GLOB '*[^0-9a-f]*'),
	FOREIGN KEY(film_id) REFERENCES film (id) ON DELETE CASCADE
);

CREATE TABLE film_search_read_model (
	film_id VARCHAR NOT NULL,
	normalized_title VARCHAR NOT NULL,
	release_year INTEGER,
	search_text VARCHAR NOT NULL,
	source_hash VARCHAR NOT NULL,
	projection_version VARCHAR NOT NULL,
	projected_at VARCHAR NOT NULL,
	PRIMARY KEY (film_id),
	CONSTRAINT ck_film_search_read_hash CHECK (length(source_hash) = 64 AND source_hash NOT GLOB '*[^0-9a-f]*'),
	FOREIGN KEY(film_id) REFERENCES film (id) ON DELETE CASCADE
);

CREATE INDEX ix_film_search_read_model_normalized_title ON film_search_read_model (normalized_title);

CREATE INDEX ix_film_search_read_model_release_year ON film_search_read_model (release_year);

CREATE INDEX ix_film_search_read_title_year ON film_search_read_model (normalized_title, release_year);

CREATE TABLE graph_node_read_model (
	entity_id VARCHAR NOT NULL,
	entity_type VARCHAR NOT NULL,
	display_label VARCHAR NOT NULL,
	secondary_label VARCHAR,
	owned BOOLEAN NOT NULL,
	payload JSON NOT NULL,
	source_hash VARCHAR NOT NULL,
	projection_version VARCHAR NOT NULL,
	projected_at VARCHAR NOT NULL,
	PRIMARY KEY (entity_id),
	CONSTRAINT ck_graph_node_read_entity_type CHECK (entity_type IN ('film', 'person', 'concept')),
	CONSTRAINT ck_graph_node_read_hash CHECK (length(source_hash) = 64 AND source_hash NOT GLOB '*[^0-9a-f]*'),
	FOREIGN KEY(entity_id) REFERENCES graph_entity (id) ON DELETE CASCADE
);

CREATE INDEX ix_graph_node_read_model_entity_type ON graph_node_read_model (entity_type);

CREATE INDEX ix_graph_node_read_model_owned ON graph_node_read_model (owned);

CREATE INDEX ix_graph_node_read_type_label ON graph_node_read_model (entity_type, display_label);

CREATE TABLE graph_edge_read_model (
	edge_id VARCHAR NOT NULL,
	edge_kind VARCHAR NOT NULL,
	subject_entity_id VARCHAR NOT NULL,
	object_entity_id VARCHAR NOT NULL,
	relation VARCHAR NOT NULL,
	priority INTEGER NOT NULL,
	payload JSON NOT NULL,
	source_hash VARCHAR NOT NULL,
	projection_version VARCHAR NOT NULL,
	projected_at VARCHAR NOT NULL,
	PRIMARY KEY (edge_id),
	CONSTRAINT ck_graph_edge_read_kind CHECK (edge_kind IN ('credit', 'assertion')),
	CONSTRAINT ck_graph_edge_read_hash CHECK (length(source_hash) = 64 AND source_hash NOT GLOB '*[^0-9a-f]*'),
	FOREIGN KEY(subject_entity_id) REFERENCES graph_entity (id) ON DELETE CASCADE,
	FOREIGN KEY(object_entity_id) REFERENCES graph_entity (id) ON DELETE CASCADE
);

CREATE INDEX ix_graph_edge_read_model_edge_kind ON graph_edge_read_model (edge_kind);

CREATE INDEX ix_graph_edge_read_model_object_entity_id ON graph_edge_read_model (object_entity_id);

CREATE INDEX ix_graph_edge_read_model_priority ON graph_edge_read_model (priority);

CREATE INDEX ix_graph_edge_read_model_relation ON graph_edge_read_model (relation);

CREATE INDEX ix_graph_edge_read_model_subject_entity_id ON graph_edge_read_model (subject_entity_id);

CREATE INDEX ix_graph_edge_read_object_priority ON graph_edge_read_model (object_entity_id, priority, edge_id);

CREATE INDEX ix_graph_edge_read_subject_priority ON graph_edge_read_model (subject_entity_id, priority, edge_id);
