# RC distribution and installation acceptance

Status: Done
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

- [x] RC tag validation excludes stable/latest tags; no Git mutation in release tooling.
- [x] Build records bind source, base image digests, output digests and architectures.
- [x] Release Compose supports fixed image references and isolated installations.
- [x] Tests cover invalid inputs, partial failures and digest/platform checks.
- [x] AMD64 and ARM64 images build and pass installation/recovery smoke.
- [x] Operator guidance and readiness evidence match observed results.

## Slices

1. RC packaging and deployment contract — Complete.
2. Script regression and actual multi-platform artifacts — Complete.
3. Isolated install/upgrade/recovery and operator handoff — Complete.

## Verification evidence

- Baseline `main` clean at `3d1180e`; Docker 28.5.2 and buildx available.
- Existing builder advertises AMD64 and ARM64 support.
- `uv run --project backend --locked python -m unittest discover -s scripts -p 'test_*.py' -q`
  — 11 passed. Covers tag/input refusal, partial build and registry drift, OCI
  digest checks, platform selection and resolved Compose isolation defaults.
- `bash -n publish.sh`, Python module compilation and `git diff --check` passed.
- Source image revision: `50e7125442175f5df251d3af4998d1d68246723d`.
  Later changes affect acceptance tooling/tests/docs, not either image context.
- `uv run --project backend --locked python scripts/release_rc.py --version 0.1.0-rc.1 --revision 50e7125 --repository 127.0.0.1:15000/5x49 --builder rc-5x49-qn096y --base-lock /private/tmp/5x49-rc-dist-qn096Y/base-lock.json --output /private/tmp/5x49-rc-dist-qn096Y/published --push`
  — both Dockerfiles built for AMD64/ARM64, pushed only to the disposable local
  registry, verified by output digest/platform index. No public registry write.
- Same build command without `--push`, with output directory
  `/private/tmp/5x49-rc-dist-qn096Y/oci` — both OCI archives and their index
  digests/platforms verified. No deployment env file generated in local mode.
- Repeating the published RC/version/source with a new output directory refused
  at the existing-tag check (exit 2), before any rebuild or upload.
- Final registry index digests:
  - backend: `sha256:fb1f4e821bdf207a58ac2da332a3a8b16669676364c107542fcabe1291323c18`
  - frontend: `sha256:e44684fa9463b903b237dc350fbc686c440043243df24cfca9e54c46a8fb52ff`
- `uv run --project backend --locked python scripts/smoke_rc.py --release /private/tmp/5x49-rc-dist-qn096Y/published/release.json --platform linux/amd64 --output /private/tmp/5x49-rc-dist-qn096Y/smoke-amd64-v2`
  and the equivalent ARM64 command using `smoke-arm64-v2` — passed. They pulled
  exact architecture manifests, checked source labels, and exercised fresh
  installation/proxy, no-key read-only scans, reconciliation, personal state,
  Viewing, DNA, Ask, localized pages, restart, verified backup/offline restore,
  eight projection families and a separate v4→v5 startup upgrade with verified
  pre-upgrade backup. Synthetic media hashes remained unchanged.
- Engine: `linux/aarch64`; ARM64 ran natively, AMD64 through cross-architecture
  emulation. The final tests overlapped using distinct projects, data and ports.
  Acceptance JSON records both parent index and installed child-manifest digests.
- First cross-architecture pull exposed classic Docker's `cannot overwrite
  digest` limitation when reusing an index reference. Fixed by selecting a
  verified architecture-specific child manifest, with regression coverage;
  both final runs passed. Initial Docker Hub EOF errors resolved on retry.
- Test services/networks were removed by the smoke tool. Artifacts, synthetic
  backups and logs are under `/private/tmp/5x49-rc-dist-qn096Y`; these local
  registry references are acceptance fixtures, not publicly installable tags.
- Temporary registry container and task Buildx builder were removed after
  verification. The pre-existing selected `multi-arch-builder` is unchanged.
- Final review covered committed-only build inputs, argument handling, partial
  publication, digest checks, architecture identity, Compose isolation, failure
  cleanup, and separation of synthetic acceptance from real-user product gates.

## Remaining risks

- Native Windows/NAS permissions and performance need target-host evidence.
- AMD64 emulation does not certify native AMD64 host performance or permissions.
- Public registry authentication/publication and its resulting distributed
  digests must be verified when a public release is explicitly performed.
- No real application data is used in acceptance. Gate B/C/D, recruitment and
  Public Beta opening remain separate decisions.
