#!/usr/bin/env python3
"""Exercise pulled RC images using a unique Compose project and synthetic data only."""

import argparse
import hashlib
import json
import os
import socket
import subprocess
import time
import urllib.request
import uuid
from pathlib import Path

from release_rc import DIGEST, PLATFORMS, ROOT, ReleaseError


def port():
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        return server.getsockname()[1]


def request(base, path, method="GET", data=None):
    body = None if data is None else json.dumps(data).encode()
    req = urllib.request.Request(base + path, data=body, method=method, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def smoke(args):
    release = json.loads(args.release.read_text(encoding="utf-8"))
    if release["distribution"] != "registry" or args.platform not in release["platforms"]:
        raise ReleaseError("Smoke requires registry-distributed images for the selected platform")
    for service in ("backend", "frontend"):
        image = release["images"][service]
        if not DIGEST.fullmatch(image["digest"]) or not image["reference"].endswith("@" + image["digest"]):
            raise ReleaseError("Smoke requires digest-pinned image references")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    media = output / "media"
    film_dir = media / "RC Film (1999)"
    film_dir.mkdir(parents=True)
    (film_dir / "movie.nfo").write_text("<movie><title>RC Film</title><year>1999</year><genre>Drama</genre><country>Japan</country></movie>")
    (film_dir / "film.mkv").write_bytes(b"synthetic media for RC scan; not a real video")
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in film_dir.iterdir()}
    data_dir = output / "data"
    data_dir.mkdir()
    frontend_port, backend_port = port(), port()
    while frontend_port == backend_port:
        backend_port = port()
    environment = {**os.environ, "BACKEND_IMAGE": release["images"]["backend"]["reference"],
                   "FRONTEND_IMAGE": release["images"]["frontend"]["reference"],
                   "MEDIA_DIR": str(media), "MEDIA_READ_ONLY": "true", "WATCH_LIBRARY": "false",
                   "TMDB_API_KEY": "", "OPENROUTER_API_KEY": "", "BIND_ADDRESS": "127.0.0.1",
                   "BACKEND_PORT": str(backend_port), "FRONTEND_PORT": str(frontend_port),
                   "ALLOWED_ORIGINS": f"http://localhost:{frontend_port}", "COMPOSE_PROFILES": ""}
    # Never load a repository/operator .env file; explicit fixture settings win.
    settings = output / "smoke-settings.env"
    settings.write_text("# Synthetic acceptance; no credentials.\n")
    override = output / "compose.override.json"
    override.write_text(json.dumps({"services": {
        "backend": {"platform": args.platform, "volumes": [{"type": "bind", "source": str(data_dir), "target": "/app/data"}]},
        "frontend": {"platform": args.platform},
    }}))
    project = "5x49-rc-" + args.platform.split("/")[1] + "-" + uuid.uuid4().hex[:8]
    command = ["docker", "compose", "--env-file", str(settings), "--project-name", project,
               "-f", str(ROOT / "docker-compose.release.yml"), "-f", str(override)]
    log = (output / "commands.log").open("w", encoding="utf-8")

    def compose(*arguments, capture=False):
        result = subprocess.run(command + list(arguments), env=environment, text=True,
                                stdout=subprocess.PIPE if capture else log, stderr=log)
        if result.returncode:
            raise ReleaseError(f"Compose {arguments[0]} failed; inspect {output / 'commands.log'}")
        return result.stdout

    def python(code):
        return compose("run", "--rm", "--no-deps", "-T", "backend", "python", "-c", code, capture=True).strip()

    def up():
        compose("up", "-d", "--wait", "--wait-timeout", "240")

    base = f"http://127.0.0.1:{frontend_port}/api"
    evidence = {"source_revision": release["source_revision"], "platform": args.platform, "images": release["images"],
                "project": project, "checks": []}
    try:
        compose("config", "--quiet")
        compose("pull")
        up()
        for service in ("backend", "frontend"):
            container = compose("ps", "-q", service, capture=True).strip()
            image_id = subprocess.check_output(["docker", "inspect", "--format", "{{.Image}}", container], text=True).strip()
            image = json.loads(subprocess.check_output(["docker", "image", "inspect", image_id], text=True))[0]
            if "linux/" + image["Architecture"] != args.platform:
                raise ReleaseError("Installed image architecture does not match requested platform")
            if image["Config"]["Labels"].get("org.opencontainers.image.revision") != release["source_revision"]:
                raise ReleaseError("Installed image does not match source revision")
        assert request(base, "/health")["status"] == "healthy"
        assert request(base, "/ask/status")["configured"] is False
        assert request(base, "/library/films") == []
        for _ in range(2):
            workflow = request(base, "/library/scan", "POST")["workflow_id"]
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                state = request(base, "/workflows/" + workflow)["status"]
                if state in ("succeeded", "failed", "cancelled"):
                    assert state == "succeeded", state
                    break
                time.sleep(0.25)
            else:
                raise ReleaseError("Scan timeout")
        films = request(base, "/library/films")
        assert len(films) == 1
        film_id = films[0]["id"]
        profile_path = "/films/" + film_id + "/profile-state"
        request(base, profile_path, "PUT", {"rating": 4, "notes": "RC before restore"})
        request(base, "/films/" + film_id + "/viewings", "POST", {"watched_at": "2026-10-01"})
        result = request(base, "/ask/query", "POST", {"plan": {"decade": 1990}, "confirmed": True})
        assert result["results"]["total"] == 1
        assert request(base, "/profile/cinema-dna")["totals"]["watched_films"] == 1
        for route in ("/en", "/zh", "/en/ask", "/zh/diary"):
            with urllib.request.urlopen(f"http://127.0.0.1:{frontend_port}" + route, timeout=30) as response:
                assert response.status == 200
        evidence["checks"].append("fresh install, proxy, no-key scan/reconcile, profile, Viewing, DNA, Ask, localized pages")
        compose("stop")
        up()
        assert request(base, profile_path)["rating"] == 4
        backup = json.loads(compose("run", "--rm", "--no-deps", "-T", "backend", "python", "-m", "app.backup",
                                    "--database", "data/library.db", "--backup-dir", "data/backups/rc", capture=True))
        manifest = "data/backups/rc/" + backup["manifest_file"]
        request(base, profile_path, "PUT", {"rating": 2, "notes": "RC after backup"})
        compose("stop")
        target_hash = python("import sqlite3,hashlib; from pathlib import Path; c=sqlite3.connect('data/library.db'); assert c.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()[0] == 0; c.close(); print(hashlib.sha256(Path('data/library.db').read_bytes()).hexdigest())")
        compose("run", "--rm", "--no-deps", "-T", "backend", "python", "-m", "app.migrations.restore", "--manifest", manifest)
        compose("run", "--rm", "--no-deps", "-T", "backend", "python", "-m", "app.migrations.restore", "--manifest", manifest,
                "--replace", "--target", "data/library.db", "--confirm-current-sha256", target_hash)
        compose("run", "--rm", "--no-deps", "-T", "backend", "python", "-m", "app.projections", "verify")
        up()
        restored = request(base, profile_path)
        assert restored["rating"] == 4 and restored["notes"] == "RC before restore"
        assert request(base, "/library/films")[0]["id"] == film_id
        assert request(base, "/profile/cinema-dna")["totals"]["watched_films"] == 1
        assert {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in film_dir.iterdir()} == before
        evidence["checks"].append("restart, online backup, offline preview/restore, projections, Film identity and personal state preserved; media unchanged")
        compose("stop")
        # A separate synthetic v4 database tests the actual container's startup upgrade.
        python("""from pathlib import Path
from sqlmodel import create_engine, Session, select
from app.migrations.runner import run_migrations
from app.migrations.versions import MIGRATIONS
from app.canonical_models import Film, GraphEntity, LocalProfile, FilmProfileState, Viewing
path = Path('/app/data/upgrade.db')
engine = create_engine(f'sqlite:///{path}')
run_migrations(engine, path, migrations=MIGRATIONS[:4], backup_required=False)
with Session(engine) as session:
    profile = session.exec(select(LocalProfile.id)).one()
    film_id = 'film_' + 'a' * 32
    session.add(GraphEntity(id=film_id, entity_type='film'))
    session.flush()
    session.add(Film(id=film_id, canonical_title='Upgrade fixture', release_year=1999))
    session.flush()
    session.add(FilmProfileState(profile_id=profile, film_id=film_id, rating=5, notes='upgrade sentinel'))
    session.add(Viewing(id='view_' + 'b' * 32, profile_id=profile, film_id=film_id, source='diary', source_record_id='rc'))
    session.commit()
engine.dispose()
""")
        override_data = json.loads(override.read_text())
        override_data["services"]["backend"]["environment"] = {"SQLITE_DB_PATH": "/app/data/upgrade.db"}
        override.write_text(json.dumps(override_data))
        up()
        upgraded = request(base, "/films/film_" + "a" * 32 + "/profile-state")
        assert upgraded["rating"] == 5 and upgraded["notes"] == "upgrade sentinel"
        assert request(base, "/profile/cinema-dna")["totals"]["watched_films"] == 1
        compose("run", "--rm", "--no-deps", "-T", "backend", "python", "-m", "app.projections", "verify")
        python("""from pathlib import Path
from app.migrations.restore import verify_backup_manifest
manifests = list(Path('data/backups').rglob('*.manifest.json'))
assert any(verify_backup_manifest(path).source_schema_version == 4 for path in manifests)
""")
        evidence["checks"].append("v4-to-v5 container startup upgrade, verified automatic backup, personal records and projections preserved")
        evidence["status"] = "passed"
    finally:
        try:
            compose("down", "--remove-orphans")
        finally:
            log.close()
    (output / "acceptance.json").write_text(json.dumps(evidence, indent=2) + "\n")
    print(f"RC smoke passed: {output / 'acceptance.json'}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", required=True, type=Path)
    parser.add_argument("--platform", required=True, choices=sorted(PLATFORMS))
    parser.add_argument("--output", required=True, type=Path, help="New directory for synthetic fixtures and acceptance evidence")
    args = parser.parse_args()
    try:
        smoke(args)
    except (ReleaseError, OSError, ValueError, KeyError, AssertionError, subprocess.SubprocessError) as exc:
        print(f"RC smoke failed: {exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
