import os
from pathlib import Path
from shutil import copy2

from sqlalchemy import inspect, text
from sqlmodel import SQLModel, create_engine, Session

DEFAULT_SQLITE_FILE = Path("data") / "library.db"
LEGACY_SQLITE_FILE = Path("library.db")

sqlite_file_name = os.getenv("SQLITE_DB_PATH", str(DEFAULT_SQLITE_FILE))
sqlite_path = Path(sqlite_file_name)

if not sqlite_path.is_absolute():
    sqlite_path = Path.cwd() / sqlite_path

sqlite_path.parent.mkdir(parents=True, exist_ok=True)

if "SQLITE_DB_PATH" not in os.environ:
    legacy_sqlite_path = Path.cwd() / LEGACY_SQLITE_FILE
    if not sqlite_path.exists() and legacy_sqlite_path.exists():
        copy2(legacy_sqlite_path, sqlite_path)

sqlite_url = f"sqlite:///{sqlite_path}"

engine = create_engine(sqlite_url, connect_args={"timeout": 30})

MOVIE_SCHEMA_COLUMNS = {
    "media_path": "VARCHAR",
    "folder_path": "VARCHAR",
    "file_size": "INTEGER",
    "file_mtime": "FLOAT",
    "last_seen_at": "VARCHAR",
    "missing_since": "VARCHAR",
    "library_status": "VARCHAR DEFAULT 'available'",
    "metadata_updated_at": "VARCHAR",
    "countries": "JSON",
    "audio_tracks": "JSON",
}


def migrate_sqlite_schema():
    """Add lightweight columns for existing SQLite databases.

    SQLModel's create_all creates missing tables, but it does not alter an
    existing table. This project does not use Alembic, so keep migrations
    explicit and narrowly scoped.
    """
    if not sqlite_url.startswith("sqlite:///"):
        return

    inspector = inspect(engine)
    if "movie" not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns("movie")}
    missing_columns = [
        (name, column_type)
        for name, column_type in MOVIE_SCHEMA_COLUMNS.items()
        if name not in existing_columns
    ]
    if not missing_columns:
        return

    with engine.begin() as connection:
        for name, column_type in missing_columns:
            connection.execute(text(f"ALTER TABLE movie ADD COLUMN {name} {column_type}"))

        if "library_status" in dict(missing_columns):
            connection.execute(
                text("UPDATE movie SET library_status = 'available' WHERE library_status IS NULL")
            )

def create_db_and_tables():
    SQLModel.metadata.create_all(engine)
    migrate_sqlite_schema()

def get_session():
    return Session(engine)
