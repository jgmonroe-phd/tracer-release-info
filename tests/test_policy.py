"""Publication policy invariants and explicit emergency withdrawal support."""

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.validate_policy import load_policy, validate_policy


POLICY = {
    "schema_version": 2, "product": "TRACER", "latest_version": "0.9.10",
    "minimum_supported_version": "0.8.8", "warning_below_version": "0.9.10",
    "blocked_below_version": "0.8.8", "blocked_versions": [],
    "warning_message": "Update soon.", "blocked_message": "Update required.",
    "message": "", "release_date": "2026-09-21", "channel": "beta",
    "stale_after_days": 14, "usage_endpoint": None,
}


class PolicyTests(unittest.TestCase):
    def test_current_policy_valid(self):
        load_policy(Path(__file__).resolve().parents[1] / "version.json")

    def test_rejects_wrong_schema_and_unsafe_policy(self):
        cases = [
            {"schema_version": True}, {"schema_version": 1},
            {"product": "OTHER"}, {"warning_below_version": "0.9.11"},
            {"blocked_below_version": "0.9.11", "minimum_supported_version": "0.9.11"},
            {"minimum_supported_version": "0.9.0"},
            {"blocked_versions": ["0.9.11"]},
            {"blocked_versions": ["0.9.9", "0.9.9"]}, {"blocked_versions": None},
            {"warning_below_version": "0.09.10"}, {"release_date": "2026-99-29"},
            {"release_date": None}, {"stale_after_days": True},
            {"warning_message": ""}, {"blocked_message": "message\nextra"},
            {"usage_endpoint": "http://example.com/v1/launches"},
            {"usage_endpoint": "https://user:secret@example.com/v1/launches"},
            {"usage_endpoint": "https://example.com/v1/launches?token=secret"},
            {"usage_endpoint": "https://example.com:invalid/v1/launches"},
            {"usage_endpoint": "https://example.com/v1/laun\x7fches"},
        ]
        for change in cases:
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_policy(POLICY | change)

    def test_requires_each_schema_field(self):
        for field in POLICY:
            changed = deepcopy(POLICY)
            del changed[field]
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_policy(changed)

    def test_eligible_specific_block_and_https_endpoint(self):
        validate_policy(POLICY | {
            "blocked_versions": ["0.9.9"],
            "usage_endpoint": "https://usage.example.com/v1/launches",
        })

    def test_numeric_order_not_lexical(self):
        validate_policy(POLICY | {
            "latest_version": "0.10.0", "warning_below_version": "0.9.10",
        })

    def test_emergency_exact_block_can_include_current_release(self):
        validate_policy(POLICY | {"blocked_versions": [POLICY["latest_version"]]})

    def test_cli_rejects_duplicate_keys_nonfinite_and_oversized_raw_policy(self):
        script = Path(__file__).resolve().parents[1] / "scripts" / "validate_policy.py"
        good = json.dumps(POLICY)
        invalid = [
            '{"schema_version":1,' + good[1:],
            '{"future":{"key":1,"key":2},' + good[1:],
            '{"future":NaN,' + good[1:],
            json.dumps(POLICY | {"future": "x" * 65536}),
        ]
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / "version.json"
            for raw in invalid:
                manifest.write_text(raw, encoding="utf-8")
                result = subprocess.run([sys.executable, str(script), str(manifest)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 1)
                self.assertIn("validate_policy:", result.stderr)
                self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
