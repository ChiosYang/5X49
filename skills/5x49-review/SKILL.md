---
name: 5x49-review
description: Code review workflow for 5X49 repository diffs, commits, and PR-ready changes. Use when Codex is asked to review current changes, inspect git diff, assess a plan or PR, find bugs, check regressions, evaluate security risk, or identify missing tests/documentation.
---

# 5X49 Review

Use this skill in review mode. Prioritize findings over summaries.

## Review Stance

1. Inspect the relevant diff or files before commenting.
2. Lead with bugs, regressions, security issues, API incompatibilities, and missing verification.
3. Order findings by severity.
4. Cite concrete files and line numbers when possible.
5. Keep style preferences secondary unless they hide real risk.
6. Do not modify files during a pure review unless the user asks for fixes.

## Project-Specific Checks

- Backend endpoint or response-shape changes must update `docs/api.md` and `skills/5x49-backend/SKILL.md`.
- Frontend source changes should have `npm run lint` and `npm run typecheck`; routing/runtime changes usually need `npm run build`.
- Backend app changes should run the smallest relevant backend check, usually `uv run python test_agent.py`.
- Docker changes should run the affected Docker build or explain why not.
- `.env`, `.env.local`, media files, generated databases, and user data should not be modified.
- Existing uncommitted changes may be user work; do not recommend reverting unrelated changes casually.
- File-system operations under media directories need careful path validation.

## Output Format

Start with findings. If there are no findings, say so clearly and mention residual test gaps or risks.

Use this order:

1. Findings
2. Open questions or assumptions
3. Brief change summary, only if useful
4. Verification gaps

Keep the answer concise and grounded in observed code.
