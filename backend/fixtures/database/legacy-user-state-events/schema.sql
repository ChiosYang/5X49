CREATE TABLE movie (
    id VARCHAR NOT NULL PRIMARY KEY,
    title VARCHAR NOT NULL,
    year INTEGER NOT NULL,
    last_seen_at VARCHAR
);

CREATE TABLE movie_user_state (
    movie_id VARCHAR NOT NULL PRIMARY KEY,
    watched BOOLEAN NOT NULL DEFAULT 0,
    watched_at VARCHAR,
    rating INTEGER,
    favorite BOOLEAN NOT NULL DEFAULT 0,
    notes VARCHAR,
    updated_at VARCHAR NOT NULL,
    FOREIGN KEY(movie_id) REFERENCES movie(id)
);

CREATE TABLE job (
    id VARCHAR NOT NULL PRIMARY KEY,
    type VARCHAR NOT NULL,
    status VARCHAR NOT NULL
);

CREATE TABLE events (
    id VARCHAR NOT NULL PRIMARY KEY,
    aggregate_type VARCHAR NOT NULL,
    aggregate_id VARCHAR,
    type VARCHAR NOT NULL,
    actor_type VARCHAR NOT NULL DEFAULT 'system',
    actor_id VARCHAR,
    command_id VARCHAR,
    correlation_id VARCHAR,
    causation_id VARCHAR,
    payload JSON,
    context JSON,
    schema_version INTEGER NOT NULL DEFAULT 1,
    occurred_at VARCHAR NOT NULL
);

INSERT INTO movie (id, title, year, last_seen_at) VALUES
    ('state_movie_watched', 'Watched Legacy Movie', 1995, '2023-01-01T10:00:00+00:00'),
    ('state_movie_review', 'Contradictory Legacy Movie', 2005, '2023-02-02T10:00:00+00:00');

INSERT INTO movie_user_state (
    movie_id,
    watched,
    watched_at,
    rating,
    favorite,
    notes,
    updated_at
) VALUES
    (
        'state_movie_watched',
        1,
        '2023-03-03T20:30:00+00:00',
        5,
        1,
        'Synthetic watched state',
        '2023-03-03T20:31:00+00:00'
    ),
    (
        'state_movie_review',
        0,
        NULL,
        3,
        0,
        'Synthetic contradictory state',
        '2023-04-04T20:31:00+00:00'
    );

INSERT INTO job (id, type, status)
VALUES ('state_job_001', 'analysis', 'completed');

INSERT INTO events (
    id,
    aggregate_type,
    aggregate_id,
    type,
    actor_type,
    payload,
    context,
    schema_version,
    occurred_at
) VALUES
    (
        'evt_legacy_state_001',
        'movie',
        'state_movie_watched',
        'MetadataMatched',
        'system',
        '{"movie_id":"state_movie_watched","title":"Watched Legacy Movie"}',
        '{"source":"legacy_fixture"}',
        1,
        '2023-01-01T10:00:00+00:00'
    ),
    (
        'evt_legacy_state_002',
        'movie',
        'state_movie_review',
        'MovieIgnored',
        'user',
        '{"movie_id":"state_movie_review"}',
        '{"source":"legacy_fixture"}',
        1,
        '2023-02-02T10:00:00+00:00'
    );
