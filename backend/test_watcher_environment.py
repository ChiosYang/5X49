"""Watcher defaults must be safe even when watching is disabled."""
import os
import unittest
from unittest.mock import patch

from app.services import settings


class WatcherEnvironmentTests(unittest.TestCase):
    def defaults(self, **environment):
        with patch.dict(os.environ, environment, clear=True), patch.object(settings, "get_available_models", return_value=[]):
            return settings.get_default_settings()

    def test_invalid_and_blank_values_fall_back_with_watching_on_or_off(self):
        for enabled in ("true", "false"):
            for value in ("", " ", "oops", "NaN", "inf", "1.5", "-1", "86401", "9" * 5000):
                with self.subTest(enabled=enabled, value=value[:20]):
                    result = self.defaults(WATCH_LIBRARY=enabled, WATCH_DEBOUNCE_SECONDS=value,
                                           WATCH_INTERVAL_SECONDS=value, MEDIA_FILE_STABLE_SECONDS=value)
                    self.assertEqual(result["watch_library"], enabled == "true")
                    self.assertEqual(result["watch_debounce_seconds"], 5)
                    self.assertEqual(result["watch_interval_seconds"], 5)
                    self.assertEqual(result["media_file_stable_seconds"], 15)

    def test_valid_bounds_and_whitespace_are_respected(self):
        for value in (" 1 ", "86400"):
            result = self.defaults(WATCH_DEBOUNCE_SECONDS=value, WATCH_INTERVAL_SECONDS=value,
                                   MEDIA_FILE_STABLE_SECONDS=value)
            for key in ("watch_debounce_seconds", "watch_interval_seconds", "media_file_stable_seconds"):
                self.assertEqual(result[key], int(value))
        result = self.defaults(WATCH_DEBOUNCE_SECONDS="0", WATCH_INTERVAL_SECONDS="0", MEDIA_FILE_STABLE_SECONDS="0")
        self.assertEqual(result["watch_debounce_seconds"], 0)
        self.assertEqual(result["watch_interval_seconds"], 5)
        self.assertEqual(result["media_file_stable_seconds"], 0)

    def test_missing_values_use_defaults(self):
        result = self.defaults()
        self.assertEqual((result["watch_debounce_seconds"], result["watch_interval_seconds"], result["media_file_stable_seconds"]), (5, 5, 15))
