import os
from pathlib import Path
from shutil import copy2

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

engine = create_engine(sqlite_url)

def create_db_and_tables():
    SQLModel.metadata.create_all(engine)

def get_session():
    return Session(engine)
