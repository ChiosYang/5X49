import os
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from shutil import copy2

from sqlalchemy import event
from sqlmodel import SQLModel, create_engine, Session

from app.migrations import run_migrations
from app.migrations.runner import database_has_user_tables

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


def configure_sqlite_engine(sqlite_engine) -> None:
    event.listen(sqlite_engine, "connect", _enable_sqlite_foreign_keys)


def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys = ON")
    finally:
        cursor.close()


configure_sqlite_engine(engine)


def create_db_and_tables():
    import app.models  # noqa: F401

    existing_database = database_has_user_tables(sqlite_path)
    if existing_database:
        run_migrations(
            engine,
            sqlite_path,
            app_version=_app_version(),
        )

    SQLModel.metadata.create_all(engine)

    if not existing_database:
        run_migrations(
            engine,
            sqlite_path,
            app_version=_app_version(),
            backup_required=False,
        )


def _app_version() -> str:
    try:
        return version("backend")
    except PackageNotFoundError:
        return "0.1.0"


def get_session():
    return Session(engine)
