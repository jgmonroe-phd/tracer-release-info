#!/usr/bin/env python3
"""Build public executable metadata from a complete GitHub Releases API list."""

import argparse
from copy import deepcopy
from datetime import datetime, timezone
from fnmatch import fnmatchcase
from html import escape
import json
from pathlib import Path
import re
import sys
from urllib.parse import quote, unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
VERSION = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z")
REPOSITORY = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9][A-Za-z0-9_.-]*\Z")
PACKAGE_SUFFIXES = (
    ".exe", ".msi", ".msix", ".zip", ".tar.gz", ".tgz", ".dmg",
    ".pkg", ".appimage", ".deb", ".rpm",
)
PLATFORM_LABELS = {"windows": "Windows", "macos": "macOS", "linux": "Linux"}
ARCHITECTURES = ("x64", "x86", "arm64", "universal")
ARCHITECTURE_LABELS = {"x64": "64-bit", "x86": "32-bit", "arm64": "ARM64", "universal": "Universal"}
DOWNLOADS_START = "<!-- downloads:start -->"
DOWNLOADS_END = "<!-- downloads:end -->"


def parse_version(value):
    if not isinstance(value, str) or not VERSION.fullmatch(value):
        raise ValueError(f"invalid version {value!r}; expected major.minor.patch")
    return tuple(int(part) for part in value.split("."))


def github_url(value, expected_path):
    """Accept only the exact repository release/asset path, served over HTTPS."""
    if value is None:
        return "https://github.com" + expected_path
    if not isinstance(value, str):
        raise ValueError("release and asset URLs must be strings")
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "github.com"
        or unquote(parsed.path) != unquote(expected_path)
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(f"unexpected release or asset URL: {value!r}")
    return value


def release_date(value):
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            raise ValueError("missing timezone")
        return timestamp.astimezone(timezone.utc).date().isoformat()
    except (AttributeError, TypeError, ValueError) as error:
        raise ValueError(f"invalid release published_at: {value!r}") from error


def validate_platform_rules(rules):
    if not isinstance(rules, list):
        raise ValueError("download platform rules must be a JSON list")
    for rule in rules:
        if not isinstance(rule, dict) or set(rule) != {"pattern", "platform", "architecture"}:
            raise ValueError("each platform rule must contain pattern, platform, and architecture")
        pattern = rule["pattern"]
        if (
            not isinstance(pattern, str) or not pattern.strip()
            or "/" in pattern or "\\" in pattern
            or any(ord(char) < 32 for char in pattern)
        ):
            raise ValueError("platform rule pattern must be a nonempty filename glob")
        if not isinstance(rule["platform"], str) or rule["platform"] not in PLATFORM_LABELS:
            raise ValueError("platform rule platform must be windows, macos, or linux")
        if rule["architecture"] not in ARCHITECTURES:
            raise ValueError("platform rule architecture must be x64, x86, arm64, or universal")


def asset_platform(name, rules):
    matches = {
        (rule["platform"], rule["architecture"])
        for rule in rules if fnmatchcase(name, rule["pattern"])
    }
    if len(matches) > 1:
        raise ValueError(f"conflicting platform rules match asset {name!r}")
    return next(iter(matches), (None, None))


def asset_file(asset, repository, tag, platform_rules):
    if not isinstance(asset, dict):
        raise ValueError("each release asset must be an object")
    name = asset.get("name")
    if (
        asset.get("state") != "uploaded"
        or not isinstance(name, str)
        or not name.lower().endswith(PACKAGE_SUFFIXES)
    ):
        return None
    if "/" in name or "\\" in name or any(ord(char) < 32 for char in name):
        raise ValueError(f"invalid asset filename: {name!r}")
    size = asset.get("size")
    if not isinstance(size, int) or isinstance(size, bool) or size < 0:
        raise ValueError(f"invalid size for asset {name!r}")
    if size == 0:
        return None
    digest = asset.get("digest")
    checksum = None
    if digest is not None:
        if not isinstance(digest, str) or not re.fullmatch(r"sha256:[0-9a-fA-F]{64}", digest):
            raise ValueError(f"invalid SHA-256 digest for asset {name!r}")
        checksum = digest.split(":", 1)[1].lower()
    path = f"/{repository}/releases/download/{quote(tag, safe='')}/{quote(name, safe='')}"
    platform, architecture = asset_platform(name, platform_rules)
    return {
        "name": name,
        "url": github_url(asset.get("browser_download_url"), path),
        "size_bytes": size,
        "sha256": checksum,
        "platform": platform,
        "architecture": architecture,
    }


def build_metadata(manifest, releases, repository, platform_rules=None):
    """Return complete new documents without mutating inputs or writing files."""
    if not isinstance(releases, list):
        raise ValueError("--releases must contain a JSON list of release objects")
    if not REPOSITORY.fullmatch(repository):
        raise ValueError("--repository must be a GitHub owner/repository name")
    if platform_rules is None:
        platform_rules = []
    validate_platform_rules(platform_rules)
    if not isinstance(manifest, dict):
        raise ValueError("version.json must contain a JSON object")
    product = manifest.get("product")
    if not isinstance(product, str) or not product.strip():
        raise ValueError("version.json product must be a nonempty string")
    channel = manifest.get("channel")
    if channel not in ("beta", "stable"):
        raise ValueError("version.json channel must be beta or stable")
    current = parse_version(manifest.get("latest_version"))

    catalog = []
    for release in releases:
        if not isinstance(release, dict):
            raise ValueError("each release must be an object")
        if release.get("draft") is not False or not release.get("published_at"):
            continue
        tag = release.get("tag_name")
        if not isinstance(tag, str):
            continue
        version = tag[1:] if tag.startswith("v") else tag
        if not VERSION.fullmatch(version):
            continue
        prerelease = release.get("prerelease")
        if not isinstance(prerelease, bool):
            raise ValueError(f"release {tag!r} prerelease must be a boolean")
        assets = release.get("assets")
        if not isinstance(assets, list):
            raise ValueError(f"release {tag!r} assets must be a list")
        files = [asset_file(asset, repository, tag, platform_rules) for asset in assets]
        files = sorted(
            (item for item in files if item is not None),
            key=lambda item: (item["name"].casefold(), item["name"], item["url"]),
        )
        if not files:
            continue
        path = f"/{repository}/releases/tag/{quote(tag, safe='')}"
        catalog.append({
            "version": version,
            "channel": "beta" if prerelease else "stable",
            "release_date": release_date(release["published_at"]),
            "release_url": github_url(release.get("html_url"), path),
            "files": files,
        })

    catalog.sort(key=lambda item: (
        tuple(-number for number in parse_version(item["version"])),
        item["channel"] != "stable",
        item["release_url"],
    ))
    updated = deepcopy(manifest)
    eligible = [item for item in catalog if channel == "beta" or item["channel"] == "stable"]
    if eligible and parse_version(eligible[0]["version"]) > current:
        updated["latest_version"] = eligible[0]["version"]
        updated["release_date"] = eligible[0]["release_date"]
    return updated, {"product": product, "releases": catalog}


def markdown_text(value):
    text = re.sub(r"([\\`*_{}\[\]()#+.!-])", r"\\\1", escape(value, quote=False))
    return text.replace("|", "&#124;")


def human_size(size):
    if size >= 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MiB"
    if size >= 1024:
        return f"{size / 1024:.1f} KiB"
    return f"{size} bytes"


def render_downloads(readme, manifest, catalog, repository):
    """Replace only the marked block, using the exact recommended release."""
    if readme.count(DOWNLOADS_START) != 1 or readme.count(DOWNLOADS_END) != 1:
        raise ValueError("README must contain exactly one downloads:start and downloads:end marker pair")
    start = readme.index(DOWNLOADS_START) + len(DOWNLOADS_START)
    end = readme.index(DOWNLOADS_END)
    if end < start:
        raise ValueError("README downloads:end marker must follow downloads:start")
    recommended = next((
        item for item in catalog["releases"]
        if item["version"] == manifest["latest_version"]
        and (manifest["channel"] == "beta" or item["channel"] == "stable")
    ), None)
    version = manifest["latest_version"]
    channel = recommended["channel"] if recommended else manifest["channel"]
    lines = [f"Recommended version: **{version}** ({channel}).", ""]
    if recommended is None:
        lines.append("No public download is available yet for this recommended version.")
    else:
        files = recommended["files"]
        zip_platforms = {
            (item["platform"], item["architecture"]) for item in files
            if item["platform"] and item["architecture"] and item["name"].lower().endswith(".zip")
        }
        lines.extend(["| Platform | File | Size | Version |", "| --- | --- | --- | --- |"])
        for item in files:
            if item["name"].lower().endswith(".exe") and (item["platform"], item["architecture"]) in zip_platforms:
                continue
            platform = (
                f"{PLATFORM_LABELS[item['platform']]} ({ARCHITECTURE_LABELS[item['architecture']]})"
                if item["platform"] and item["architecture"] else "Platform not specified"
            )
            # Encode Markdown delimiters even when GitHub returned them literally.
            url = quote(item["url"], safe=":/%")
            name = markdown_text(item["name"])
            lines.append(f"| {platform} | [{name}]({url}) | {human_size(item['size_bytes'])} | {version} |")
    lines.extend(["", f"[All releases](https://github.com/{repository}/releases)"])
    return readme[:start] + "\n\n" + "\n".join(lines) + "\n\n" + readme[end:]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--releases", required=True, type=Path, help="complete Releases API JSON list")
    parser.add_argument("--repository", required=True, help="GitHub owner/repository")
    parser.add_argument("--manifest", type=Path, default=ROOT / "version.json")
    parser.add_argument("--catalog", type=Path, default=ROOT / "executables.json")
    parser.add_argument("--platforms", type=Path, default=ROOT / "download-platforms.json")
    parser.add_argument("--readme", type=Path, default=ROOT / "README.md")
    args = parser.parse_args(argv)
    try:
        if len({path.resolve() for path in (args.manifest, args.catalog, args.readme)}) != 3:
            raise ValueError("manifest, catalog, and README output paths must be different")
        releases = json.loads(args.releases.read_text(encoding="utf-8"))
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        platform_rules = json.loads(args.platforms.read_text(encoding="utf-8"))
        readme = args.readme.read_bytes().decode("utf-8")
        updated, catalog = build_metadata(manifest, releases, args.repository, platform_rules)
        updated_readme = render_downloads(readme, updated, catalog, args.repository)
        # Validate and serialize all documents before touching any output.
        manifest_text = json.dumps(updated, indent=2, ensure_ascii=False) + "\n"
        catalog_text = json.dumps(catalog, indent=2, ensure_ascii=False) + "\n"
        args.catalog.write_text(catalog_text, encoding="utf-8")
        if updated_readme != readme:
            args.readme.write_bytes(updated_readme.encode("utf-8"))
        if updated != manifest:
            args.manifest.write_text(manifest_text, encoding="utf-8")
    except (OSError, ValueError) as error:
        print(f"sync_releases: {error}", file=sys.stderr)
        return 1
    print(f"Catalog contains {len(catalog['releases'])} releases; latest version: {updated['latest_version']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
