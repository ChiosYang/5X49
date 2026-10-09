"""Bounded, read-only diagnostics. Never return provider messages or private paths."""
import os
import re
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path
import requests
import app.database as database
from app.migrations.versions import MIGRATIONS
from app.services.projections import PROJECTION_VERSIONS
from app.services.settings import get_media_dir, get_tmdb_api_key
from app.services.metadata.tmdb import TMDBClient


def system_diagnostics() -> dict:
    path = database.sqlite_path.resolve()
    db = {"state": "unavailable", "schema_version": None, "expected_schema_version": MIGRATIONS[-1].version}
    projections = []
    try:
        with closing(sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True, timeout=1)) as connection:
            check = connection.execute("PRAGMA quick_check(1)").fetchone()[0]
            version = connection.execute("SELECT MAX(version) FROM schema_migrations WHERE status='applied'").fetchone()[0]
            db.update(schema_version=version, state="ready" if check == "ok" and version == MIGRATIONS[-1].version else "needs_attention")
            rows = {name:(status,version) for name,status,version in connection.execute("SELECT name,status,projection_version FROM projection_state")}
            projections = [{"name":name,"state":"ready" if rows.get(name)==("ready",version) else "needs_attention"}
                for name,version in PROJECTION_VERSIONS.items()]
    except (OSError, sqlite3.Error):
        pass
    # A missing DB must stay missing; settings readers otherwise open SQLite.
    media = Path(get_media_dir() if db["state"] != "unavailable" else os.getenv("MEDIA_DIR", "/media"))
    media_state = "ready" if media.is_dir() and os.access(media,os.R_OK | os.X_OK) else "unavailable"
    try:
        backup_space = shutil.disk_usage(path.parent).free >= max(100 * 1024 * 1024, path.stat().st_size * 3)
    except OSError:
        backup_space = False
    return {"backend":"ready", "database":db, "projections":projections,
        "media":{"state":media_state,"writable":media_state == "ready" and os.access(media,os.W_OK)},
        "backup_space":{"state":"ready" if backup_space else "needs_attention"},
        "tmdb":{"state":"configured" if (get_tmdb_api_key() if db["state"] != "unavailable" else os.getenv("TMDB_API_KEY")) else "not_configured"}}


def _http_state(status: int) -> dict:
    state = ("ready" if 200 <= status < 300 else "credentials_rejected" if status == 401
        else "access_denied" if status == 403 else "rate_limited" if status == 429 else "unavailable")
    return {"state":state,"status_code":status}


def _network_failure(error: requests.RequestException) -> dict:
    state = ("tls_failed" if isinstance(error,requests.exceptions.SSLError)
        else "proxy_failed" if isinstance(error,requests.exceptions.ProxyError)
        else "timeout" if isinstance(error,requests.Timeout) else "connection_failed")
    return {"state":state,"status_code":None}


def provider_diagnostics() -> dict:
    key = get_tmdb_api_key()
    result = {"tmdb":{"state":"not_configured","status_code":None}, "artwork":{"state":"not_checked","status_code":None}}
    if not key: return result
    client = TMDBClient()
    with requests.Session() as session:
        try:
            client.rate_limiter.acquire()
            response = session.get(f"{client.base_url}/movie/5511",params={"api_key":key},timeout=(3,8),allow_redirects=False)
            result["tmdb"] = _http_state(response.status_code)
            if response.status_code != 200: return result
            data = response.json()
            if not isinstance(data,dict) or data.get("id") != 5511:
                result["tmdb"]["state"] = "invalid_response"
                return result
            poster = data.get("poster_path")
            if not isinstance(poster,str) or not re.fullmatch(r"/[A-Za-z0-9_-]+\.(jpg|png|webp)",poster):
                result["artwork"]["state"] = "no_artwork"
                return result
        except requests.RequestException as error:
            result["tmdb"] = _network_failure(error)
            return result
        except ValueError:
            result["tmdb"]["state"] = "invalid_response"
            return result
        try:
            with session.get(client.image_url(poster,"w92"),timeout=(3,8),allow_redirects=False,stream=True) as response:
                result["artwork"] = _http_state(response.status_code)
        except requests.RequestException as error:
            result["artwork"] = _network_failure(error)
    return result
