# 5X49 Feature Documents

Feature documents preserve the execution state of non-trivial changes across
Codex tasks and chat sessions. They complement `docs/product-spec.md` and
`docs/product-roadmap.md`; they do not replace product-level documentation or
Git history.

Create `docs/features/<feature-slug>.md` when work is likely to span multiple
sessions, crosses frontend and backend boundaries, changes an API or persistent
state, requires a meaningful UI or architecture decision, or contains multiple
independently verifiable behavior slices.

Do not create one for a small isolated fix, copy-only edit, local style change,
or other low-risk task that can be implemented and verified in one pass.

## Lifecycle

Use one of these statuses:

- `Draft`: scope or acceptance criteria are still being shaped.
- `In Progress`: implementation has started.
- `Blocked`: progress requires a decision or external dependency.
- `Done`: acceptance criteria and required verification are complete.
- `Superseded`: another document or decision replaced this plan.

Update the document when scope, decisions, slice status, verification evidence,
or known risks change. Record only checks that were actually run. Keep detailed
command output in the task or CI logs rather than copying it into the document.

## Template

```md
# <Feature Name>

Status: Draft
Last updated: YYYY-MM-DD
Related: <issue, product spec section, roadmap item, or none>

## Goal

Describe the user-visible or operational outcome.

## Scope

- Included behavior.

## Non-goals

- Explicitly excluded behavior.

## Existing behavior

Summarize the relevant current behavior and implementation constraints.

## Acceptance criteria

- [ ] Observable outcome.

## Decisions

- Decision and short rationale.

## Open questions

- Unresolved question, owner, or required evidence.

## Slices

### Slice 1 — <name>

Status: Pending

- Intended behavior:
- Likely affected areas:
- Dependencies:
- Verification:

## Verification evidence

- `<exact command>` — <result>
- Manual or browser check — <observed result>

## Remaining risks

- Known issue, unverified area, or `None known`.
```

Prefer the smallest number of slices that keeps behavior understandable and
verifiable. If implementation shows that the plan or acceptance criteria are
wrong, update the feature document before expanding the change.
