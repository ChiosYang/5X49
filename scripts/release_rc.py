#!/usr/bin/env python3
"""Build a committed RC as OCI archives, or explicitly publish digest-pinned images."""

import argparse
import hashlib
import json
import re
import subprocess
import tarfile
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLATFORMS = {"linux/amd64", "linux/arm64"}
BASE_IMAGES = {
    "PYTHON_IMAGE": "python:3.13-slim",
    "UV_IMAGE": "ghcr.io/astral-sh/uv:latest",
    "NODE_IMAGE": "node:20-alpine",
}
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")


class ReleaseError(RuntimeError):
    pass


def run(args, *, cwd=ROOT, capture=True):
    result = subprocess.run(args, cwd=cwd, text=True, capture_output=capture)
    if result.returncode:
        # Docker errors can include signed registry URLs. Keep them out of records.
        raise ReleaseError(f"{args[0]} {args[1]} failed (exit {result.returncode})")
    return result.stdout if capture else ""


def validate_version(value):
    if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{0,79}", value) or not re.search(r"(^|[.-])rc([.-]|$)", value):
        raise ReleaseError("Version must be an RC tag, e.g. 0.1.0-rc.1; stable/latest tags are refused")
    return value


def validate_repository(value):
    if not re.fullmatch(r"(?:[a-z0-9][a-z0-9.-]*(?::[0-9]+)?/)?[a-z0-9][a-z0-9._/-]*", value):
        raise ReleaseError("Repository must be a lowercase image prefix without a tag or digest")
    return value


def inspect_digest(reference):
    description = run(["docker", "buildx", "imagetools", "inspect", reference])
    match = re.search(r"^Digest:\s+(sha256:[0-9a-f]{64})\s*$", description, re.MULTILINE)
    if not match:
        raise ReleaseError("Registry did not return an image digest")
    return match[1]


def require_platforms(manifest, expected):
    actual = {
        f"{item.get('platform', {}).get('os')}/{item.get('platform', {}).get('architecture')}"
        for item in manifest.get("manifests", [])
    }
    if not expected <= actual:
        raise ReleaseError(f"Image index is missing platforms: {', '.join(sorted(expected - actual))}")


def resolve_bases(lock_path):
    if lock_path:
        bases = json.loads(lock_path.read_text(encoding="utf-8"))["base_images"]
    else:
        bases = {name: f"{reference}@{inspect_digest(reference)}" for name, reference in BASE_IMAGES.items()}
    if set(bases) != set(BASE_IMAGES) or any(
        not isinstance(value, str) or not re.fullmatch(r"[a-z0-9][a-z0-9./:_-]*@sha256:[0-9a-f]{64}", value)
        for value in bases.values()
    ):
        raise ReleaseError("Base lock must contain all three digest-pinned base images")
    return bases


def require_unused_tag(reference):
    result = subprocess.run(
        ["docker", "buildx", "imagetools", "inspect", reference],
        text=True, capture_output=True,
    )
    if result.returncode == 0:
        raise ReleaseError(f"RC tag already exists: {reference}; choose a new RC version")
    if not re.search(r"manifest unknown|manifest_unknown|^ERROR: \S+: not found\s*$", result.stderr, re.IGNORECASE | re.MULTILINE):
        raise ReleaseError("Cannot confirm RC tag is absent; check registry access before publishing")


def build_command(service, context, output, tag, bases, revision, platforms, builder, push):
    command = ["docker", "buildx", "build", "--platform", ",".join(sorted(platforms)),
               "--tag", tag, "--metadata-file", str(output / f"{service}.metadata.json"),
               "--label", f"org.opencontainers.image.revision={revision}",
               "--label", f"org.opencontainers.image.version={tag.rsplit(':', 1)[1]}",
               "--provenance=mode=min", "--progress=plain"]
    if builder:
        command += ["--builder", builder]
    for name in (("PYTHON_IMAGE", "UV_IMAGE") if service == "backend" else ("NODE_IMAGE",)):
        command += ["--build-arg", f"{name}={bases[name]}"]
    command += ["--push"] if push else ["--output", f"type=oci,dest={output / (service + '.oci.tar')}"]
    return command + [str(context / service)]


def verify_oci(path, digest, platforms):
    with tarfile.open(path) as archive:
        index = json.load(archive.extractfile("index.json"))
        descriptor = next((item for item in index["manifests"] if item["digest"] == digest), None)
        if descriptor is None:
            raise ReleaseError("OCI archive does not contain the reported build digest")
        data = archive.extractfile("blobs/sha256/" + digest.split(":")[1]).read()
        if "sha256:" + hashlib.sha256(data).hexdigest() != digest:
            raise ReleaseError("OCI image index digest mismatch")
        require_platforms(json.loads(data), platforms)


def release(args):
    version = validate_version(args.version)
    repository = validate_repository(args.repository)
    platforms = set(args.platforms.split(","))
    if platforms != PLATFORMS:
        raise ReleaseError("RC distribution requires linux/amd64,linux/arm64")
    revision = run(["git", "rev-parse", "--verify", "--end-of-options", args.revision + "^{commit}"]).strip()
    tag_suffix = f"{version}-{revision[:12]}"
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise ReleaseError("Output directory must be new or empty; previous evidence is never overwritten")
    if "," in str(output):
        raise ReleaseError("Output directory cannot contain a comma (Buildx exporter syntax)")
    output.mkdir(parents=True, exist_ok=True)
    bases = resolve_bases(args.base_lock)
    tags = {service: f"{repository}-{service}:{tag_suffix}" for service in ("backend", "frontend")}
    if args.push:
        for tag in tags.values():
            require_unused_tag(tag)
    record = {"source_revision": revision, "version": tag_suffix, "platforms": sorted(platforms),
              "base_images": bases, "distribution": "registry" if args.push else "oci", "images": {}}
    # This records intent/inputs even if the second build fails; it is not a release record.
    (output / "build-inputs.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="5x49-rc-source-") as temporary:
        context = Path(temporary)
        source_archive = context / "source.tar"
        run(["git", "archive", "--format=tar", f"--output={source_archive}", revision, "backend", "frontend"])
        with tarfile.open(source_archive) as archive:
            archive.extractall(context, filter="data")
        # Refuse old revisions that cannot consume the pinned build arguments.
        for service, names in (("backend", ("PYTHON_IMAGE", "UV_IMAGE")), ("frontend", ("NODE_IMAGE",))):
            dockerfile = (context / service / "Dockerfile").read_text(encoding="utf-8")
            if any(f"ARG {name}=" not in dockerfile for name in names):
                raise ReleaseError("Source revision predates RC base-image pinning support")
            run(build_command(service, context, output, tags[service], bases, revision, platforms, args.builder, args.push), capture=False)
            metadata = json.loads((output / f"{service}.metadata.json").read_text(encoding="utf-8"))
            digest = metadata.get("containerimage.digest", "")
            if not DIGEST.fullmatch(digest):
                raise ReleaseError("Build did not return a valid image digest")
            reference = f"{repository}-{service}@{digest}"
            if args.push:
                if inspect_digest(tags[service]) != digest:
                    raise ReleaseError("Published tag does not match build output")
                manifest = json.loads(run(["docker", "buildx", "imagetools", "inspect", "--raw", reference]))
                require_platforms(manifest, platforms)
            else:
                verify_oci(output / f"{service}.oci.tar", digest, platforms)
            record["images"][service] = {"tag": tags[service], "digest": digest, "reference": reference}
    if args.push:
        (output / "rc-images.env").write_text(
            "# Image identities only. Keep local settings/credentials in a separate file.\n"
            + "".join(f"{service.upper()}_IMAGE={record['images'][service]['reference']}\n" for service in tags),
            encoding="utf-8",
        )
    (output / "release.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(f"RC artifacts verified: {output / 'release.json'}")
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True, help="RC version, e.g. 0.1.0-rc.1")
    parser.add_argument("--revision", default="HEAD", help="Committed source revision (working files are excluded)")
    parser.add_argument("--repository", default="alicolia/5x49", help="Image prefix, without -backend/-frontend")
    parser.add_argument("--output", required=True, type=Path, help="New or empty artifact directory")
    parser.add_argument("--base-lock", type=Path, help="Previous build-inputs.json or release.json to reuse pinned bases")
    parser.add_argument("--platforms", default="linux/amd64,linux/arm64")
    parser.add_argument("--builder", help="Existing multi-platform Buildx builder; global selection is unchanged")
    parser.add_argument("--push", action="store_true", help="Explicitly publish to registry; otherwise write local OCI archives")
    try:
        release(parser.parse_args(argv))
    except (ReleaseError, OSError, ValueError, KeyError, tarfile.TarError) as exc:
        print(f"RC build refused: {exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
