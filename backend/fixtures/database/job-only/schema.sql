CREATE TABLE job (
    id VARCHAR NOT NULL PRIMARY KEY,
    type VARCHAR NOT NULL,
    status VARCHAR NOT NULL
);

INSERT INTO job (id, type, status)
VALUES ('job_only_001', 'scan', 'queued');
