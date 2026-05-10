---
name: 5x49-api-docs
description: API change and documentation workflow for the 5X49 FastAPI backend and frontend clients. Use when Codex adds, removes, or changes backend endpoints, request parameters, response shapes, status behavior, frontend API helpers, docs/api.md, or skills/5x49-backend/SKILL.md.
---

# 5X49 API Docs

Use this skill when an API surface or its consumers may change.

## Workflow

1. Inspect `backend/app/main.py`, related services under `backend/app/services/`, frontend callers under `frontend/src/`, `docs/api.md`, and `skills/5x49-backend/SKILL.md`.
2. Preserve public response shapes unless the task explicitly asks to change them.
3. Validate user-controlled identifiers with existing helpers such as `validate_movie_id` where applicable.
4. Update frontend API helpers or hooks when endpoint paths, query parameters, or response fields change.
5. Update `docs/api.md` and `skills/5x49-backend/SKILL.md` in the same task for endpoint or response-shape changes.
6. Include examples that match the implemented behavior.

## Documentation Checklist

- Method and path are correct.
- Path and query parameters are listed with realistic examples.
- Request body shape is documented when present.
- Response shape matches implementation.
- Background/SSE behavior is called out when relevant.
- Error behavior is documented when it is part of the public contract.
- `skills/5x49-backend/SKILL.md` stays concise and useful for agent/API callers.

## Verification

For backend API or service changes, run the smallest relevant backend check from `backend/`, usually:

```bash
uv run python test_agent.py
```

For frontend client changes caused by API edits, also run from `frontend/`:

```bash
npm run lint
npm run typecheck
```

If a command cannot run, report the exact command and reason.
