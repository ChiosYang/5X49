CREATE TABLE movie (
    id VARCHAR NOT NULL PRIMARY KEY,
    title VARCHAR NOT NULL,
    title_cn VARCHAR,
    year INTEGER NOT NULL,
    tmdb_id VARCHAR,
    imdb_id VARCHAR,
    overview VARCHAR,
    runtime INTEGER,
    folder_name VARCHAR,
    folder_path VARCHAR,
    media_path VARCHAR,
    video_file VARCHAR,
    file_size INTEGER,
    poster_local VARCHAR,
    backdrop_local VARCHAR,
    poster_path VARCHAR,
    backdrop_path VARCHAR,
    nfo_file VARCHAR,
    nfo_path VARCHAR,
    last_seen_at VARCHAR,
    library_status VARCHAR
);

INSERT INTO movie (
    id, title, title_cn, year, tmdb_id, imdb_id, overview, runtime,
    folder_name, folder_path, media_path, video_file, file_size,
    poster_local, backdrop_local, poster_path, backdrop_path,
    nfo_file, nfo_path, last_seen_at, library_status
) VALUES
    (
        'identity_a', 'Shared Identity A', '共享身份 A', 1999, '42', 'tt0000042',
        'First identity source', 120, 'A', 'A', 'A/movie-a.mkv', 'movie-a.mkv', 1000,
        'A/poster.jpg', 'A/backdrop.jpg', '/poster/42.jpg', '/backdrop/42.jpg',
        'movie-a.nfo', 'A/movie-a.nfo', '2026-01-01T00:00:00Z', 'available'
    ),
    (
        'identity_b', 'Shared Identity B', NULL, 1999, '42', 'TT0000042',
        'Second library edition', 121, 'B', 'B', 'B/movie-b.mkv', 'movie-b.mkv', 2000,
        'B/poster.jpg', NULL, '/poster/42.jpg', '/backdrop/42.jpg',
        'movie-b.nfo', 'B/movie-b.nfo', '2026-01-02T00:00:00Z', 'available'
    ),
    (
        'identity_c', 'Other Identity', NULL, 2005, '99', 'tt0000099',
        'Other identity source', 90, 'C', 'C', 'C/movie-c.mkv', 'movie-c.mkv', 3000,
        NULL, NULL, '/poster/99.jpg', NULL,
        'movie-c.nfo', 'C/movie-c.nfo', '2026-01-03T00:00:00Z', 'missing'
    ),
    (
        'identity_conflict', 'Conflicting Identity', NULL, 2010, '42', 'tt0000099',
        'Must not auto merge', 100, 'Conflict', 'Conflict', 'Conflict/movie.mkv', 'movie.mkv', 4000,
        NULL, NULL, NULL, NULL,
        'movie.nfo', 'Conflict/movie.nfo', '2026-01-04T00:00:00Z', 'available'
    ),
    (
        'same_title_one', 'The Same Name', NULL, 1988, NULL, NULL,
        'First distinct work', 80, 'Same One', 'Same-One', 'Same-One/movie.mkv', 'movie.mkv', 5000,
        NULL, NULL, NULL, NULL,
        NULL, NULL, '2026-01-05T00:00:00Z', 'available'
    ),
    (
        'same_title_two', 'The Same Name', NULL, 1988, NULL, NULL,
        'Second distinct work', 81, 'Same Two', 'Same-Two', 'Same-Two/movie.mkv', 'movie.mkv', 6000,
        NULL, NULL, NULL, NULL,
        NULL, NULL, '2026-01-06T00:00:00Z', 'ignored'
    );
