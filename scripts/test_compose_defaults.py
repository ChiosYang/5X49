"""Render only: never start containers or change host networking."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

class ComposeDefaultsTests(unittest.TestCase):
    def render(self, **overrides):
        with tempfile.TemporaryDirectory() as temporary:
            env = {key: os.environ[key] for key in ('PATH', 'HOME', 'SYSTEMROOT') if key in os.environ}
            env.update(MEDIA_DIR=temporary, **overrides)
            output = subprocess.check_output(['docker', 'compose', '--env-file', os.devnull,
                '-f', str(ROOT / 'docker-compose.yml'), 'config', '--format', 'json'], env=env, text=True)
            return json.loads(output)['services']

    def test_defaults_are_loopback_and_read_only(self):
        services = self.render()
        for service in services.values():
            self.assertTrue(all(port['host_ip'] == '127.0.0.1' for port in service['ports']))
        media = next(v for v in services['backend']['volumes'] if v['target'] == '/media')
        self.assertTrue(media['read_only'])
        self.assertFalse(media.get('bind', {}).get('create_host_path', False))

    def test_explicit_lan_and_write_opt_ins(self):
        services = self.render(BIND_ADDRESS='192.0.2.10', MEDIA_READ_ONLY='false')
        for service in services.values():
            self.assertTrue(all(port['host_ip'] == '192.0.2.10' for port in service['ports']))
        media = next(v for v in services['backend']['volumes'] if v['target'] == '/media')
        self.assertFalse(media.get('read_only', False))

if __name__ == '__main__':
    unittest.main()
