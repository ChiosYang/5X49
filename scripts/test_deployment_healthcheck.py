"""Execute the shipped healthcheck snippets with synthetic HTTP responses (no Docker)."""
import ast
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class DeploymentHealthcheckTests(unittest.TestCase):
    def test_both_healthchecks_reject_http_errors_and_bound_network_wait(self):
        dockerfile = (ROOT / "backend/Dockerfile").read_text()
        compose = (ROOT / "docker-compose.yml").read_text()
        commands = [re.search(r'CMD python -c "([^"]+)"', dockerfile).group(1),
                    ast.literal_eval(re.search(r'test: (\["CMD", "python", "-c", .*\])', compose).group(1))[3]]
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "requests.py").write_text('''import os
class Response:
    def raise_for_status(self):
        if int(os.environ["STATUS"]) >= 400:
            raise RuntimeError("HTTP failure")
def get(url, timeout):
    assert url == "http://localhost:8000/health"
    assert 0 < timeout < 10
    return Response()
''')
            for command in commands:
                for status in (200, 404, 500, 503):
                    with self.subTest(command=command, status=status):
                        result = subprocess.run([sys.executable, "-c", command], cwd=directory,
                                                env={"STATUS": str(status)}, capture_output=True)
                        self.assertEqual(result.returncode == 0, status == 200, result.stderr)

    def test_templates_do_not_advertise_removed_read_source(self):
        for relative in (".env.example", "backend/.env.example"):
            self.assertNotIn("LIBRARY_READ_SOURCE", (ROOT / relative).read_text())
