"""Execution input separation and source freeze, without network or keys."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import app.evaluation.search_holdout as holdout
from app.services.semantic_search import SemanticError


class ExecutionBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.patch = patch.object(holdout, "RUN", self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_freeze_only_never_reads_questions_key_or_provider(self):
        with patch.object(holdout, "SearchProviderClient", side_effect=AssertionError("No provider")), patch.object(
                holdout, "existing_credential", side_effect=AssertionError("No key")):
            first = holdout.execute(None, credential_path=None)
            second = holdout.execute(None, credential_path=None)
        self.assertEqual(first, second)
        self.assertEqual(first["requests"], 0)
        self.assertTrue((self.root / "holdout-configuration.v3.json").is_file())

    def test_changed_configuration_cannot_silently_refreeze(self):
        holdout.freeze()
        changed = {**holdout.configuration(), "candidate_limit": 1}
        with patch.object(holdout, "configuration", return_value=changed), self.assertRaisesRegex(
                SemanticError, "search_frozen_configuration_changed"):
            holdout.freeze()

    def test_execution_input_rejects_labels_extra_conditions_and_path_ids(self):
        rows = [{"id": f"isolated-{i}", "locale": "en" if i < 30 else "zh",
                 "question": f"Public fixture search {i}"} for i in range(60)]
        path = self.root / "execution.json"
        path.write_text(json.dumps(rows))
        self.assertEqual(holdout.execution_questions(path), rows)
        for name, value in (("gold", []), ("hard", {}), ("expected_ids", [])):
            bad = [dict(row) for row in rows]
            bad[0][name] = value
            path.write_text(json.dumps(bad))
            with self.assertRaises(SemanticError): holdout.execution_questions(path)
        rows[0]["id"] = "../outside"
        path.write_text(json.dumps(rows))
        with self.assertRaises(SemanticError): holdout.execution_questions(path)


if __name__ == "__main__":
    unittest.main()
