# RC packaging and fixed-image installation

RC artifacts are built from one committed revision. The RC path never updates
`latest`, creates Git tags, or runs the stable release flow. Use Docker Engine,
Compose v2, a multi-platform Buildx builder, Git and the project's `uv` runtime.
Run commands from the repository root.

## Build or publish an RC

Commit the intended source first: working files, local settings and databases
are excluded by `git archive`. The source must include RC base-image arguments.

Build AMD64 and ARM64 OCI archives without publishing:

```sh
uv run --project backend --locked python scripts/release_rc.py \
  --version 0.1.0-rc.1 --revision HEAD \
  --builder multi-arch-builder --output /tmp/5x49-rc-artifacts
```

Choose a new empty output directory and an existing builder from
`docker buildx ls`. The script does not change the globally selected builder.
Docker's classic image store cannot load a multi-platform OCI archive directly;
use registry publication for the installation flow below.

When registry publication is intended, authenticate to the chosen registry with
Docker first, then explicitly publish:

```sh
./publish.sh --rc 0.1.0-rc.1 --revision HEAD \
  --repository alicolia/5x49 --builder multi-arch-builder \
  --output /tmp/5x49-rc-published
```

On Windows, or without Bash, use the same Python command with `--push`.
The image tag includes the RC version and twelve-character commit suffix.
Existing tags are refused; authentication/network failures fail closed. Use a
new RC version after a partial publication. Registry tag creation is not atomic
across images; coordinate publishers and use registry tag immutability where
available. Never infer a completed release from only one uploaded image.

Outputs:

- `build-inputs.json`: source SHA, resolved base-image digests and platforms.
- `backend.metadata.json`, `frontend.metadata.json`: Buildx output metadata.
- `backend.oci.tar`, `frontend.oci.tar`: local mode only.
- `release.json`: written only after both outputs and platform indexes verify.
- `rc-images.env`: registry mode only; exact `repository@sha256:...` references,
  with no credentials. Treat it as complete only alongside `release.json`.

`--base-lock /path/to/build-inputs.json` reuses pinned base images for a retry.
Application dependencies use committed lockfiles; base images are pinned during
each build. OS package repositories and build timestamps remain time-dependent,
so this is traceable packaging and reproducible artifact selection, not a claim
of byte-identical rebuilds.

## Install the verified images

Use the release Compose file with the generated image references and a separate
local settings file. Example `rc-settings.env` (operator-created, not committed):

```dotenv
MEDIA_DIR=/absolute/path/to/existing/movies
MEDIA_READ_ONLY=true
BACKEND_PORT=11548
FRONTEND_PORT=5549
TMDB_API_KEY=
OPENROUTER_API_KEY=
```

```sh
docker compose -p 5x49-alpha -f docker-compose.release.yml \
  --env-file /tmp/5x49-rc-published/rc-images.env --env-file rc-settings.env config --quiet
docker compose -p 5x49-alpha -f docker-compose.release.yml \
  --env-file /tmp/5x49-rc-published/rc-images.env --env-file rc-settings.env pull
docker compose -p 5x49-alpha -f docker-compose.release.yml \
  --env-file /tmp/5x49-rc-published/rc-images.env --env-file rc-settings.env up -d --wait
```

Unset conflicting shell `BACKEND_IMAGE`/`FRONTEND_IMAGE` variables before running;
Compose gives the shell precedence over env files. Use the same project, files
and settings for every subsequent command. Frontend: `http://localhost:5549`;
backend: `http://localhost:11548`. Both bind to loopback by default. The release
file requires explicit images and an existing media directory; it has no
fallback to `latest`, fixed container names or implicit media-folder creation.
Separate project names isolate data/networks; use different host ports for
simultaneous installations. Changing the project name starts a separate database.

Media is read-only and watching is disabled by default for controlled acceptance.
Set `MEDIA_READ_ONLY=false` or `WATCH_LIBRARY=true` only when the corresponding
workflow is intended. Provider keys are optional. Health probes check HTTP status
and the frontend proxy; they do not replace the data-path smoke or user evidence.

For upgrades, preserve the Compose project/data volume, stop writers and follow
[the backup/restore runbook](rc-operations.md) before changing the image file.
Keep the prior image references and matching verified database backup. A database
downgrade is not guaranteed merely by switching to an older image.

## Repeat installation/recovery acceptance

This command pulls exact digests and creates a unique, temporary Compose project
with empty synthetic data, read-only media and no provider keys. It never uses an
existing installation or repository `.env`. Output must be a new directory.
For each platform it resolves the verified index to that architecture's child
manifest digest. This lets classic Docker stores test both architectures without
trying to overwrite the same local index reference. Both index and installed
manifest references are recorded with the Docker engine architecture.

```sh
uv run --project backend --locked python scripts/smoke_rc.py \
  --release /tmp/5x49-rc-published/release.json --platform linux/amd64 \
  --output /tmp/5x49-rc-smoke-amd64
uv run --project backend --locked python scripts/smoke_rc.py \
  --release /tmp/5x49-rc-published/release.json --platform linux/arm64 \
  --output /tmp/5x49-rc-smoke-arm64
```

It checks architecture/source labels, fresh install, frontend proxy, repeated
scan, personal state, Viewing, DNA, Ask, restart, verified backup/offline restore
and a separate synthetic v4→v5 startup upgrade. A passed `acceptance.json` is
written only after success and container cleanup. Synthetic databases, backups
and local logs remain in the output directory for diagnosis. Logs are not
automatically uploaded. Emulated AMD64 checks must be labelled as emulation;
they do not certify native Windows/NAS permissions, performance or long-term use.

Buildx reference: [build outputs, metadata and provenance](https://docs.docker.com/reference/cli/docker/buildx/build/).
