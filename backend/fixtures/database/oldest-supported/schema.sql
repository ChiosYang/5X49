CREATE TABLE movie (
    id VARCHAR NOT NULL PRIMARY KEY,
    title VARCHAR NOT NULL,
    title_cn VARCHAR,
    year INTEGER NOT NULL,
    poster_local VARCHAR,
    backdrop_local VARCHAR,
    poster_path VARCHAR,
    backdrop_path VARCHAR,
    tmdb_id VARCHAR,
    imdb_id VARCHAR,
    overview VARCHAR,
    plot VARCHAR,
    director VARCHAR,
    runtime INTEGER,
    imdb_rating FLOAT,
    genres JSON,
    actors JSON,
    analysis_status VARCHAR NOT NULL DEFAULT 'pending',
    micro_genre VARCHAR,
    micro_genre_definition VARCHAR,
    analysis_data JSON,
    folder_name VARCHAR,
    video_file VARCHAR,
    nfo_source VARCHAR,
    last_seen_at VARCHAR
);

CREATE TABLE job (
    id VARCHAR NOT NULL PRIMARY KEY,
    type VARCHAR NOT NULL,
    status VARCHAR NOT NULL DEFAULT 'queued',
    payload JSON,
    progress JSON,
    result JSON,
    error VARCHAR,
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 1,
    created_at VARCHAR NOT NULL,
    updated_at VARCHAR NOT NULL,
    started_at VARCHAR,
    finished_at VARCHAR
);

INSERT INTO movie (
    id,
    title,
    title_cn,
    year,
    tmdb_id,
    genres,
    analysis_status,
    folder_name,
    video_file,
    last_seen_at
) VALUES (
    'legacy_movie_001',
    'Legacy Sentinel',
    '旧库哨兵电影',
    1999,
    'legacy-tmdb-001',
    '["Drama"]',
    'completed',
    'Legacy Sentinel (1999)',
    'Legacy.Sentinel.1999.mkv',
    '2024-01-02T03:04:05+00:00'
);

INSERT INTO job (
    id,
    type,
    status,
    payload,
    attempts,
    max_attempts,
    created_at,
    updated_at
) VALUES (
    'legacy_job_001',
    'scan',
    'completed',
    '{"source":"fixture"}',
    1,
    1,
    '2024-01-02T03:04:05+00:00',
    '2024-01-02T03:05:05+00:00'
);
