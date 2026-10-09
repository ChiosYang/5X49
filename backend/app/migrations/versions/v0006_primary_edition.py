from sqlalchemy import Connection, text
from app.migrations.runner import Migration


def upgrade(connection: Connection) -> None:
    connection.execute(text(
        "ALTER TABLE film_profile_state ADD COLUMN primary_item_id VARCHAR "
        "REFERENCES library_item(id) ON DELETE SET NULL"
    ))
    # Preserve the previously displayed default when rebuilding v1 read models.
    # Match both Film and profile; never carry an unrelated/retired edition.
    selection = (
        "SELECT i.id FROM library_film_read_model r JOIN library_item i ON i.id=r.primary_item_id "
        "JOIN film f ON f.id=r.film_id WHERE r.film_id=film_profile_state.film_id "
        "AND i.film_id=r.film_id AND i.profile_id=film_profile_state.profile_id "
        "AND i.availability_status<>'retired' AND f.lifecycle_status='active'"
    )
    connection.execute(text(f"UPDATE film_profile_state SET primary_item_id=({selection}) WHERE primary_item_id IS NULL"))
    connection.execute(text(
        "INSERT INTO film_profile_state (profile_id,film_id,favorite,primary_item_id,created_at,updated_at) "
        "SELECT i.profile_id,r.film_id,0,i.id,strftime('%Y-%m-%dT%H:%M:%f+00:00','now'),"
        "strftime('%Y-%m-%dT%H:%M:%f+00:00','now') FROM library_film_read_model r "
        "JOIN library_item i ON i.id=r.primary_item_id JOIN film f ON f.id=r.film_id "
        "WHERE i.film_id=r.film_id AND i.availability_status<>'retired' AND f.lifecycle_status='active' "
        "AND NOT EXISTS (SELECT 1 FROM film_profile_state s WHERE s.profile_id=i.profile_id AND s.film_id=r.film_id)"
    ))


MIGRATION = Migration(
    version=6, name="primary_edition", checksum_material="fresh-canonical-v6:primary-item-fk-preserve-read-default-v2",
    upgrade=upgrade,
)
