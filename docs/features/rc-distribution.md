# RC distribution and installation acceptance

Status: In Progress
Last updated: 2026-10-01
Related: W12 / Gate E; rc-stabilization

## Goal

Tie an installable RC to an exact source commit and image digests, then verify
the actual artifacts with isolated data on Linux AMD64 and ARM64.

## Scope

- RC-only publication without moving `latest` or creating/pushing Git tags.
- Committed source archives, locked application dependencies, pinned base images,
  build metadata, multi-platform outputs and digest-based deployment.
- Fresh installation, restart, upgrade and backup/restore acceptance.

## Non-goals

- Public Beta opening, recruitment, Gate B/C/D or real-user retention evidence.
- Bit-identical rebuilds: distro package repositories remain time-dependent.
- Changes to production installations, user data or the stable release flow.

## Decisions

- Sequential work in the existing checkout on `ai/rc-distribution`, based on
  `3d1180e`; no additional worktree.
- Build only an explicit committed source revision, never the working directory.
- Default to local OCI archives; registry writes require `--push` or `publish.sh --rc`.
- Produce deployment references only after both images and their platform manifests
  are verified. Partial publication must not produce a successful release record.
- Exercise registry distribution using a disposable loopback-only registry;
  public registry publication remains a separate operator action.

## Acceptance criteria

- [ ] RC tag validation excludes stable/latest tags; no Git mutation in release tooling.
- [ ] Build records bind source, base image digests, output digests and architectures.
- [ ] Release Compose supports fixed image references and isolated installations.
- [ ] Tests cover invalid inputs, partial failures and digest/platform checks.
- [ ] AMD64 and ARM64 images build and pass installation/recovery smoke.
- [ ] Operator guidance and readiness evidence match observed results.

## Slices

1. RC packaging and deployment contract — In Progress.
2. Script regression and actual multi-platform artifacts — Pending.
3. Isolated install/upgrade/recovery and operator handoff — Pending.

## Verification evidence

- Baseline `main` clean at `3d1180e`; Docker 28.5.2 and buildx available.
- Existing builder advertises AMD64 and ARM64 support.

## Remaining risks

- Native Windows/NAS permissions and performance need target-host evidence.
- No public registry credentials or real application data are used in acceptance.
