CREATE TABLE cinema_dna_film_read_model (
    profile_id VARCHAR NOT NULL,
    film_id VARCHAR NOT NULL,
    payload JSON NOT NULL,
    source_hash VARCHAR NOT NULL,
    projection_version VARCHAR NOT NULL,
    projected_at VARCHAR NOT NULL,
    PRIMARY KEY (profile_id, film_id),
    CONSTRAINT ck_cinema_dna_film_read_hash CHECK (length(source_hash) = 64 AND source_hash NOT GLOB '*[^0-9a-f]*'),
    FOREIGN KEY(profile_id) REFERENCES local_profile (id) ON DELETE CASCADE,
    FOREIGN KEY(film_id) REFERENCES film (id) ON DELETE CASCADE
);
