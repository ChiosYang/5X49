import os
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from sqlalchemy import event, inspect, text
from sqlmodel import create_engine, Session

from app.canonical_models import FRESH_SCHEMA_EPOCH
from app.migrations import MigrationError, run_migrations
from app.migrations.runner import database_has_user_tables
from app.services.projections import install_projection_hooks, projection_coordinator

DEFAULT_SQLITE_FILE = Path("data") / "library.db"
sqlite_file_name = os.getenv("SQLITE_DB_PATH", str(DEFAULT_SQLITE_FILE))
sqlite_path = Path(sqlite_file_name)

if not sqlite_path.is_absolute():
    sqlite_path = Path.cwd() / sqlite_path

sqlite_path.parent.mkdir(parents=True, exist_ok=True)

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
install_projection_hooks()


def create_db_and_tables():
    import app.models  # noqa: F401

    existing_database = database_has_user_tables(sqlite_path)
    if existing_database:
        _assert_fresh_schema_epoch()
    run_migrations(
        engine,
        sqlite_path,
        app_version=_app_version(),
        backup_required=existing_database,
    )
    _assert_fresh_schema_epoch()
    projection_coordinator.bootstrap(engine)


def _assert_fresh_schema_epoch() -> None:
    with engine.connect() as connection:
        tables = set(inspect(connection).get_table_names())
        if "schema_metadata" not in tables:
            raise MigrationError(
                "This database predates the fresh Canonical baseline. "
                "Archive it and initialize a new database."
            )
        epoch = connection.execute(
            text("SELECT epoch FROM schema_metadata WHERE id = 1")
        ).scalar_one_or_none()
        if epoch != FRESH_SCHEMA_EPOCH:
            raise MigrationError(
                f"Unsupported database epoch; expected {FRESH_SCHEMA_EPOCH}"
            )


def _app_version() -> str:
    try:
        return version("backend")
    except PackageNotFoundError:
        return "0.1.0"


def get_session():
    return Session(engine)
