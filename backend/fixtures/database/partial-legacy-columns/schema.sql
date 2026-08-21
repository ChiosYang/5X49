CREATE TABLE movie (
    id VARCHAR NOT NULL PRIMARY KEY,
    title VARCHAR NOT NULL,
    year INTEGER NOT NULL,
    media_path VARCHAR,
    last_seen_at VARCHAR,
    library_status VARCHAR,
    metadata_updated_at VARCHAR
);

CREATE TABLE job (
    id VARCHAR NOT NULL PRIMARY KEY,
    type VARCHAR NOT NULL,
    status VARCHAR NOT NULL,
    priority INTEGER
);

INSERT INTO movie (
    id,
    title,
    year,
    media_path,
    last_seen_at,
    library_status,
    metadata_updated_at
) VALUES (
    'partial_movie_001',
    'Partially Migrated',
    2001,
    'media/Partially Migrated (2001)/movie.mkv',
    '2024-01-01T00:00:00+00:00',
    'missing',
    '2025-02-03T04:05:06+00:00'
);

INSERT INTO job (id, type, status, priority)
VALUES ('partial_job_001', 'scan', 'failed', 7);
