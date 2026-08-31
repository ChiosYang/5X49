# 🎬 5X49

[English](README.md) | [简体中文](README.zh-CN.md)

> A local-first Film Library manager and cinematic genealogy explorer.

![Library](docs/images/library_grid.png)

5X49 scans local Film folders and NFO metadata and presents the collection in a
cinematic dark interface. Optional TMDB integration enriches metadata and
artwork; optional OpenRouter integration generates Film genealogy analysis.

## Highlights

- Scan TinyMediaManager/Kodi-style Film folders and NFO files.
- Manage Film editions, watch state, favorites, metadata, and artwork.
- Observe background scan, organization, and scraping workflows.
- Analyze themes, styles, and Film-history relationships with an optional LLM.
- Integrate through the FastAPI REST interface documented in [docs/api.md](docs/api.md).

## Quick Start: Published Images

Published Docker images are the recommended path for regular users. This flow
does not build source code from the current checkout.

### Requirements

- Docker Desktop or Docker Engine
- Docker Compose v2 (`docker compose`)
- A directory for local Films; no API key is required to start

### 1. Get the deployment files

```bash
git clone https://github.com/ChiosYang/5X49.git
cd 5X49
cp .env.example .env
```

PowerShell:

```powershell
Copy-Item .env.example .env
```

Edit the host media directory in `.env`. The default `./media` is suitable for
an empty trial installation:

```dotenv
MEDIA_DIR=./media
TMDB_API_KEY=
OPENROUTER_API_KEY=
```

Linux/NAS users can use an absolute path such as `/volume1/video/movies`.
Windows Docker Desktop accepts a path such as `D:/Movies`. Compose mounts this
host directory as `/media` inside the backend container.

In a Bash environment, the optional interactive script validates a custom
directory or creates the default `./media` directory:

```bash
./setup.sh
```

### 2. Start 5X49

```bash
docker compose up -d
```

- Frontend: [http://localhost:5549](http://localhost:5549)
- Backend API: [http://localhost:11548](http://localhost:11548)
- OpenAPI: [http://localhost:11548/docs](http://localhost:11548/docs)

### 3. Complete the first scan

An empty Library opens an inline first-run guide:

1. Keep the container path `/media` for Docker; use an absolute Film path for local development.
2. Confirm that the directory is reported as existing and readable.
3. Select **Start First Scan** and wait for completion.
4. The Library refreshes automatically when Films are found.

Each Film belongs in a first-level folder below the media root:

```text
Movies/
└── Film Title (2024)/
    ├── Film Title (2024).mkv
    └── movie.nfo  # optional
```

Supported video types are MP4, MKV, AVI, MOV, WMV, M4V, TS, and ISO. Videos
placed directly in the media root can be organized from Library Management.

## Optional Integrations

| Setting | Required | Enables |
| --- | --- | --- |
| `TMDB_API_KEY` | No | Online matching, metadata/artwork scraping, and NFO generation |
| `OPENROUTER_API_KEY` | No | AI Film genealogy analysis and model-catalog refresh |

Without keys, local scanning, Library browsing, watch state, Activity, and
SQLite persistence remain available. A TMDB key can be added later in Settings;
the OpenRouter key is supplied through the environment.

## Common Docker Operations

```bash
docker compose ps
docker compose logs -f backend frontend
docker compose restart
docker compose down
```

The `backend_data` volume stores the database and settings. Do not run
`docker compose down -v` when that data must be preserved.

See [README.docker.md](README.docker.md) for additional deployment guidance.

## Source Development

Install Node.js 20, Python 3.13, and [uv](https://docs.astral.sh/uv/). TMDB and
OpenRouter keys are not required for the base application.

Backend:

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload
```

The backend listens on `http://127.0.0.1:8000`.

Frontend, in another terminal:

```bash
cd frontend
npm install
npm run dev
```

The frontend listens on `http://127.0.0.1:5549` and proxies to the development
backend at `http://127.0.0.1:8000` by default.

Frontend verification:

```bash
cd frontend
npm run test:unit
npm run lint
npm run typecheck
npm run build
```

Backend tests use `unittest`; run the smallest relevant module, for example:

```bash
cd backend
uv run python -m unittest test_api_routes.ApiRouteContractTests
```

## First-run Troubleshooting

- Backend unavailable: run `docker compose ps` and `docker compose logs backend`.
- `/media` unreadable: confirm that the host `MEDIA_DIR` exists and Docker can access it.
- Zero Films found: verify the first-level folder layout and supported video/NFO files.
- TMDB/AI actions unavailable: this is expected without the relevant optional key.

## Repository Layout

- `frontend/`: Next.js 16, React 19, TypeScript, and Tailwind CSS.
- `backend/`: Python 3.13, FastAPI, SQLModel, and OpenAI-powered Analysis V2.
- `docs/`: API, domain, installation-baseline, and feature documentation.

*Crafted with 🖤 for film lovers.*
