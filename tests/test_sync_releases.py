"""Regression checks for what the public update endpoint may advertise."""

from copy import deepcopy
from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "sync_releases.py"
SPEC = importlib.util.spec_from_file_location("sync_releases", SCRIPT)
sync = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sync)
REPOSITORY = "jgmonroe-phd/tracer-release-info"
README = "# TRACER\n\n<!-- downloads:start -->\nOld content\n<!-- downloads:end -->\n\nKeep these instructions.\n"


def manifest(channel="beta"):
    return {
        "product": "TRACER", "latest_version": "0.8.8",
        "minimum_supported_version": "0.8.6", "release_date": "2026-09-14",
        "channel": channel, "stale_after_days": 14, "message": "Keep this message.",
        "future_field": {"preserved": True},
        "schema_version": 2, "warning_below_version": "0.8.8",
        "blocked_below_version": "0.8.6", "blocked_versions": ["0.8.7"],
        "warning_message": "Update soon.", "blocked_message": "Update required.",
        "usage_endpoint": None,
    }


def release(version="0.8.9", prerelease=False, **changes):
    tag = "v" + version
    result = {
        "tag_name": tag, "draft": False, "prerelease": prerelease,
        "published_at": "2026-09-15T12:30:00Z",
        "html_url": f"https://github.com/{REPOSITORY}/releases/tag/{tag}",
        "assets": [{
            "name": "TRACER.exe", "state": "uploaded", "size": 123,
            "digest": "sha256:" + "a" * 64,
            "browser_download_url": f"https://github.com/{REPOSITORY}/releases/download/{tag}/TRACER.exe",
        }],
    }
    result.update(changes)
    return result


class MetadataTests(unittest.TestCase):
    def test_explicit_public_tag_alias_keeps_urls_and_three_part_policy(self):
        original = manifest()
        tag, name = "v2026.0.9.23", "v2026_0_9_23.zip"
        candidate = release("2026.0.9.23", published_at="2026-10-19T17:30:30Z", assets=[{
            "name": name, "state": "uploaded", "size": 62157526,
            "browser_download_url": f"https://github.com/{REPOSITORY}/releases/download/{tag}/{name}",
        }])
        snapshot = deepcopy(candidate)
        aliases = {tag: "2026.9.23"}
        updated, catalog = sync.build_metadata(
            original, [candidate], REPOSITORY, version_aliases=aliases,
        )
        self.assertEqual(updated, original | {
            "latest_version": "2026.9.23", "release_date": "2026-10-19",
        })
        self.assertEqual(original, manifest())
        self.assertEqual(candidate, snapshot)
        self.assertEqual(aliases, {tag: "2026.9.23"})
        entry = catalog["releases"][0]
        self.assertEqual(entry["version"], "2026.9.23")
        self.assertEqual(entry["display_version"], "2026.0.9.23")
        self.assertEqual(entry["release_tag"], tag)
        self.assertEqual(entry["release_url"], candidate["html_url"])
        self.assertEqual(entry["files"][0]["url"], candidate["assets"][0]["browser_download_url"])
        self.assertEqual(entry["files"][0]["size_bytes"], 62157526)
        rendered = sync.render_downloads(README, updated, catalog, REPOSITORY)
        self.assertIn("Recommended version: **2026.0.9.23**", rendered)
        self.assertIn("Application version: **2026.9.23**", rendered)
        self.assertIn(f"/releases/download/{tag}/{name}", rendered)
        self.assertIn("| 2026.0.9.23 |", rendered)

    def test_aliases_do_not_convert_unlisted_tags_or_change_standard_entry_fields(self):
        diagnostics = []
        _, catalog = sync.build_metadata(
            manifest(), [release("2026.0.9.18"), release("2026.0.9.12"), release()],
            REPOSITORY, version_aliases={"v2026.0.9.23": "2026.9.23"}, diagnostics=diagnostics,
        )
        self.assertEqual(len(catalog["releases"]), 1)
        self.assertEqual(set(catalog["releases"][0]), {
            "version", "channel", "release_date", "release_url", "files",
        })
        self.assertEqual(len(diagnostics), 2)
        self.assertTrue(all("release-version-aliases.json" in item for item in diagnostics))
        self.assertTrue(all("not converted automatically" in item for item in diagnostics))

    def test_alias_configuration_rejects_invalid_tags_values_and_duplicate_targets(self):
        for aliases in (
            [], {"v2026.9.23": "2026.9.24"}, {"v2026.0.09.23": "2026.9.23"},
            {"v2026.0.9.23\n": "2026.9.23"}, {"V2026.0.9.23": "2026.9.23"},
            {"v2026.0.9.23": "2026.0.9.23"}, {"v2026.0.9.23": "2026.09.23"},
            {"v2026.0.9.23": 23}, {23: "2026.9.23"},
            {"v2026.0.9.23": "2026.9.23", "v2026.1.9.23": "2026.9.23"},
        ):
            with self.subTest(aliases=aliases), self.assertRaises(ValueError):
                sync.build_metadata(manifest(), [], REPOSITORY, version_aliases=aliases)

    def test_ambiguous_published_tags_fail_even_if_one_has_no_package(self):
        aliases = {"v2026.0.9.23": "2026.9.23"}
        for candidates in (
            [release("2026.0.9.23"), release("2026.9.23")],
            [release("2026.9.23"), release("2026.0.9.23")],
            [release("2026.0.9.23", assets=[]), release("2026.9.23")],
            [release("2026.9.23"), release("2026.9.23", tag_name="2026.9.23")],
        ):
            with self.subTest(candidates=candidates), self.assertRaisesRegex(ValueError, "ambiguous published release tags"):
                sync.build_metadata(manifest(), candidates, REPOSITORY, version_aliases=aliases)

    def test_distinct_channels_and_unpublished_tags_are_not_alias_collisions(self):
        updated, catalog = sync.build_metadata(
            manifest(), [release("2026.0.9.23"), release("2026.9.23", prerelease=True),
                         release("2026.9.23", draft=True)],
            REPOSITORY, version_aliases={"v2026.0.9.23": "2026.9.23"},
        )
        self.assertEqual(updated["latest_version"], "2026.9.23")
        self.assertEqual([item["channel"] for item in catalog["releases"]], ["stable", "beta"])

    def test_alias_without_package_never_advances_policy(self):
        diagnostics = []
        updated, catalog = sync.build_metadata(
            manifest(), [release("2026.0.9.23", assets=[])], REPOSITORY,
            version_aliases={"v2026.0.9.23": "2026.9.23"}, diagnostics=diagnostics,
        )
        self.assertEqual(updated, manifest())
        self.assertEqual(catalog["releases"], [])
        self.assertEqual(len(diagnostics), 1)
        self.assertIn("Upload the built executable", diagnostics[0])

    def test_cli_loads_default_or_explicit_aliases_and_rejects_missing_or_duplicate_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            alias_json = '{"v2026.0.9.23": "2026.9.23"}'
            cases = [
                (None, [], 0, "0.8.8"),
                (alias_json, [], 0, "2026.9.23"),
                (alias_json, ["--aliases", str(root / "release-version-aliases.json")], 0, "2026.9.23"),
                (None, ["--aliases", str(root / "missing.json")], 1, "0.8.8"),
                ('{"v2026.0.9.23":"2026.9.23","v2026.0.9.23":"2026.9.24"}', [], 1, "0.8.8"),
            ]
            for alias_contents, options, expected_status, expected_version in cases:
                with self.subTest(alias_contents=alias_contents, options=options):
                    inputs = {
                        "version.json": json.dumps(manifest()), "executables.json": '{"original":true}',
                        "releases.json": json.dumps([release("2026.0.9.23")]),
                        "README.md": README, "download-platforms.json": "[]",
                    }
                    for name, contents in inputs.items():
                        (root / name).write_text(contents, encoding="utf-8")
                    alias_path = root / "release-version-aliases.json"
                    alias_path.unlink(missing_ok=True)
                    if alias_contents is not None:
                        alias_path.write_text(alias_contents, encoding="utf-8")
                    with patch.object(sync, "ROOT", root), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                        status = sync.main(["--repository", REPOSITORY, "--releases", str(root / "releases.json"), *options])
                    self.assertEqual(status, expected_status)
                    self.assertEqual(json.loads((root / "version.json").read_text())["latest_version"], expected_version)
                    if expected_status:
                        for name, contents in inputs.items():
                            self.assertEqual((root / name).read_text(), contents)

    def test_four_part_published_tags_are_diagnosed_without_changing_policy(self):
        original = manifest()
        diagnostics = []
        updated, catalog = sync.build_metadata(
            original, [release("2026.0.9.18"), release("2026.0.9.12")],
            REPOSITORY, diagnostics=diagnostics,
        )
        self.assertEqual(updated, original)
        self.assertEqual(catalog["releases"], [])
        self.assertEqual(len(diagnostics), 2)
        for tag, diagnostic in zip(("v2026.0.9.18", "v2026.0.9.12"), diagnostics):
            self.assertIn(tag, diagnostic)
            self.assertIn("major.minor.patch", diagnostic)
            self.assertIn("embedded version", diagnostic)

    def test_three_part_build23_fixture_advances_without_changing_policy(self):
        original = manifest()
        diagnostics = []
        candidate = release("2026.9.23", published_at="2026-10-19T12:00:00Z")
        updated, catalog = sync.build_metadata(
            original, [candidate], REPOSITORY, diagnostics=diagnostics,
        )
        self.assertEqual(updated, original | {
            "latest_version": "2026.9.23", "release_date": "2026-10-19",
        })
        self.assertEqual(catalog["releases"][0]["version"], "2026.9.23")
        self.assertEqual(diagnostics, [])

    def test_published_releases_without_packages_have_actionable_diagnostics(self):
        diagnostics = []
        candidates = [
            release("2026.9.23", assets=[]),
            release("2026.9.22", assets=[{"name": "TRACER.exe.sha256", "state": "uploaded"}]),
            release("2026.9.21", assets=[{"name": "TRACER.exe", "state": "starter"}]),
            release("2026.9.20", assets=[{"name": "TRACER.exe", "state": "uploaded", "size": 0}]),
        ]
        updated, catalog = sync.build_metadata(
            manifest(), candidates, REPOSITORY, diagnostics=diagnostics,
        )
        self.assertEqual(updated, manifest())
        self.assertEqual(catalog["releases"], [])
        self.assertEqual(len(diagnostics), len(candidates))
        for candidate, diagnostic in zip(candidates, diagnostics):
            self.assertIn(candidate["tag_name"], diagnostic)
            self.assertIn("Upload the built executable", diagnostic)

    def test_warning_cannot_inject_additional_workflow_commands(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        message = "tag%0A\r\n::error::untrusted"
        with patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                sync.report_warning(message)
        self.assertEqual(stdout.getvalue(), "::warning::tag%250A%0D%0A::error::untrusted\n")
        self.assertEqual(stderr.getvalue(), "sync_releases: warning: tag%0A\\r\\n::error::untrusted\n")
        self.assertEqual(len(stdout.getvalue().splitlines()), 1)
        self.assertEqual(len(stderr.getvalue().splitlines()), 1)

    def test_cli_reports_skipped_published_releases_and_counts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidates = [
                release("2026.9.23", published_at="2026-10-19T12:00:00Z"),
                release("2026.0.9.18"), release("2026.9.22", assets=[]),
                release("2026.9.24", draft=True), release(tag_name="bad%\r\n::error::injected"),
            ]
            inputs = {
                "version.json": json.dumps(manifest()), "releases.json": json.dumps(candidates),
                "README.md": README, "download-platforms.json": "[]",
            }
            for name, contents in inputs.items():
                (root / name).write_text(contents, encoding="utf-8")
            command = [
                sys.executable, str(SCRIPT), "--repository", REPOSITORY,
                "--releases", str(root / "releases.json"), "--manifest", str(root / "version.json"),
                "--catalog", str(root / "executables.json"), "--readme", str(root / "README.md"),
                "--platforms", str(root / "download-platforms.json"),
            ]
            for actions in ("false", "true"):
                with self.subTest(actions=actions):
                    result = subprocess.run(command, capture_output=True, text=True,
                                            env=os.environ | {"GITHUB_ACTIONS": actions})
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn("accepted 1 of 5 input releases; skipped 4", result.stdout)
                    self.assertIn("v2026.0.9.18", result.stderr)
                    self.assertIn("v2026.9.22", result.stderr)
                    self.assertIn("Upload the built executable", result.stderr)
                    annotations = [line for line in result.stdout.splitlines() if line.startswith("::")]
                    self.assertEqual(len(annotations), 3 if actions == "true" else 0)
                    self.assertTrue(all(line.startswith("::warning::") for line in annotations))
                    self.assertFalse(any(line.startswith("::error::") for line in result.stderr.splitlines()))
            self.assertEqual(json.loads((root / "version.json").read_text())["latest_version"], "2026.9.23")

    def test_advances_version_and_preserves_policy_and_unknown_fields(self):
        original = manifest()
        snapshot = deepcopy(original)
        updated, catalog = sync.build_metadata(original, [release()], REPOSITORY)
        expected = deepcopy(original)
        expected.update(latest_version="0.8.9", release_date="2026-09-15")
        self.assertEqual(updated, expected)
        self.assertEqual(original, snapshot)
        self.assertEqual(catalog["releases"][0]["files"][0]["sha256"], "a" * 64)

    def test_drafts_unpublished_and_assetless_releases_are_not_advertised(self):
        candidates = [
            release(draft=True), release(published_at=None), release(assets=[]),
            release(assets=[{"name": "TRACER.exe.sha256", "state": "uploaded"}]),
            release(assets=[{"name": "TRACER.exe", "state": "starter"}]),
            release(assets=[{"name": "TRACER.exe", "state": "uploaded", "size": 0}]),
            release(tag_name="nightly"), release(tag_name="v0.9.0-beta.1"),
        ]
        updated, catalog = sync.build_metadata(manifest(), candidates, REPOSITORY)
        self.assertEqual(updated, manifest())
        self.assertEqual(catalog, {"product": "TRACER", "releases": []})

    def test_stable_channel_excludes_prereleases_from_update_but_lists_them(self):
        updated, catalog = sync.build_metadata(
            manifest("stable"), [release("0.9.0", prerelease=True), release()], REPOSITORY,
        )
        self.assertEqual(updated["latest_version"], "0.8.9")
        self.assertEqual([item["channel"] for item in catalog["releases"]], ["beta", "stable"])

    def test_beta_channel_accepts_prerelease(self):
        updated, _ = sync.build_metadata(manifest(), [release(prerelease=True)], REPOSITORY)
        self.assertEqual(updated["latest_version"], "0.8.9")
        self.assertEqual(updated["channel"], "beta")

    def test_does_not_roll_back_or_rewrite_date_for_matching_version(self):
        for candidates in ([], [release("0.8.7")], [release("0.8.8")]):
            with self.subTest(candidates=candidates):
                updated, _ = sync.build_metadata(manifest(), candidates, REPOSITORY)
                self.assertEqual(updated, manifest())

    def test_numeric_version_order_and_deterministic_assets(self):
        candidates = [release("0.9.0"), release("0.10.0"), release("1.0.0")]
        candidates[0]["assets"].extend([
            {"name": "a.zip", "state": "uploaded", "size": 45},
            {"name": "b.AppImage", "state": "uploaded", "size": 67},
        ])
        updated, catalog = sync.build_metadata(manifest(), candidates, REPOSITORY)
        reversed_input = deepcopy(candidates[::-1])
        for item in reversed_input:
            item["assets"].reverse()
        self.assertEqual(sync.build_metadata(manifest(), reversed_input, REPOSITORY), (updated, catalog))
        self.assertEqual(updated["latest_version"], "1.0.0")
        self.assertEqual([item["version"] for item in catalog["releases"]], ["1.0.0", "0.10.0", "0.9.0"])
        self.assertEqual([item["name"] for item in catalog["releases"][2]["files"]], ["a.zip", "b.AppImage", "TRACER.exe"])

    def test_missing_url_is_encoded_and_missing_digest_is_null(self):
        item = release(assets=[{"name": "TRACER win #1.zip", "state": "uploaded", "size": 42}])
        del item["html_url"]
        _, catalog = sync.build_metadata(manifest(), [item], REPOSITORY)
        file = catalog["releases"][0]["files"][0]
        self.assertTrue(file["url"].endswith("/TRACER%20win%20%231.zip"))
        self.assertIsNone(file["sha256"])

    def test_rejects_unsafe_or_mismatched_urls(self):
        for url in (
            "http://github.com/" + REPOSITORY + "/releases/tag/v0.8.9",
            "https://evil.example/" + REPOSITORY + "/releases/tag/v0.8.9",
            "https://github.com/other/repo/releases/tag/v0.8.9",
            "https://github.com/" + REPOSITORY + "/releases/tag/v0.8.9?redirect=x",
        ):
            with self.subTest(url=url), self.assertRaisesRegex(ValueError, "unexpected release or asset URL"):
                sync.build_metadata(manifest(), [release(html_url=url)], REPOSITORY)
        item = release()
        item["assets"][0]["browser_download_url"] = "https://github.com/other/repo/releases/download/v0.8.9/TRACER.exe"
        with self.assertRaisesRegex(ValueError, "unexpected release or asset URL"):
            sync.build_metadata(manifest(), [item], REPOSITORY)

    def test_rejects_invalid_manifest_and_release_list(self):
        for key, value in (("product", ""), ("product", None), ("channel", "nightly"), ("latest_version", "v0.8.8"), ("latest_version", "0.08.8")):
            invalid = manifest()
            invalid[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                sync.build_metadata(invalid, [], REPOSITORY)
        with self.assertRaisesRegex(ValueError, "JSON list"):
            sync.build_metadata(manifest(), {"message": "API error"}, REPOSITORY)

    def test_explicit_platform_rules_and_unknown_assets(self):
        rules = [{"pattern": "TRACER_v0.8.8.zip", "platform": "windows", "architecture": "x64"}]
        item = release("0.8.8", assets=[
            {"name": "TRACER_v0.8.8.zip", "state": "uploaded", "size": 62646868},
            {"name": "unknown.exe", "state": "uploaded", "size": 123},
        ])
        _, catalog = sync.build_metadata(manifest(), [item], REPOSITORY, rules)
        known, unknown = catalog["releases"][0]["files"]
        self.assertEqual((known["platform"], known["architecture"]), ("windows", "x64"))
        self.assertEqual((unknown["platform"], unknown["architecture"]), (None, None))
        future = release(assets=[{"name": "TRACER_v0.8.9.zip", "state": "uploaded", "size": 123}])
        _, catalog = sync.build_metadata(manifest(), [future], REPOSITORY, rules)
        self.assertIsNone(catalog["releases"][0]["files"][0]["platform"])

    def test_glob_platform_rules_and_conflicting_matches(self):
        rule = {"pattern": "TRACER*", "platform": "windows", "architecture": "x64"}
        _, catalog = sync.build_metadata(manifest(), [release()], REPOSITORY, [rule, rule])
        self.assertEqual(catalog["releases"][0]["files"][0]["platform"], "windows")
        conflict = {"pattern": "*.exe", "platform": "windows", "architecture": "arm64"}
        with self.assertRaisesRegex(ValueError, "conflicting platform rules"):
            sync.build_metadata(manifest(), [release()], REPOSITORY, [rule, conflict])
        for invalid in (
            {}, [{"pattern": "*.exe", "platform": "android", "architecture": "arm64"}],
            [{"pattern": "*.exe", "platform": "windows", "architecture": "guess"}],
            [{"pattern": "", "platform": "windows", "architecture": "x64"}],
        ):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                sync.build_metadata(manifest(), [], REPOSITORY, invalid)

    def test_readme_advances_to_recommended_version_and_preserves_surrounding_text(self):
        updated, catalog = sync.build_metadata(manifest(), [release("0.8.8"), release("0.9.0")], REPOSITORY)
        rendered = sync.render_downloads(README, updated, catalog, REPOSITORY)
        self.assertIn("Recommended version: **0.9.0**", rendered)
        self.assertIn("/releases/download/v0.9.0/TRACER.exe", rendered)
        self.assertNotIn("/releases/download/v0.8.8/", rendered)
        self.assertIn("Platform not specified", rendered)
        self.assertEqual(rendered.split(sync.DOWNLOADS_START)[0], README.split(sync.DOWNLOADS_START)[0])
        self.assertEqual(rendered.split(sync.DOWNLOADS_END)[1], README.split(sync.DOWNLOADS_END)[1])

    def test_readme_does_not_link_older_or_ineligible_releases_as_recommended(self):
        for candidates in ([], [release("0.8.7")], [release("0.8.8", prerelease=True)]):
            with self.subTest(candidates=candidates):
                updated, catalog = sync.build_metadata(manifest("stable"), candidates, REPOSITORY)
                rendered = sync.render_downloads(README, updated, catalog, REPOSITORY)
                self.assertIn("No public download is available yet", rendered)
                self.assertNotIn("/releases/download/", rendered)
                self.assertIn(f"[All releases](https://github.com/{REPOSITORY}/releases)", rendered)

    def test_readme_prefers_known_platform_zip_and_escapes_asset_markdown(self):
        rules = [{"pattern": "TRACER*", "platform": "windows", "architecture": "x64"}]
        item = release(assets=[
            {"name": "TRACER.zip", "state": "uploaded", "size": 62646868},
            {"name": "TRACER.exe", "state": "uploaded", "size": 123},
            {"name": "[odd]|(file)<name>.zip", "state": "uploaded", "size": 123},
        ])
        updated, catalog = sync.build_metadata(manifest(), [item], REPOSITORY, rules)
        rendered = sync.render_downloads(README, updated, catalog, REPOSITORY)
        self.assertIn("Windows (64-bit)", rendered)
        self.assertIn("59.7 MiB", rendered)
        self.assertIn("/TRACER.zip)", rendered)
        self.assertNotIn("/TRACER.exe)", rendered)
        self.assertIn(r"\[odd\]&#124;\(file\)&lt;name&gt;\.zip", rendered)
        self.assertIn("/%5Bodd%5D%7C%28file%29%3Cname%3E.zip)", rendered)

    def test_readme_requires_one_ordered_marker_pair(self):
        updated, catalog = sync.build_metadata(manifest(), [], REPOSITORY)
        for invalid in ("# No markers", README + README, sync.DOWNLOADS_END + sync.DOWNLOADS_START):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(ValueError, "README"):
                sync.render_downloads(invalid, updated, catalog, REPOSITORY)

    def test_invalid_input_leaves_both_output_files_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            version_path = root / "version.json"
            catalog_path = root / "executables.json"
            releases_path = root / "releases.json"
            readme_path = root / "README.md"
            platforms_path = root / "download-platforms.json"
            version_path.write_text(json.dumps(manifest()), encoding="utf-8")
            catalog_path.write_text('{"original": true}\n', encoding="utf-8")
            readme_path.write_text(README, encoding="utf-8")
            platforms_path.write_text("[]", encoding="utf-8")
            original = version_path.read_bytes(), catalog_path.read_bytes(), readme_path.read_bytes()
            for input_data in ({"message": "Bad credentials"}, [release(), release("0.9.0", html_url="https://example.com/bad")]):
                releases_path.write_text(json.dumps(input_data), encoding="utf-8")
                result = subprocess.run([
                    sys.executable, str(SCRIPT), "--repository", REPOSITORY,
                    "--releases", str(releases_path), "--manifest", str(version_path),
                    "--catalog", str(catalog_path),
                    "--readme", str(readme_path), "--platforms", str(platforms_path),
                ], capture_output=True, text=True)
                self.assertEqual(result.returncode, 1)
                self.assertIn("sync_releases:", result.stderr)
                self.assertEqual((version_path.read_bytes(), catalog_path.read_bytes(), readme_path.read_bytes()), original)

    def test_invalid_readme_prevents_all_output_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = {
                "version.json": json.dumps(manifest()), "executables.json": '{"original": true}\n',
                "releases.json": json.dumps([release()]), "README.md": "# Missing markers\n",
                "download-platforms.json": "[]",
            }
            for name, contents in inputs.items():
                (root / name).write_text(contents, encoding="utf-8")
            result = subprocess.run([
                sys.executable, str(SCRIPT), "--repository", REPOSITORY,
                "--releases", str(root / "releases.json"), "--manifest", str(root / "version.json"),
                "--catalog", str(root / "executables.json"), "--readme", str(root / "README.md"),
                "--platforms", str(root / "download-platforms.json"),
            ], capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn("README", result.stderr)
            for name, contents in inputs.items():
                self.assertEqual((root / name).read_text(encoding="utf-8"), contents)

    def test_duplicate_and_oversized_serialized_policy_never_touch_outputs(self):
        valid = json.dumps(manifest())
        candidates = [
            '{"schema_version":1,' + valid[1:],
            json.dumps(manifest() | {"future": [0] * 10000}, separators=(",", ":")),
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for raw in candidates:
                inputs = {
                    "version.json": raw, "executables.json": '{"original": true}\n',
                    "releases.json": json.dumps([release()]), "README.md": README,
                    "download-platforms.json": "[]",
                }
                for name, contents in inputs.items():
                    (root / name).write_text(contents, encoding="utf-8")
                result = subprocess.run([
                    sys.executable, str(SCRIPT), "--repository", REPOSITORY,
                    "--releases", str(root / "releases.json"), "--manifest", str(root / "version.json"),
                    "--catalog", str(root / "executables.json"), "--readme", str(root / "README.md"),
                    "--platforms", str(root / "download-platforms.json"),
                ], capture_output=True, text=True)
                self.assertEqual(result.returncode, 1)
                self.assertIn("sync_releases:", result.stderr)
                for name, contents in inputs.items():
                    self.assertEqual((root / name).read_text(encoding="utf-8"), contents)


if __name__ == "__main__":
    unittest.main()
