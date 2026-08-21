CREATE TABLE movie (
    id VARCHAR NOT NULL PRIMARY KEY,
    title VARCHAR NOT NULL,
    year INTEGER NOT NULL
);

INSERT INTO movie (id, title, year)
VALUES ('movie_only_001', 'Movie Without Jobs', 1984);
