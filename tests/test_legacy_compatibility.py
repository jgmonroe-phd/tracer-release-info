"""Protect legacy policy wire compatibility and the recovered client outcomes."""

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts.validate_legacy_policy import legacy_client_decision, validate_legacy_policy
from scripts.validate_policy import validate_policy


ROOT = Path(__file__).resolve().parents[1]
APPROVED_BYTES = (ROOT / "compatibility" / "legacy-version.json").read_bytes()
APPROVED = json.loads(APPROVED_BYTES)


class LegacyCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        directory = Path(self.directory.name)
        self.manifest = directory / "version.json"
        self.baseline = directory / "approved.json"
        self.manifest.write_bytes(APPROVED_BYTES)
        self.baseline.write_bytes(APPROVED_BYTES)

    def write_policy(self, changes, *, baseline=False):
        policy = deepcopy(APPROVED)
        policy.update(changes)
        raw = (json.dumps(policy, indent=2) + "\n").encode()
        self.manifest.write_bytes(raw)
        if baseline:
            self.baseline.write_bytes(raw)
        return policy

    def check(self):
        return validate_legacy_policy(self.manifest, self.baseline)

    def test_current_public_policy_matches_approved_snapshot(self):
        self.assertEqual(validate_legacy_policy(ROOT / "version.json"), APPROVED)
        self.assertEqual((ROOT / "version.json").read_bytes(), APPROVED_BYTES)

    def test_supported_client_decisions_include_year_major_versions(self):
        cases = {
            "0.8.7": "blocked",
            "0.8.8": "warning",
            "2026.9.12": "warning",
            "2026.9.14": "warning",
            "2026.9.23": "permitted",
            "2026.0.9.23": "permitted",
            "v2026.0.9.23": "permitted",
            "2026.1.1.0": "permitted",
            "2026.1.2.6": "permitted",
        }
        for installed, expected in cases.items():
            with self.subTest(installed=installed):
                self.assertEqual(legacy_client_decision(self.check(), installed), expected)

    def test_october_29_incident_policy_is_rejected(self):
        self.write_policy({
            "latest_version": "2026.1.2.6",
            "minimum_supported_version": "2026.9.23",
            "blocked_below_version": "2026.9.14",
        })
        with self.assertRaises(ValueError):
            self.check()

    def test_inconsistent_floors_fail_even_with_a_changed_baseline(self):
        self.write_policy({
            "minimum_supported_version": "2026.9.23",
            "blocked_below_version": "2026.9.14",
        }, baseline=True)
        with self.assertRaisesRegex(ValueError, "must mirror"):
            self.check()

    def test_valid_retirement_or_exact_block_cannot_drift_from_baseline(self):
        cases = [
            {"minimum_supported_version": "2026.9.14", "blocked_below_version": "2026.9.14"},
            {"blocked_versions": ["2026.9.23"]},
        ]
        for change in cases:
            with self.subTest(change=change):
                validate_policy(self.write_policy(change))
                with self.assertRaisesRegex(ValueError, "differs from the reviewed"):
                    self.check()

    def test_supported_clients_remain_protected_if_baseline_is_also_changed(self):
        cases = [
            {"minimum_supported_version": "0.8.9", "blocked_below_version": "0.8.9"},
            {"blocked_versions": ["2026.9.23"]},
            {"latest_version": "2026.9.24", "warning_below_version": "2026.9.24"},
        ]
        for change in cases:
            with self.subTest(change=change):
                validate_policy(self.write_policy(change, baseline=True))
                with self.assertRaisesRegex(ValueError, "changes the reviewed decision"):
                    self.check()

    def test_independent_wire_guard_survives_a_widened_general_validator(self):
        cases = [{field: "2026.1.2.6"} for field in (
            "latest_version", "minimum_supported_version", "warning_below_version", "blocked_below_version",
        )] + [{"blocked_versions": ["2026.1.2.6"]}]
        for change in cases:
            with self.subTest(change=change):
                self.write_policy(change, baseline=True)
                with patch("scripts.validate_legacy_policy.validate_policy", side_effect=lambda policy: policy):
                    with self.assertRaisesRegex(ValueError, "strict three-part"):
                        self.check()

    def test_wire_guard_retains_strict_length_and_spelling(self):
        for invalid in ("v2026.9.23", "2026.09.23", "2026.9.23\n", "2026.9.23-beta", "1" * 29 + ".1.0"):
            with self.subTest(invalid=invalid):
                self.write_policy({"latest_version": invalid}, baseline=True)
                with patch("scripts.validate_legacy_policy.validate_policy", side_effect=lambda policy: policy):
                    with self.assertRaisesRegex(ValueError, "strict three-part"):
                        self.check()

    def test_strict_raw_loader_checks_both_baseline_and_manifest(self):
        good = APPROVED_BYTES.decode()
        bad = [
            b"\xff", b"[]", b"{", b" " * 65537,
            ('{"schema_version":1,' + good[1:]).encode(),
            ('{"future":{"x":1,"x":2},' + good[1:]).encode(),
            ('{"future":NaN,' + good[1:]).encode(),
        ]
        for target in (self.manifest, self.baseline):
            for raw in bad:
                with self.subTest(target=target.name, raw=raw[:40]):
                    self.manifest.write_bytes(APPROVED_BYTES)
                    self.baseline.write_bytes(APPROVED_BYTES)
                    target.write_bytes(raw)
                    with self.assertRaises(ValueError):
                        self.check()

    def test_a_non_version_semantic_error_cannot_be_approved_by_copying_baseline(self):
        self.write_policy({"usage_endpoint": "http://example.com/launches"}, baseline=True)
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            self.check()

    def test_even_formatting_drift_requires_explicit_baseline_review(self):
        self.manifest.write_text(json.dumps(APPROVED))
        with self.assertRaisesRegex(ValueError, "differs from the reviewed"):
            self.check()

    def test_approved_message_edit_preserves_compatibility(self):
        changed = self.write_policy({"message": "Reviewed maintenance notice."}, baseline=True)
        self.assertEqual(self.check(), changed)

    def test_exact_block_takes_precedence_over_warning(self):
        policy = deepcopy(APPROVED)
        policy["blocked_versions"] = ["2026.9.14"]
        self.assertEqual(legacy_client_decision(policy, "2026.0.9.14"), "blocked")

    def test_invalid_installed_version_is_not_silently_compared(self):
        for value in (None, "2026.01.2.6", "2026.1.2.6\n", "v2026.9.23", "1.2.3.4", "1" * 49):
            with self.subTest(value=value), self.assertRaises(ValueError):
                legacy_client_decision(APPROVED, value)

    def test_cli_reports_actionable_errors_without_writing_or_bypass_options(self):
        script = ROOT / "scripts" / "validate_legacy_policy.py"
        self.write_policy({"message": "Unreviewed change."})
        original = self.manifest.read_bytes()
        result = subprocess.run([sys.executable, str(script), str(self.manifest)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("validate_legacy_policy:", result.stderr)
        self.assertIn("reviewed compatibility baseline", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(self.manifest.read_bytes(), original)
        bypass = subprocess.run([sys.executable, str(script), "--baseline", str(self.manifest)], capture_output=True, text=True)
        self.assertEqual(bypass.returncode, 2)

    def test_cli_default_validates_the_repository_snapshot(self):
        result = subprocess.run([sys.executable, str(ROOT / "scripts" / "validate_legacy_policy.py")], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("matches the reviewed baseline", result.stdout)


if __name__ == "__main__":
    unittest.main()
