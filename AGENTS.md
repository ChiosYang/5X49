# 5X49 AI Coding Guide

This repository is optimized for small, reviewable AI-assisted changes. Prefer
understanding the existing structure before editing, keep diffs narrow, and run
the relevant verification commands before handing work back.

## Project Structure

- `frontend/`: Next.js 16 app using React 19, TypeScript, Tailwind CSS 4,
  next-intl, SWR, and Framer Motion.
- `backend/`: Python 3.13 FastAPI service using SQLModel, LangGraph/LangChain,
  and OpenAI/OpenRouter integrations.
- `docs/api.md`: REST API documentation. Update it when backend endpoints or
  response shapes change.
- `skills/5x49-backend/SKILL.md`: External agent skill documentation. Keep it
  in sync with backend API changes.
- `docker-compose.yml`, `docker-compose.release.yml`, `backend/Dockerfile`,
  `frontend/Dockerfile`: Container and release configuration.

## Package Managers

- Frontend: use `npm` from `frontend/`. The lockfile is
  `frontend/package-lock.json`.
- Backend: use `uv` from `backend/`. The lockfile is `backend/uv.lock`.

Do not introduce another package manager unless the task explicitly asks for it.

## Common Commands

Frontend:

```bash
cd frontend
npm install
npm run dev
npm run lint
npm run typecheck
npm run build
```

Backend:

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload
uv run python test_agent.py
```

Docker:

```bash
docker-compose up -d
```

Release:

```bash
./publish.sh
```

`publish.sh` performs Docker and Git release operations. Do not run it unless
the user explicitly asks for a release.

## Verification Expectations

- Frontend code changes: run `npm run lint`, `npm run typecheck`, and, when the
  change can affect runtime behavior or routing, `npm run build`.
- Backend API or service changes: run the smallest relevant backend check
  available. At present, this project has a manual integration-style script at
  `backend/test_agent.py`, not a formal pytest suite.
- Docker changes: run the affected Docker build or explain why it was not run.
- Documentation-only changes: no build is required unless examples or commands
  were changed in a way that should be validated.

If a command cannot be run because of missing credentials, external services, or
environment constraints, report the exact command and reason.

## Coding Rules

- Keep changes tightly scoped to the requested task.
- Preserve public API response shapes unless the task explicitly asks to change
  them.
- Do not modify `.env`, `.env.local`, media files, generated databases, or user
  data.
- Treat existing uncommitted changes as user work. Do not revert or overwrite
  them unless explicitly asked.
- Prefer existing project patterns over new abstractions.
- Add tests or focused verification when changing behavior.
- Avoid broad formatting-only rewrites.

## Frontend Guidance

- Use TypeScript and existing Next.js App Router patterns.
- Keep locale-aware routes under `frontend/src/app/[locale]/`.
- Use existing hooks in `frontend/src/hooks/` and API helpers in
  `frontend/src/lib/` when possible.
- Preserve the current dark cinematic UI direction unless the task asks for a
  design change.
- For UI changes, ensure responsive layout and avoid text overflow.

## Backend Guidance

- Use FastAPI route patterns from `backend/app/main.py`.
- Use existing services under `backend/app/services/` before adding new service
  layers.
- Validate user-controlled identifiers with existing helpers such as
  `validate_movie_id` where applicable.
- Be careful with filesystem operations under the configured media directory.
- When adding or changing endpoints, update `docs/api.md` and
  `skills/5x49-backend/SKILL.md`.

## Recommended AI Workflow

1. Inspect the relevant files and existing tests or scripts.
2. State the intended implementation approach for non-trivial changes.
3. Make the smallest useful diff.
4. Run targeted verification.
5. Review the diff for bugs, regressions, missing tests, security issues, and
   accidental unrelated changes.
6. Summarize what changed, what was verified, and any remaining risk.

For non-trivial work that is likely to span multiple sessions or contains
multiple independently verifiable behavior slices, create or update
`docs/features/<feature-slug>.md` using `docs/features/README.md`. Keep the
document focused on the behavior contract, decisions, slices, verification
evidence, and remaining risks. Do not require a feature document for small,
isolated changes. Use multi-agent workflow orchestration only when the user
explicitly requests it, including by invoking an applicable workflow Skill.

## Git Workflow

- This repository uses a single working tree at `D:/Projects/5X49`.
- Do not create or use additional Git worktrees unless the user explicitly
  requests one for a specific task.
- Perform sequential development in the main checkout. Create and switch
  ordinary feature/fix/refactor branches there when branch isolation is needed.
- Branch naming:
  - `feat/<short-topic>`
  - `fix/<short-topic>`
  - `chore/<short-topic>`
  - `docs/<short-topic>`
  - `ai/<task-topic>` for AI-assisted implementation branches
- Commit style: use Conventional Commits, for example `feat: add library scan
  status`, `fix: validate movie id`, or `docs: update api examples`.
- Pull requests should include goal, key changes, verification commands, and
  risk notes.
- Before merge, run relevant checks and perform a Codex/code-review pass focused
  on correctness, regressions, security, and missing tests.

## Cursor Cloud specific instructions

Dependencies are refreshed automatically on VM startup by the update script
(`npm --prefix frontend install` + `uv sync --project backend`). `uv` is
installed at `~/.local/bin` and is already on `PATH` (via `~/.bashrc`). The VM
has Node and `ffmpeg`; `uv` provisions Python 3.13 as pinned in
`backend/.python-version`.

Running the two dev servers (commands are in "Common Commands" above):

- Backend: `cd backend && uv run uvicorn app.main:app --reload` serves on
  port `8000` (health at `/health`, OpenAPI docs at `/docs`).
- Frontend: `cd frontend && npm run dev` serves on port `5549`.

Non-obvious caveats:

- The frontend proxies `/api/*` and `/media/*` to `BACKEND_URL` when it is set
  in either development or production. Without it, development defaults to
  `http://127.0.0.1:8000` and container builds default to `http://backend:8000`.
- Persistence is embedded SQLite (`backend/data/library.db`, auto-created, git
  ignored). There is no external database, cache, or message broker to start.
- The app boots and serves the library without any API keys. Only two features
  need secrets: AI genealogy analysis needs `OPENROUTER_API_KEY`, and TMDB
  metadata/artwork scraping needs `TMDB_API_KEY`. Browsing and scanning an
  existing NFO library work without them.
- `MEDIA_DIR` defaults to `/media`, which does not exist in the VM (the backend
  logs a warning but still starts with an empty library). To populate the
  library, point `MEDIA_DIR` (env var, or `PUT /settings/media-dir`) at a folder
  whose subfolders each contain a movie `.nfo` (TinyMediaManager/Kodi format),
  then `POST /library/scan`. `POST /library/seed` inserts sample rows without any
  media.
- There is no pytest suite. `backend/test_agent.py` is a manual, LLM-driven
  integration script that requires `OPENROUTER_API_KEY`.
