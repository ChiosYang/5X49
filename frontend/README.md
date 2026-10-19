# 5X49 Frontend

Next.js 16 / React 19 frontend for 5X49. Use npm and the committed
`package-lock.json`; do not substitute another package manager.

## Development

Start the backend on `http://127.0.0.1:8000`, then run:

```bash
npm install
npm run dev
```

The frontend listens on `http://127.0.0.1:5549`. Development defaults to the
local backend above. Set `BACKEND_URL` only when the backend is elsewhere.

## Verification

```bash
npm run test:unit
npm run lint
npm run typecheck
npm run build
```

See the repository [README](../README.md) for Docker deployment and first-run
media setup.

## Dependency security

The Next.js ESLint plugin's `fast-glob` dependency is overridden with
`tinyglobby@0.2.17` to remove the vulnerable `braces` dependency chain. The
override is scoped to plugin version 16.3.8 and preserves its `globSync`
directory lookup. The ESLint config loads a local adapter that asks this scoped
alias for absolute directory paths. This avoids malformed paths when the working
directory and matched roots are on different Windows drives; it does not patch
installed files or change application runtime behavior. Unit tests exercise
absolute/relative root matching, directory-only filtering and the internal-link
rule. Recheck the override and adapter when upgrading Next.js. Keep `source-map-js`
at the patched version 1.2.2 or newer in the lockfile.
