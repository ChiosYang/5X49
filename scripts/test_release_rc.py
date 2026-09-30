import io
import json
import subprocess
import tarfile
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

import release_rc as rc


SHA = "a" * 40
DIGEST = "sha256:" + "b" * 64
BASES = {key: f"{image}@{DIGEST}" for key, image in rc.BASE_IMAGES.items()}


class ReleaseTests(unittest.TestCase):
    def test_rejects_stable_versions_and_malformed_repositories(self):
        for value in ("latest", "stable", "1.0.0", "rc;echo", "../rc", "rcevil"):
            with self.subTest(value=value), self.assertRaises(rc.ReleaseError):
                rc.validate_version(value)
        self.assertEqual(rc.validate_version("0.1.0-rc.1"), "0.1.0-rc.1")
        for value in ("owner/app:latest", "owner/app@sha256:abc", "x\nDOCKER_HOST=bad", "--flag"):
            with self.subTest(value=value), self.assertRaises(rc.ReleaseError):
                rc.validate_repository(value)
        self.assertEqual(rc.validate_repository("127.0.0.1:15000/5x49"), "127.0.0.1:15000/5x49")

    def test_platform_check_ignores_attestations_and_requires_both_architectures(self):
        manifest = {"manifests": [{"platform": {"os": "linux", "architecture": "arm64"}},
                                  {"platform": {"os": "unknown", "architecture": "unknown"}}]}
        with self.assertRaises(rc.ReleaseError):
            rc.require_platforms(manifest, rc.PLATFORMS)
        manifest["manifests"].append({"platform": {"os": "linux", "architecture": "amd64"}})
        rc.require_platforms(manifest, rc.PLATFORMS)

    def test_build_commands_pin_bases_and_only_one_rc_tag(self):
        for push in (False, True):
            command = rc.build_command("backend", Path("/source"), Path("/output"), "repo/backend:0.1-rc.1",
                                       BASES, SHA, rc.PLATFORMS, "isolated-builder", push)
            self.assertEqual(command.count("--tag"), 1)
            self.assertIn(f"PYTHON_IMAGE={BASES['PYTHON_IMAGE']}", command)
            self.assertIn(f"UV_IMAGE={BASES['UV_IMAGE']}", command)
            self.assertIn(f"org.opencontainers.image.revision={SHA}", command)
            self.assertEqual("--push" in command, push)
            self.assertNotIn("--use", command)
            self.assertNotIn("repo/backend:latest", command)

    def test_registry_errors_and_existing_tags_fail_closed(self):
        for result in (subprocess.CompletedProcess([], 0, "", ""),
                       subprocess.CompletedProcess([], 1, "", "unauthorized"),
                       subprocess.CompletedProcess([], 1, "", "connection refused")):
            with patch.object(rc.subprocess, "run", return_value=result), self.assertRaises(rc.ReleaseError):
                rc.require_unused_tag("repo:rc.1")
        with patch.object(rc.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "", "manifest unknown")):
            rc.require_unused_tag("repo:rc.1")

    def test_base_lock_rejects_unpinned_inputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "input.json"
            path.write_text(json.dumps({"base_images": rc.BASE_IMAGES}))
            with self.assertRaises(rc.ReleaseError):
                rc.resolve_bases(path)
            path.write_text(json.dumps({"base_images": BASES}))
            self.assertEqual(rc.resolve_bases(path), BASES)

    def _fake_run(self, output, *, fail_frontend=False, wrong_digest=False):
        def fake(args, **kwargs):
            if args[:2] == ["git", "rev-parse"]:
                return SHA
            if args[:2] == ["git", "archive"]:
                archive_path = Path(next(arg.split("=", 1)[1] for arg in args if arg.startswith("--output=")))
                with tarfile.open(archive_path, "w") as archive:
                    for service, content in (("backend", b"ARG PYTHON_IMAGE=x\nARG UV_IMAGE=y"),
                                             ("frontend", b"ARG NODE_IMAGE=z")):
                        entry = tarfile.TarInfo(f"{service}/Dockerfile")
                        entry.size = len(content)
                        archive.addfile(entry, io.BytesIO(content))
                return ""
            if args[:3] == ["docker", "buildx", "build"]:
                service = Path(args[-1]).name
                if service == "frontend" and fail_frontend:
                    raise rc.ReleaseError("frontend build failed")
                (output / f"{service}.metadata.json").write_text(json.dumps({"containerimage.digest": DIGEST}))
                return ""
            if "--raw" in args:
                return json.dumps({"manifests": [{"platform": {"os": "linux", "architecture": arch}}
                                                 for arch in ("amd64", "arm64")]})
            if args[:4] == ["docker", "buildx", "imagetools", "inspect"]:
                return "Digest: " + ("sha256:" + "c" * 64 if wrong_digest else DIGEST)
            raise AssertionError(args)
        return fake

    def _args(self, output):
        return Namespace(version="0.1.0-rc.1", repository="test/5x49", revision="HEAD", output=output,
                         base_lock=None, platforms="linux/amd64,linux/arm64", builder="test", push=True)

    def test_partial_build_or_registry_drift_never_emits_deployment_record(self):
        for failure in ("build", "digest"):
            with tempfile.TemporaryDirectory() as temporary:
                output = Path(temporary) / "release"
                with patch.object(rc, "resolve_bases", return_value=BASES), patch.object(rc, "require_unused_tag"), \
                     patch.object(rc, "run", side_effect=self._fake_run(output, fail_frontend=failure == "build", wrong_digest=failure == "digest")):
                    with self.assertRaises(rc.ReleaseError):
                        rc.release(self._args(output))
                self.assertTrue((output / "build-inputs.json").exists())
                self.assertFalse((output / "release.json").exists())
                self.assertFalse((output / "rc-images.env").exists())

    def test_success_emits_digest_references_and_records_committed_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "release"
            with patch.object(rc, "resolve_bases", return_value=BASES), patch.object(rc, "require_unused_tag"), \
                 patch.object(rc, "run", side_effect=self._fake_run(output)) as run:
                record = rc.release(self._args(output))
            self.assertEqual(record["source_revision"], SHA)
            self.assertIn(f"BACKEND_IMAGE=test/5x49-backend@{DIGEST}", (output / "rc-images.env").read_text())
            self.assertNotIn(":latest", (output / "rc-images.env").read_text())
            self.assertTrue((output / "release.json").exists())
            self.assertTrue(any(call.args[0][:2] == ["git", "archive"] for call in run.call_args_list))
            self.assertFalse(any(call.args[0][:2] in (["git", "tag"], ["git", "push"]) for call in run.call_args_list))

    def test_refuses_overwriting_previous_output(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(rc, "run", return_value=SHA):
            output = Path(temporary)
            (output / "release.json").write_text("retain me")
            with self.assertRaises(rc.ReleaseError):
                rc.release(self._args(output))
            self.assertEqual((output / "release.json").read_text(), "retain me")


if __name__ == "__main__":
    unittest.main()
