# Playwright MCP Browser Agent

This project can use Playwright MCP as a browser-side verification agent for
frontend work. The MCP server opens a real Chromium browser, exposes page
snapshots and actions to the coding agent, and stores screenshots or session
artifacts under `.mcp-artifacts/playwright`.

## Configuration

The repository includes:

- `.mcp.json`: project-level MCP server definition for MCP clients that read it.
- `mcp/playwright.config.json`: shared Playwright MCP runtime configuration.

The default profile is isolated, so browser state is not persisted between
sessions. This avoids accidentally reusing personal cookies while keeping the
workflow suitable for local UI checks.

Generated browser evidence should stay under the MCP artifact directory:

```text
.mcp-artifacts/playwright/
  screenshots/
  page-*.yml
  console-*.log
  network-*.log
```

## Codex CLI

Register the server once from the repository root:

```bash
codex mcp add playwright -- npx -y @playwright/mcp@latest --config mcp/playwright.config.json
```

Then restart Codex so the `playwright` MCP tools are available in the next
session.

If your MCP client launches commands outside the repository root, replace the
relative config path with an absolute path:

```bash
codex mcp add playwright -- npx -y @playwright/mcp@latest --config /Users/alicolia/Projects/agent-test/mcp/playwright.config.json
```

## IDE Clients

For VS Code, Cursor, Windsurf, or another MCP-aware IDE, either use `.mcp.json`
if the client supports project-level MCP discovery, or add this server manually
to the IDE's MCP settings:

```json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": [
        "-y",
        "@playwright/mcp@latest",
        "--config",
        "${workspaceFolder}/mcp/playwright.config.json"
      ]
    }
  }
}
```

## Local Verification Workflow

Start the app first:

```bash
cd backend
uv run uvicorn app.main:app --reload
```

```bash
cd frontend
npm run dev
```

Then ask the coding agent to use Playwright MCP for a browser check. Example:

```text
Use the Playwright MCP browser agent to verify /zh/library:
1. Open http://localhost:3000/zh/library.
2. Confirm the library refresh icon is visible in the header summary.
3. Click the icon and confirm it sends a request to /api/library/reconcile.
4. Confirm the button enters a loading/disabled state while the request is pending.
5. Capture screenshots under .mcp-artifacts/playwright/screenshots/ and report console or network errors.
```

For frontend UI changes, keep the normal project checks as the baseline:

```bash
cd frontend
npm run lint
npm run typecheck
npm run build
```

Use Playwright MCP as browser-level evidence on top of those checks, not as a
replacement for TypeScript, linting, or production builds.
