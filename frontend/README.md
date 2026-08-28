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
