"""NEXUS publication preserves reviewed approvals and bounded policy freshness."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts.generate_nexus_policy import (
    MAX_POLICY_BYTES, generate_policy, load_config, render_policy, validate_config,
)


CONFIG = {
    "schema_version": 1, "product": "NEXUS-TRACER", "policy_id": "nexus-tracer-test",
    "approved_compositions": ["a" * 64],
}
NOW = datetime(2026, 10, 29, 12, 30, 0, 123456, tzinfo=timezone.utc)
SCRIPT = Path(__file__).resolve().parents[1] / "scripts/generate_nexus_policy.py"


class NexusPolicyTests(unittest.TestCase):
    def test_exact_wire_shape_and_time_boundaries(self):
        raw = render_policy(CONFIG, now=NOW)
        value = json.loads(raw)
        self.assertEqual(set(value), set(CONFIG) | {"issued_at", "expires_at"})
        for key, expected in CONFIG.items():
            self.assertEqual(value[key], expected)
        issued = datetime.fromisoformat(value["issued_at"].replace("Z", "+00:00"))
        expires = datetime.fromisoformat(value["expires_at"].replace("Z", "+00:00"))
        self.assertEqual(issued, NOW - timedelta(minutes=5))
        self.assertEqual(expires - issued, timedelta(hours=24))
        self.assertTrue(issued <= NOW < expires)
        self.assertEqual(expires - NOW, timedelta(hours=23, minutes=55))
        self.assertLessEqual(len(raw), MAX_POLICY_BYTES)

    def test_fixed_clock_is_deterministic_and_timezone_normalized(self):
        other = NOW.astimezone(timezone(timedelta(hours=-5)))
        self.assertEqual(render_policy(CONFIG, now=NOW), render_policy(CONFIG, now=other))
        self.assertEqual(render_policy(CONFIG, now=NOW), render_policy(CONFIG, now=NOW))

    def test_refresh_only_changes_freshness_fields(self):
        original = deepcopy(CONFIG)
        older = json.loads(render_policy(CONFIG, now=NOW))
        newer = json.loads(render_policy(CONFIG, now=NOW + timedelta(hours=6)))
        self.assertEqual(CONFIG, original)
        self.assertNotEqual(older.pop("issued_at"), newer.pop("issued_at"))
        self.assertNotEqual(older.pop("expires_at"), newer.pop("expires_at"))
        self.assertEqual(older, newer)

    def test_empty_allowlist_remains_empty(self):
        value = json.loads(render_policy(CONFIG | {"approved_compositions": []}, now=NOW))
        self.assertEqual(value["approved_compositions"], [])

    def test_validation_detaches_approvals_from_input(self):
        value = validate_config(CONFIG)
        value["approved_compositions"].append("b" * 64)
        self.assertEqual(CONFIG["approved_compositions"], ["a" * 64])

    def test_strict_contract_rejects_wrong_or_unknown_fields(self):
        cases = [
            {"schema_version": True}, {"schema_version": 1.0}, {"schema_version": 2},
            {"product": "TRACER"}, {"policy_id": ""}, {"policy_id": "a" * 129},
            {"policy_id": "https://example.org/policy"}, {"policy_id": "two words"},
            {"policy_id": "identifier\n"}, {"policy_id": "-starts-wrong"},
            {"policy_id": None}, {"issued_at": "2026-10-29T00:00:00Z"},
            {"api_key": "not-a-policy-field"}, {"approved_compositions": None},
            {"approved_compositions": "a" * 64}, {"approved_compositions": [1]},
            {"approved_compositions": ["A" * 64]}, {"approved_compositions": ["a" * 63]},
            {"approved_compositions": ["a" * 64 + "\n"]},
            {"approved_compositions": ["a" * 64, "a" * 64]},
            {"approved_compositions": [f"{i:064x}" for i in range(1001)]},
        ]
        for change in cases:
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_config(CONFIG | change)

    def test_identifier_boundary_and_opaque_characters(self):
        validate_config(CONFIG | {"policy_id": "a" * 128})
        validate_config(CONFIG | {"policy_id": "nexus:review/test-1.0_approved"})

    def test_every_config_field_is_required(self):
        for key in CONFIG:
            value = deepcopy(CONFIG)
            del value[key]
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_config(value)

    def test_wrong_root_type_is_rejected(self):
        for value in (None, [], 1, "policy"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_config(value)

    def test_naive_and_non_datetime_clocks_are_rejected(self):
        for value in (NOW.replace(tzinfo=None), "2026-10-29", 0):
            with self.subTest(value=value), self.assertRaises(ValueError):
                render_policy(CONFIG, now=value)

    def test_count_bound_does_not_override_wire_size_limit(self):
        config = CONFIG | {"approved_compositions": [f"{i:064x}" for i in range(1000)]}
        validate_config(config)
        with self.assertRaisesRegex(ValueError, "generated.*64 KiB"):
            render_policy(config, now=NOW)

    def test_raw_loader_rejects_ambiguous_and_oversized_json(self):
        cases = [b'{"schema_version":1,"schema_version":1}',
                 b'{"x":{"key":1,"key":2}}', b'{"x":NaN}', b'{"x":Infinity}',
                 b'{"x":-Infinity}', b'{"x":1e999}', b'\xff', b'{} trailing',
                 b' ' * (MAX_POLICY_BYTES + 1)]
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "input.json"
            for raw in cases:
                path.write_bytes(raw)
                with self.subTest(raw=raw[:40]), self.assertRaises(ValueError):
                    load_config(path)

    def test_loader_accepts_exact_size_limit_but_not_one_more_byte(self):
        raw = json.dumps(CONFIG).encode()
        padded = raw + b" " * (MAX_POLICY_BYTES - len(raw))
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "input.json"
            path.write_bytes(padded)
            self.assertEqual(load_config(path), CONFIG)
            path.write_bytes(padded + b" ")
            with self.assertRaisesRegex(ValueError, "configuration exceeds"):
                load_config(path)

    def test_generation_replaces_only_target_and_preserves_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.json"
            source.write_text(json.dumps(CONFIG))
            original = source.read_bytes()
            target = root / "site/nexus-tracer.json"
            raw = generate_policy(source, target, now=NOW)
            self.assertEqual(target.read_bytes(), render_policy(CONFIG, now=NOW))
            self.assertEqual(raw, target.read_bytes())
            self.assertEqual(source.read_bytes(), original)
            self.assertEqual(list(target.parent.iterdir()), [target])
            generate_policy(source, target, now=NOW + timedelta(hours=6))
            self.assertNotEqual(target.read_bytes(), raw)

    def test_invalid_config_preserves_existing_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.json"
            source.write_text(json.dumps(CONFIG | {"product": "wrong"}))
            target = root / "nexus-tracer.json"
            target.write_bytes(b"previous published policy")
            with self.assertRaises(ValueError):
                generate_policy(source, target, now=NOW)
            self.assertEqual(target.read_bytes(), b"previous published policy")
            self.assertEqual(sorted(p.name for p in root.iterdir()), ["nexus-tracer.json", "source.json"])

    def test_atomic_replace_failure_preserves_output_and_cleans_temporary(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.json"
            source.write_text(json.dumps(CONFIG))
            target = root / "nexus-tracer.json"
            target.write_bytes(b"previous published policy")
            with patch("scripts.generate_nexus_policy.os.replace", side_effect=OSError("injected failure")):
                with self.assertRaises(OSError):
                    generate_policy(source, target, now=NOW)
            self.assertEqual(target.read_bytes(), b"previous published policy")
            self.assertEqual(sorted(p.name for p in root.iterdir()), ["nexus-tracer.json", "source.json"])

    def test_source_cannot_be_overwritten_by_generated_policy(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source.json"
            source.write_text(json.dumps(CONFIG))
            original = source.read_bytes()
            with self.assertRaisesRegex(ValueError, "separate regular file"):
                generate_policy(source, source, now=NOW)
            self.assertEqual(source.read_bytes(), original)

    def test_cli_check_does_not_write_and_reports_invalid_input(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.json"
            source.write_text(json.dumps(CONFIG))
            result = subprocess.run([sys.executable, str(SCRIPT), "--config", str(source), "--check"],
                                    cwd=root, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(list(root.iterdir()), [source])
            source.write_text('{}')
            result = subprocess.run([sys.executable, str(SCRIPT), "--config", str(source), "--check"],
                                    cwd=root, capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(list(root.iterdir()), [source])

    def test_cli_output_requires_explicit_destination(self):
        result = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source.json"
            source.write_text(json.dumps(CONFIG))
            target = Path(temporary) / "policy.json"
            result = subprocess.run([sys.executable, str(SCRIPT), "--config", str(source),
                                     "--output", str(target)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            value = json.loads(target.read_bytes())
            self.assertEqual(value["approved_compositions"], CONFIG["approved_compositions"])


if __name__ == "__main__":
    unittest.main()
