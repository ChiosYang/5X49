# 5X49 Backend

Python 3.13 FastAPI backend for the local Film Library. Dependencies are managed
with uv and the committed `uv.lock`.

## Development

```bash
uv sync
uv run uvicorn app.main:app --reload
```

The API listens on `http://127.0.0.1:8000`; OpenAPI is available at
`http://127.0.0.1:8000/docs`. Local scanning and Library browsing do not require
TMDB or OpenRouter credentials.

## Focused API Verification

```bash
uv run python -m unittest test_api_routes.ApiRouteContractTests
```

See [docs/api.md](../docs/api.md) for the public API contract and the repository
[README](../README.md) for complete development and Docker instructions.
