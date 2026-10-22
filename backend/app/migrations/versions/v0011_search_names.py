from sqlalchemy import Connection, text
from app.migrations.runner import Migration


def upgrade(connection: Connection) -> None:
    connection.execute(text("ALTER TABLE film_search_read_model ADD COLUMN exact_titles VARCHAR NOT NULL DEFAULT ''"))
    connection.execute(text("""CREATE TABLE person_alias (
        id VARCHAR NOT NULL PRIMARY KEY,
        person_id VARCHAR NOT NULL REFERENCES person(id) ON DELETE CASCADE,
        film_id VARCHAR NOT NULL REFERENCES film(id) ON DELETE CASCADE,
        identity_id VARCHAR NOT NULL REFERENCES external_identity(id) ON DELETE CASCADE,
        name VARCHAR NOT NULL, normalized_name VARCHAR NOT NULL,
        origin_kind VARCHAR NOT NULL, origin_ref VARCHAR NOT NULL,
        observed_at VARCHAR NOT NULL, superseded_at VARCHAR,
        CONSTRAINT uq_person_alias_source_value UNIQUE (person_id, film_id, normalized_name, origin_kind, origin_ref))"""))
    connection.execute(text("CREATE INDEX ix_person_alias_name_active ON person_alias(normalized_name, superseded_at)"))
    connection.execute(text("CREATE INDEX ix_person_alias_person_id ON person_alias(person_id)"))
    connection.execute(text("CREATE INDEX ix_person_alias_film_id ON person_alias(film_id)"))


MIGRATION = Migration(version=11, name="search_names",
    checksum_material="fresh-canonical-v11:stable-source-person-alias-v1", upgrade=upgrade)
