---
name: 5x49-frontend
description: Frontend implementation workflow for the 5X49 Next.js app. Use when Codex works on frontend pages, components, hooks, API client calls, next-intl locale routes, Tailwind CSS styling, Framer Motion interactions, responsive layout fixes, or frontend verification in frontend/.
---

# 5X49 Frontend

Use this skill for changes under `frontend/`.

## Workflow

1. Inspect the existing page/component/hook and nearby patterns before editing.
2. Keep locale-aware routes under `frontend/src/app/[locale]/`.
3. Reuse existing hooks from `frontend/src/hooks/` and API helpers from `frontend/src/lib/` before adding new data access code.
4. Preserve the current dark cinematic UI direction unless the user asks for a design change.
5. Keep changes narrow and avoid broad formatting-only rewrites.
6. Verify responsive behavior for UI changes and avoid text overflow.

## Project Patterns

- Use TypeScript and existing Next.js App Router conventions.
- Prefer SWR and existing hooks for data fetching.
- Keep API URL and fetch behavior aligned with existing helpers.
- Use Tailwind CSS 4 classes consistently with nearby components.
- Use client components only where interactivity, browser APIs, hooks, or Framer Motion require them.
- Keep visible copy locale-aware when editing routed UI under `[locale]`.

## Verification

For frontend source changes, run from `frontend/`:

```bash
npm run lint
npm run typecheck
```

Also run this when routing, build-time behavior, metadata, imports, or runtime rendering may be affected:

```bash
npm run build
```

If verification cannot run because of missing dependencies, environment constraints, or external services, report the exact command and reason.

## Browser Verification

When Playwright MCP is available, use it for browser-level checks after UI
changes that affect interaction, layout, or responsive behavior. See
`docs/playwright-mcp.md` for the project MCP configuration and recommended
verification prompts. Treat browser checks as additional evidence on top of
`npm run lint`, `npm run typecheck`, and `npm run build` when those commands
apply.
