"""Verify a browser-downloaded synthetic backup in a fresh, offline environment."""
import asyncio
import json
import os
import sqlite3
import sys
import zipfile
from contextlib import closing, redirect_stdout
from io import StringIO
from pathlib import Path

root = Path(os.environ['E2E_ROOT']).resolve()
assert root.name.startswith('5x49-e2e-') and (root / '.owned').is_file()
package = Path(sys.argv[1]).resolve()
assert package.is_relative_to(root)
destination = root / 'restore-probe'
destination.mkdir()
target = destination / 'fresh.db'
os.environ['SQLITE_DB_PATH'] = str(target)
os.environ['WATCH_LIBRARY'] = 'false'
os.environ['TMDB_API_KEY'] = ''
os.environ['OPENROUTER_API_KEY'] = ''
os.environ['PYTHON_DOTENV_DISABLED'] = '1'
with zipfile.ZipFile(package) as archive:
    assert len(archive.namelist()) == 3
    for name in archive.namelist():
        assert Path(name).name == name and '/' not in name and '\\' not in name
        content = archive.read(name)
        for canary in (b'E2E-CONFIG-CREDENTIAL-CANARY', b'E2E-HISTORICAL-TOKEN-CANARY'):
            assert canary not in content
    archive.extractall(destination)

from app.database import create_db_and_tables, engine
from app.migrations.restore import main as restore_cli
from app.migrations.backup import inspect_database
create_db_and_tables()
engine.dispose()
manifest = next(destination.glob('*.manifest.json'))
with redirect_stdout(StringIO()):
    assert restore_cli(['--manifest', str(manifest)]) == 0
    assert restore_cli(['--manifest', str(manifest), '--replace', '--target', str(target),
                       '--confirm-current-sha256', inspect_database(target).sha256]) == 0

# Boot the actual application against only the restored database. Every job
# execution is intercepted as a failing assertion; no synthetic reset is needed.
from app.main import app, lifespan
from app.jobs import job_runtime
executions = []
job_runtime._execute = lambda job: executions.append(job['id'])
async def boot():
    async with lifespan(app):
        await asyncio.sleep(1.2)
asyncio.run(boot())
assert not executions
with closing(sqlite3.connect(target)) as db:
    assert db.execute('PRAGMA foreign_key_check').fetchall() == []
    assert db.execute('SELECT COUNT(*) FROM setting').fetchone()[0] == 0
    assert json.loads(db.execute('SELECT "values" FROM film_metadata_override WHERE film_id=?', (sys.argv[2],)).fetchone()[0]) == {'title': 'Backup Manual Title', 'year': None}
    assert db.execute('SELECT rating,notes FROM film_profile_state WHERE film_id=?', (sys.argv[2],)).fetchone() == (3, 'Backup Film review')
    assert db.execute('SELECT rating,notes,watched_at_precision FROM viewing WHERE film_id=?', (sys.argv[2],)).fetchone() == (5, 'Backup Viewing review', 'year')
print(json.dumps({'restored': True, 'actual_application_boot': True, 'jobs_executed': len(executions), 'credential_canaries_absent': True}))
