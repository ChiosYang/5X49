# Small local fixture

This directory contains 12 compact, model-compatible movie records and six
user-state records for API and frontend checks. It intentionally contains no
database, image, or video files.

For a temporary media tree with valid NFO, missing NFO, corrupt XML, duplicate
versions, special paths, and root-video cases, run from `backend/`:

```powershell
uv run python scripts/generate_test_data.py --count 12 --seed 549 --output-dir data/generated-test-data
```

The generated directory is gitignored. Remove only that exact generator-owned
directory with:

```powershell
uv run python scripts/generate_test_data.py --clean --output-dir data/generated-test-data
```
