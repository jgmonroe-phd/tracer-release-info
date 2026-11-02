"""Current year-major releases retain the established client ordering contract.

Fixtures describe application versions, not decisions about production floors.
No real release metadata is rewritten or approved by these tests.
"""

from copy import deepcopy
import json
from pathlib import Path
import re
import unittest

from scripts import sync_releases as sync
from scripts.validate_policy import validate_policy, version


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "jgmonroe-phd/tracer-release-info"
README = "# Downloads\n<!-- downloads:start -->\nOld\n<!-- downloads:end -->\nKeep me.\n"
VALID = {
    "0.8.8": (0, 8, 8),
    "999.2.3": (999, 2, 3),
    "10000.2.3": (10000, 2, 3),
    "2026.9.14": (2026, 0, 9, 14),
    "2026.9.23": (2026, 0, 9, 23),
    "2026.0.9.23": (2026, 0, 9, 23),
    "v2026.0.9.23": (2026, 0, 9, 23),
    "2026.1.2.6": (2026, 1, 2, 6),
    "v2026.1.2.6": (2026, 1, 2, 6),
    "1000.0.0.0": (1000, 0, 0, 0),
    "9999.1.2.3": (9999, 1, 2, 3),
}
INVALID = (
    None, True, 2026, b"2026.1.2.6", "", "2026.1.2.6\n", "\n2026.1.2.6",
    " 2026.1.2.6", "2026.1.2.6 ", "2026.1.2.6\r", "2026.1.2.6\x00",
    "v2026.9.23", "v0.8.8", "V2026.1.2.6", "vv2026.1.2.6",
    "2026.01.2.6", "2026.1.02.6", "2026.1.2.06", "2026.09.23", "00.8.8",
    "02026.1.2.6", "0999.1.2.3", "999.1.2.3", "10000.1.2.3", "0.1.2.3",
    "2026.1.2.6.0", "2026.1.2.-6", "2026.1.2.+6",
    "2026.1.2.6rc1", "2026.1.2.6-beta", "2026.1.2.6+local", "2026.1.2.６",
)
def policy(**changes):
    result = {
        "schema_version": 2, "product": "TRACER", "latest_version": "2026.1.2.6",
        "minimum_supported_version": "2026.9.14",
        "warning_below_version": "2026.9.23", "blocked_below_version": "2026.9.14",
        "blocked_versions": [], "warning_message": "Update available.",
        "blocked_message": "Update required.", "message": "",
        "release_date": "2026-10-29", "channel": "beta", "stale_after_days": 14,
        "usage_endpoint": None,
    }
    result.update(changes)
    return result


def release(tag, *, beta=False, assets=True):
    return {
        "tag_name": tag, "draft": False, "prerelease": beta,
        "published_at": "2026-10-29T12:00:00Z",
        "html_url": f"https://github.com/{REPOSITORY}/releases/tag/{tag}",
        "assets": [{
            "name": "TRACER.exe", "state": "uploaded", "size": 123,
            "browser_download_url": f"https://github.com/{REPOSITORY}/releases/download/{tag}/TRACER.exe",
        }] if assets else [],
    }


class YearVersionContractTests(unittest.TestCase):
    def test_client_ordering_vectors_are_shared_by_policy_and_catalog(self):
        for label, key in VALID.items():
            with self.subTest(label=label):
                self.assertEqual(version(label), key)
                self.assertEqual(sync.parse_version(label), key)
        self.assertEqual(version("2026.1.2"), (2026, 0, 1, 2))

    def test_malformed_and_unsupported_labels_are_rejected(self):
        for label in INVALID:
            with self.subTest(label=label):
                with self.assertRaises(ValueError):
                    version(label)
                with self.assertRaises(ValueError):
                    sync.parse_version(label)

    def test_48_character_limit_applies_before_legacy_normalization(self):
        labels = ["2026.1.2." + "9" * 39, "2026.1." + "9" * 41]
        for label in labels:
            with self.subTest(label=label):
                self.assertEqual(len(label), 48)
                self.assertEqual(version(label), sync.parse_version(label))
                with self.assertRaises(ValueError):
                    version(label + "9")
                with self.assertRaises(ValueError):
                    sync.parse_version(label + "9")
        with self.assertRaises(ValueError):
            version("v" + labels[0])

    def test_current_major_follows_historical_series_and_sorts_numerically(self):
        ordered = ["0.8.8", "2026.9.14", "2026.9.23", "2026.1.0.0",
                   "2026.1.2.6", "2026.1.10.0", "2026.2.0.0", "2027.0.0.0"]
        self.assertEqual(sorted(reversed(ordered), key=version), ordered)
        self.assertEqual(sorted(reversed(ordered), key=sync.parse_version), ordered)

    def test_four_part_policy_with_legacy_thresholds_preserves_original_strings(self):
        candidate = policy()
        original = deepcopy(candidate)
        self.assertEqual(validate_policy(candidate), original)
        self.assertEqual(candidate, original)

    def test_floor_equality_uses_canonical_identity_without_changing_policy(self):
        for floor in ("2026.9.14", "2026.0.9.14", "v2026.0.9.14"):
            candidate = policy(minimum_supported_version=floor)
            with self.subTest(floor=floor):
                self.assertEqual(validate_policy(candidate)["minimum_supported_version"], floor)
        with self.assertRaises(ValueError):
            validate_policy(policy(minimum_supported_version="2026.9.23"))

    def test_exact_blocks_cannot_duplicate_canonical_versions(self):
        for values in (["2026.9.23", "2026.0.9.23"],
                       ["2026.0.9.23", "v2026.0.9.23"],
                       ["2026.1.2.6", "v2026.1.2.6"]):
            with self.subTest(values=values), self.assertRaises(ValueError):
                validate_policy(policy(blocked_versions=values))
        validate_policy(policy(blocked_versions=["2026.9.23", "2026.1.2.6"]))

    def test_each_version_schema_field_matches_format_and_length_contract(self):
        schema = json.loads((ROOT / "version.schema.json").read_text(encoding="utf-8"))
        fields = [schema["properties"][name] for name in (
            "latest_version", "minimum_supported_version", "warning_below_version",
            "blocked_below_version")]
        fields.append(schema["properties"]["blocked_versions"]["items"])
        valid = list(VALID) + ["2026.1.2", "2026.1.2." + "9" * 39]
        invalid = list(INVALID) + ["2026.1.2." + "9" * 40]
        for field in fields:
            while "$ref" in field:
                ref = field["$ref"]
                self.assertTrue(ref.startswith("#/"))
                field = schema
                for name in ref[2:].split("/"):
                    field = field[name]
            self.assertEqual(field["type"], "string")
            self.assertEqual(field["maxLength"], 48)
            for label, expected in [(v, True) for v in valid] + [(v, False) for v in invalid]:
                with self.subTest(field=field, label=label):
                    # JSON Schema pattern is a search, not Python fullmatch.
                    accepted = (isinstance(label, str) and len(label) <= field["maxLength"]
                                and re.search(field["pattern"], label) is not None)
                    self.assertEqual(accepted, expected)

    def test_explicit_four_part_alias_advances_catalog_without_rewriting_identity(self):
        original = policy(latest_version="2026.9.23", release_date="2026-10-19")
        candidates = [release("v2026.0.9.23"), release("v2026.1.2.6")]
        aliases = {"v2026.0.9.23": "2026.9.23", "v2026.1.2.6": "2026.1.2.6"}
        snapshot = deepcopy((original, candidates, aliases))
        updated, catalog = sync.build_metadata(original, candidates, REPOSITORY,
                                                version_aliases=aliases)
        self.assertEqual(updated, original | {"latest_version": "2026.1.2.6",
                                              "release_date": "2026-10-29"})
        self.assertEqual([entry["version"] for entry in catalog["releases"]],
                         ["2026.1.2.6", "2026.9.23"])
        new = catalog["releases"][0]
        self.assertEqual(new["release_tag"], "v2026.1.2.6")
        self.assertEqual(new["release_url"], candidates[1]["html_url"])
        self.assertEqual(new["files"][0]["url"], candidates[1]["assets"][0]["browser_download_url"])
        self.assertEqual((original, candidates, aliases), snapshot)

    def test_new_four_part_public_tags_still_need_reviewed_alias(self):
        original = policy(latest_version="2026.9.23")
        diagnostics = []
        updated, catalog = sync.build_metadata(
            original, [release("v2026.1.2.6"), release("v2026.0.9.23")], REPOSITORY,
            version_aliases={"v2026.0.9.23": "2026.9.23"}, diagnostics=diagnostics)
        self.assertEqual(updated, original)
        self.assertEqual([entry["version"] for entry in catalog["releases"]], ["2026.9.23"])
        self.assertEqual(len(diagnostics), 1)
        self.assertIn("v2026.1.2.6", diagnostics[0])
        self.assertIn("release-version-aliases.json", diagnostics[0])

    def test_alias_targets_cannot_name_one_application_twice(self):
        aliases = {"v2026.0.9.23": "2026.9.23", "v2026.1.2.6": "v2026.0.9.23"}
        with self.assertRaises(ValueError):
            sync.validate_version_aliases(aliases)

    def test_catalog_collisions_use_canonical_identity_even_without_assets(self):
        aliases = {"v2026.0.9.23": "2026.0.9.23"}
        for has_assets in (True, False):
            candidates = [release("v2026.0.9.23", assets=has_assets), release("v2026.9.23")]
            for rows in (candidates, list(reversed(candidates))):
                with self.subTest(has_assets=has_assets, rows=rows), self.assertRaisesRegex(
                        ValueError, "ambiguous published release tags"):
                    sync.build_metadata(policy(), rows, REPOSITORY, version_aliases=aliases)

    def test_distinct_channels_remain_separate_for_canonical_equivalent_versions(self):
        _, catalog = sync.build_metadata(
            policy(), [release("v2026.0.9.23"), release("v2026.9.23", beta=True)],
            REPOSITORY, version_aliases={"v2026.0.9.23": "2026.0.9.23"})
        self.assertEqual([entry["channel"] for entry in catalog["releases"]], ["stable", "beta"])

    def test_equivalent_manifest_spelling_does_not_advance_and_download_is_found(self):
        original = policy(latest_version="v2026.0.9.23", release_date="2026-10-19")
        updated, catalog = sync.build_metadata(
            original, [release("v2026.0.9.23")], REPOSITORY,
            version_aliases={"v2026.0.9.23": "2026.9.23"})
        self.assertEqual(updated, original)
        rendered = sync.render_downloads(README, updated, catalog, REPOSITORY)
        self.assertIn("/releases/download/v2026.0.9.23/TRACER.exe", rendered)
        self.assertIn("Keep me.", rendered)
        self.assertNotIn("No public download", rendered)


if __name__ == "__main__":
    unittest.main()
