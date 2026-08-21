CREATE TABLE movie (
    id VARCHAR NOT NULL PRIMARY KEY,
    title VARCHAR NOT NULL,
    year INTEGER NOT NULL,
    tmdb_id VARCHAR,
    imdb_id VARCHAR,
    folder_path VARCHAR,
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

INSERT INTO movie (id, title, year, tmdb_id, imdb_id, folder_path, last_seen_at) VALUES
    ('viewing_a', 'Shared Viewing Film A', 2001, '777', 'tt0000777', 'Edition-A', '2026-01-01T00:00:00Z'),
    ('viewing_b', 'Shared Viewing Film B', 2001, '777', 'TT0000777', 'Edition-B', '2026-01-02T00:00:00Z'),
    ('viewing_empty', 'Empty State Film', 2002, NULL, NULL, 'Empty', '2026-01-03T00:00:00Z'),
    ('viewing_favorite', 'Favorite Only Film', 2003, NULL, NULL, 'Favorite', '2026-01-04T00:00:00Z');

INSERT INTO movie_user_state (
    movie_id, watched, watched_at, rating, favorite, notes, updated_at
) VALUES
    (
        'viewing_a', 1, '2025-05-06T20:30:00Z', 5, 0,
        'Confirmed legacy viewing', '2025-05-06T20:31:00Z'
    ),
    (
        'viewing_b', 0, NULL, 3, 1,
        'Needs review but must survive', '2025-06-07T20:31:00Z'
    ),
    (
        'viewing_empty', 0, NULL, NULL, 0, NULL, '2025-07-08T20:31:00Z'
    ),
    (
        'viewing_favorite', 0, NULL, NULL, 1, NULL, '2025-08-09T20:31:00Z'
    );
