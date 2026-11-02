"""Publication renewal cannot change or replace the legacy client contract."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest

from scripts.prepare_site import prepare_site, validate_staged_site


ROOT = Path(__file__).resolve().parents[1]
STATIC_FILES = ("version.json", "version.schema.json", "executables.json", "index.html")
NOW = datetime(2026, 11, 2, 15, 0, tzinfo=timezone.utc)


class LegacyPublicationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        self.source.mkdir()
        for name in STATIC_FILES + ("nexus-tracer-policy.json",):
            (self.source / name).write_bytes((ROOT / name).read_bytes())
        (self.source / "compatibility").mkdir()
        (self.source / "compatibility/legacy-version.json").write_bytes(
            (ROOT / "compatibility/legacy-version.json").read_bytes()
        )
        self.output = self.root / "site"

    def prepare(self):
        prepare_site(self.source, self.output, now=NOW)

    def validate(self):
        validate_staged_site(self.source, self.output, now=NOW)

    def test_publication_copies_legacy_files_and_emits_only_separate_nexus_policy(self):
        originals = {name: (self.source / name).read_bytes() for name in STATIC_FILES}
        self.prepare()
        self.validate()
        self.assertEqual({p.name for p in self.output.iterdir()}, set(STATIC_FILES) | {"nexus-tracer.json"})
        for name, expected in originals.items():
            self.assertEqual((self.output / name).read_bytes(), expected)
            self.assertEqual((self.source / name).read_bytes(), expected)
        config = json.loads((self.source / "nexus-tracer-policy.json").read_bytes())
        generated = json.loads((self.output / "nexus-tracer.json").read_bytes())
        self.assertEqual(set(generated), set(config) | {"issued_at", "expires_at"})
        for field, value in config.items():
            self.assertEqual(generated[field], value)

    def test_repeated_renewal_changes_only_nexus_timestamps(self):
        first = self.root / "first"
        prepare_site(self.source, first, now=NOW - timedelta(hours=6))
        self.prepare()
        self.validate()
        validate_staged_site(self.source, first, now=NOW)
        for name in STATIC_FILES:
            self.assertEqual((first / name).read_bytes(), (self.output / name).read_bytes())
        earlier = json.loads((first / "nexus-tracer.json").read_bytes())
        newer = json.loads((self.output / "nexus-tracer.json").read_bytes())
        self.assertNotEqual(earlier.pop("issued_at"), newer.pop("issued_at"))
        self.assertNotEqual(earlier.pop("expires_at"), newer.pop("expires_at"))
        self.assertEqual(earlier, newer)

    def test_unapproved_valid_floor_change_fails_before_output_creation(self):
        path = self.source / "version.json"
        policy = json.loads(path.read_bytes())
        policy.update(minimum_supported_version="2026.9.14", blocked_below_version="2026.9.14")
        path.write_text(json.dumps(policy))
        with self.assertRaises(ValueError):
            self.prepare()
        self.assertFalse(self.output.exists())

    def test_invalid_nexus_config_fails_before_output_creation(self):
        path = self.source / "nexus-tracer-policy.json"
        config = json.loads(path.read_bytes())
        config["approved_compositions"].append("not-a-composition-hash")
        path.write_text(json.dumps(config))
        with self.assertRaises(ValueError):
            self.prepare()
        self.assertFalse(self.output.exists())

    def test_existing_output_and_symlink_targets_remain_untouched(self):
        self.output.mkdir()
        sentinel = self.output / "keep.txt"
        sentinel.write_bytes(b"existing output")
        with self.assertRaises((ValueError, OSError)):
            self.prepare()
        self.assertEqual(sentinel.read_bytes(), b"existing output")
        self.assertEqual(list(self.output.iterdir()), [sentinel])
        alias = self.root / "alias"
        alias.symlink_to(self.output, target_is_directory=True)
        with self.assertRaises((ValueError, OSError)):
            prepare_site(self.source, alias, now=NOW)
        self.assertEqual(sentinel.read_bytes(), b"existing output")

    def test_staged_legacy_policy_and_static_file_mutations_are_rejected(self):
        self.prepare()
        for name in STATIC_FILES:
            path = self.output / name
            original = path.read_bytes()
            with self.subTest(file=name):
                path.write_bytes(original + b"\n")
                with self.assertRaises(ValueError):
                    self.validate()
                path.write_bytes(original)
        self.validate()

    def test_changed_approval_cannot_be_smuggled_into_generated_policy(self):
        self.prepare()
        path = self.output / "nexus-tracer.json"
        generated = json.loads(path.read_bytes())
        generated["approved_compositions"].append("b" * 64)
        path.write_text(json.dumps(generated))
        with self.assertRaises(ValueError):
            self.validate()

    def test_duplicate_generated_json_keys_are_rejected(self):
        self.prepare()
        path = self.output / "nexus-tracer.json"
        raw = path.read_text()
        path.write_text('{"schema_version":1,' + raw[1:])
        with self.assertRaises(ValueError):
            self.validate()

    def test_invalid_generated_freshness_windows_are_rejected(self):
        self.prepare()
        path = self.output / "nexus-tracer.json"
        original = path.read_bytes()
        baseline = json.loads(original)
        cases = [
            {"expires_at": (NOW + timedelta(days=2)).isoformat()},
            {"issued_at": "2026-11-02T14:55:00", "expires_at": "2026-11-03T14:55:00"},
            {"issued_at": (NOW - timedelta(days=2)).isoformat(), "expires_at": (NOW - timedelta(days=1)).isoformat()},
            {"issued_at": (NOW + timedelta(hours=1)).isoformat(), "expires_at": (NOW + timedelta(hours=25)).isoformat()},
        ]
        for changes in cases:
            with self.subTest(changes=changes):
                path.write_text(json.dumps(baseline | changes))
                with self.assertRaises(ValueError):
                    self.validate()
        path.write_bytes(original)
        self.validate()

    def test_extra_missing_and_symlink_staged_files_are_rejected(self):
        self.prepare()
        extra = self.output / "unexpected.json"
        extra.write_text("{}")
        with self.assertRaises(ValueError):
            self.validate()
        extra.unlink()
        path = self.output / "index.html"
        raw = path.read_bytes()
        path.unlink()
        with self.assertRaises(ValueError):
            self.validate()
        path.symlink_to(self.source / "index.html")
        with self.assertRaises(ValueError):
            self.validate()
        path.unlink()
        path.write_bytes(raw)
        self.validate()


if __name__ == "__main__":
    unittest.main()
