"""Exercise the real download-page JavaScript with local data and a minimal DOM.

Node is a test-only prerequisite. No browser, HTTP request or remote page is used.
"""
import json
from pathlib import Path
import re
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")
RELEASE_URL = "https://github.com/jgmonroe-phd/tracer-release-info/releases"

HARNESS = r"""
const vm = require('node:vm');
const fs = require('node:fs');
const data = JSON.parse(fs.readFileSync(0, 'utf8'));
class Element {
  constructor(tag) { this.tag = tag; this.children = []; this.hidden = false; }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  setAttribute(name, value) { this[name] = value; }
}
const elements = new Map();
const document = {
  getElementById(id) {
    if (!elements.has(id)) elements.set(id, new Element('div'));
    return elements.get(id);
  },
  createElement(tag) { return new Element(tag); },
};
const requests = [];
const context = vm.createContext({
  document, URL, AbortController, setTimeout, clearTimeout,
  fetch: async (path) => {
    requests.push(path);
    if (!['version.json', 'executables.json'].includes(path)) throw Error('Unexpected request');
    return {ok: true, json: async () => path === 'version.json' ? data.manifest : data.catalog};
  },
});
function flatten(node) {
  return [node, ...node.children.flatMap(flatten)];
}
(async () => {
  vm.runInContext(data.script, context);
  const keys = vm.runInContext('(' + JSON.stringify(data.keyInputs) + ').map(releaseVersionKey)', context);
  await vm.runInContext('loadDownloads()', context);
  const content = document.getElementById('download-content');
  const status = document.getElementById('download-status');
  const nodes = [...flatten(content), ...flatten(status)];
  process.stdout.write(JSON.stringify({
    keys, requests, contentHidden: content.hidden,
    text: nodes.map(node => node.textContent || '').join('\n'),
    links: nodes.filter(node => node.href).map(node => node.href),
  }));
})().catch(error => { console.error(error.stack); process.exitCode = 1; });
"""


def release(version, *, url=None, files=True, channel="stable"):
    tag = "v" + version.removeprefix("v")
    return {
        "version": version, "channel": channel,
        "release_url": RELEASE_URL + "/tag/" + tag,
        "files": [{
            "name": "TRACER.zip", "url": url or RELEASE_URL + "/download/" + tag + "/TRACER.zip",
            "size_bytes": 1024, "platform": "windows", "architecture": "x64",
        }] if files else [],
    }


@unittest.skipUnless(NODE, "Node is required to execute the download-page JavaScript")
class DownloadVersionContractTests(unittest.TestCase):
    def page(self, latest, entries, *, key_inputs=(), channel="beta"):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        scripts = re.findall(r"<script>(.*?)</script>", html, re.S)
        self.assertEqual(len(scripts), 1)
        script, removed = re.subn(r"\n\s*loadDownloads\(\);\s*$", "\n", scripts[0])
        self.assertEqual(removed, 1, "Harness must remove only the automatic final call")
        result = subprocess.run(
            [NODE, "-e", HARNESS], input=json.dumps({
                "script": script, "manifest": {"latest_version": latest, "channel": channel},
                "catalog": {"releases": entries}, "keyInputs": list(key_inputs),
            }), text=True, capture_output=True, timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["requests"], ["version.json", "executables.json"])
        return report

    def test_current_four_part_version_renders_real_download_link(self):
        entry = release("2026.1.2.6", channel="beta")
        result = self.page("2026.1.2.6", [entry])
        self.assertFalse(result["contentHidden"])
        self.assertIn("Release 2026.1.2.6", result["text"])
        self.assertIn(entry["files"][0]["url"], result["links"])

    def test_legacy_and_canonical_labels_match_in_both_directions(self):
        for latest, catalog in (("2026.9.23", "2026.0.9.23"),
                                ("2026.0.9.23", "2026.9.23"),
                                ("v2026.1.2.6", "2026.1.2.6"), ("0.8.8", "0.8.8")):
            with self.subTest(latest=latest, catalog=catalog):
                result = self.page(latest, [release(catalog)])
                self.assertFalse(result["contentHidden"])
                self.assertIn("Release " + catalog, result["text"])

    def test_version_keys_reject_malformed_labels_and_preserve_large_components(self):
        invalid = [None, True, 2026, "", "2026.01.2.6", "2026.1.02.6", "2026.1.2.6-rc1",
                   "2026.1.2.6+local", "2026.1.2.6\n", "V2026.1.2.6", "v0.8.8",
                   "999.1.2.6", "10000.1.2.6", "2026.1.2.6.7", "2026.1." + "1" * 42]
        result = self.page("0.8.8", [release("0.8.8")], key_inputs=invalid)
        self.assertEqual(result["keys"], [None] * len(invalid))
        exact = ["2026.9.23", "2026.0.9.23", "2026.1.2.6", "0.8.8",
                 "2026.1.9007199254740992.6", "2026.1.9007199254740993.6"]
        result = self.page("0.8.8", [], key_inputs=exact)
        self.assertEqual(result["keys"], ["2026.0.9.23", "2026.0.9.23", *exact[2:]])
        result = self.page(exact[-1], [release(exact[-2])])
        self.assertTrue(result["contentHidden"])

    def test_invalid_missing_or_wrong_channel_release_stays_unavailable(self):
        cases = [
            ("2026.1.02.6", [release("2026.1.02.6")], "beta"),
            ("2026.1.2.6", [], "beta"),
            ("2026.1.2.6", [release("2026.1.2.6", files=False)], "beta"),
            ("2026.1.2.6", [release("2026.1.2.5")], "beta"),
            ("2026.1.2.6", [release("2026.1.2.6", channel="beta")], "stable"),
        ]
        for latest, entries, channel in cases:
            with self.subTest(latest=latest, entries=entries, channel=channel):
                result = self.page(latest, entries, channel=channel)
                self.assertTrue(result["contentHidden"])
                self.assertNotIn("is available for download", result["text"])
                self.assertEqual(result["links"], [RELEASE_URL])

    def test_four_part_support_keeps_existing_asset_url_restrictions(self):
        valid = release("2026.1.2.6")["files"][0]["url"]
        for url in (valid.replace("https:", "http:"), valid.replace("github.com", "example.com"),
                    valid + "?token=secret", valid.replace("TRACER.zip", "different.zip")):
            with self.subTest(url=url):
                result = self.page("2026.1.2.6", [release("2026.1.2.6", url=url)])
                self.assertTrue(result["contentHidden"])
                self.assertNotIn(url, result["links"])


if __name__ == "__main__":
    unittest.main()
