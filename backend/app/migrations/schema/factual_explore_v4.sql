CREATE TABLE explore_film_read_model (
	film_id VARCHAR NOT NULL,
	sort_title VARCHAR NOT NULL,
	release_year INTEGER,
	watched BOOLEAN NOT NULL,
	source_hash VARCHAR NOT NULL,
	projection_version VARCHAR NOT NULL,
	projected_at VARCHAR NOT NULL,
	PRIMARY KEY (film_id),
	CONSTRAINT ck_explore_film_read_hash CHECK (length(source_hash) = 64 AND source_hash NOT GLOB '*[^0-9a-f]*'),
	FOREIGN KEY(film_id) REFERENCES film (id) ON DELETE CASCADE
);

CREATE INDEX ix_explore_film_read_model_sort_title ON explore_film_read_model (sort_title);

CREATE INDEX ix_explore_film_read_model_release_year ON explore_film_read_model (release_year);

CREATE INDEX ix_explore_film_read_model_watched ON explore_film_read_model (watched);

CREATE INDEX ix_explore_film_watched_sort ON explore_film_read_model (watched, sort_title, film_id);

CREATE INDEX ix_explore_film_year_sort ON explore_film_read_model (release_year, sort_title, film_id);

CREATE TABLE explore_facet_read_model (
	dimension VARCHAR NOT NULL,
	facet_key VARCHAR NOT NULL,
	film_id VARCHAR NOT NULL,
	display_label VARCHAR NOT NULL,
	normalized_label VARCHAR NOT NULL,
	eligible BOOLEAN NOT NULL,
	conflicted BOOLEAN NOT NULL,
	payload JSON NOT NULL,
	source_hash VARCHAR NOT NULL,
	projection_version VARCHAR NOT NULL,
	projected_at VARCHAR NOT NULL,
	PRIMARY KEY (dimension, facet_key, film_id),
	CONSTRAINT ck_explore_facet_dimension CHECK (dimension IN ('genre', 'person', 'country', 'decade')),
	CONSTRAINT ck_explore_facet_conflict_eligibility CHECK (conflicted = 0 OR eligible = 0),
	CONSTRAINT ck_explore_facet_read_hash CHECK (length(source_hash) = 64 AND source_hash NOT GLOB '*[^0-9a-f]*'),
	FOREIGN KEY(film_id) REFERENCES film (id) ON DELETE CASCADE
);

CREATE INDEX ix_explore_facet_read_model_eligible ON explore_facet_read_model (eligible);

CREATE INDEX ix_explore_facet_read_model_conflicted ON explore_facet_read_model (conflicted);

CREATE INDEX ix_explore_facet_dimension_label ON explore_facet_read_model (dimension, eligible, normalized_label, facet_key);

CREATE INDEX ix_explore_facet_dimension_key ON explore_facet_read_model (dimension, facet_key, eligible, film_id);

CREATE INDEX ix_explore_facet_film_dimension ON explore_facet_read_model (film_id, dimension);
