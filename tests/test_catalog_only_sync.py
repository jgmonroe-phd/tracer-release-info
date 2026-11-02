"""Catalog refresh must not promote or rewrite the legacy release policy."""

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.sync_releases import build_metadata, render_downloads


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "jgmonroe-phd/tracer-release-info"
README = "Keep the introduction.\n<!-- downloads:start -->\nOld downloads\n<!-- downloads:end -->\nKeep the instructions.\n"


def release(version):
    tag = "v" + version
    return {
        "tag_name": tag, "draft": False, "prerelease": False,
        "published_at": "2026-11-01T12:00:00Z",
        "html_url": f"https://github.com/{REPOSITORY}/releases/tag/{tag}",
        "assets": [{
            "name": "TRACER.exe", "state": "uploaded", "size": 123,
            "browser_download_url": f"https://github.com/{REPOSITORY}/releases/download/{tag}/TRACER.exe",
        }],
    }


class CatalogOnlySyncTests(unittest.TestCase):
    def test_catalog_only_accepts_valid_compact_manifest_at_raw_size_limit(self):
        policy = json.loads((ROOT / "version.json").read_bytes())
        policy["future_field"] = ""
        compact_size = len(json.dumps(policy, separators=(",", ":")).encode())
        policy["future_field"] = "x" * (65536 - compact_size)
        raw = json.dumps(policy, separators=(",", ":")).encode()
        self.assertEqual(len(raw), 65536)
        self.assertGreater(len(json.dumps(policy, indent=2).encode()), 65536)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "version.json").write_bytes(raw)
            (root / "README.md").write_text(README)
            (root / "platforms.json").write_text("[]")
            (root / "aliases.json").write_text("{}")
            (root / "releases.json").write_text(json.dumps([release("2026.9.24")]))
            result = subprocess.run([
                sys.executable, str(ROOT / "scripts/sync_releases.py"), "--catalog-only",
                "--repository", REPOSITORY, "--releases", str(root / "releases.json"),
                "--manifest", str(root / "version.json"), "--catalog", str(root / "executables.json"),
                "--readme", str(root / "README.md"), "--platforms", str(root / "platforms.json"),
                "--aliases", str(root / "aliases.json"),
            ], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((root / "version.json").read_bytes(), raw)
            self.assertEqual(json.loads((root / "executables.json").read_bytes())["releases"][0]["version"], "2026.9.24")

    def test_higher_release_is_cataloged_without_promoting_recommendation(self):
        original = json.loads((ROOT / "version.json").read_bytes())
        snapshot = deepcopy(original)
        candidates = [release("2026.9.24"), release("2026.9.23")]
        updated, catalog = build_metadata(original, candidates, REPOSITORY, catalog_only=True)
        self.assertEqual(updated, snapshot)
        self.assertEqual(original, snapshot)
        self.assertEqual([r["version"] for r in catalog["releases"]], ["2026.9.24", "2026.9.23"])
        readme = render_downloads(README, updated, catalog, REPOSITORY)
        self.assertIn("Recommended version: **2026.9.23**", readme)
        self.assertIn("/releases/download/v2026.9.23/", readme)
        self.assertNotIn("/releases/download/v2026.9.24/", readme)
        self.assertTrue(readme.startswith("Keep the introduction.\n"))
        self.assertTrue(readme.endswith("Keep the instructions.\n"))

    def test_missing_recommended_asset_stays_unavailable_instead_of_selecting_newer(self):
        original = json.loads((ROOT / "version.json").read_bytes())
        updated, catalog = build_metadata(original, [release("2026.9.24")], REPOSITORY, catalog_only=True)
        readme = render_downloads(README, updated, catalog, REPOSITORY)
        self.assertEqual(updated, original)
        self.assertIn("No public download is available yet for this recommended version.", readme)
        self.assertNotIn("/releases/download/v2026.9.24/", readme)

    def test_cli_preserves_exact_manifest_bytes_during_repeated_catalog_refresh(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / "version.json"
            # Formatting must survive too: the endpoint is a reviewed byte snapshot.
            raw = b" \n" + (ROOT / "version.json").read_bytes() + b"\n\t"
            manifest.write_bytes(raw)
            (root / "README.md").write_text(README)
            (root / "platforms.json").write_text("[]")
            (root / "aliases.json").write_text("{}")
            candidates = [release("2026.9.24"), release("2026.9.23")]
            (root / "releases.json").write_text(json.dumps(candidates))
            command = [
                sys.executable, str(ROOT / "scripts/sync_releases.py"), "--catalog-only",
                "--repository", REPOSITORY, "--releases", str(root / "releases.json"),
                "--manifest", str(manifest), "--catalog", str(root / "executables.json"),
                "--readme", str(root / "README.md"), "--platforms", str(root / "platforms.json"),
                "--aliases", str(root / "aliases.json"),
            ]
            for _ in range(2):
                result = subprocess.run(command, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(manifest.read_bytes(), raw)
                catalog = json.loads((root / "executables.json").read_bytes())
                self.assertEqual(catalog["releases"][0]["version"], "2026.9.24")
                self.assertIn("Recommended version: **2026.9.23**", (root / "README.md").read_text())


if __name__ == "__main__":
    unittest.main()
