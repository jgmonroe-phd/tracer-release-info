#!/usr/bin/env python3
"""Validate the published version policy without third-party dependencies."""

import argparse
from datetime import date
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit


VERSION = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z")
ROOT = Path(__file__).resolve().parents[1]
MAX_POLICY_BYTES = 64 * 1024


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError("non-finite values are not valid policy JSON")


def load_policy(path):
    """Use the client's raw decoding contract, including nested object keys."""
    with Path(path).open("rb") as source:
        payload = source.read(MAX_POLICY_BYTES + 1)
    if len(payload) > MAX_POLICY_BYTES:
        raise ValueError("version.json exceeds 64 KiB")
    policy = json.loads(
        payload.decode("utf-8"), object_pairs_hook=unique_object,
        parse_constant=reject_constant,
    )
    return validate_policy(policy)


def version(value):
    if not isinstance(value, str) or len(value) > 32 or not VERSION.fullmatch(value):
        raise ValueError("versions must be numeric major.minor.patch, at most 32 characters")
    return tuple(int(part) for part in value.split("."))


def validate_policy(policy):
    if not isinstance(policy, dict):
        raise ValueError("version.json must be an object")
    if type(policy.get("schema_version")) is not int or policy["schema_version"] != 2:
        raise ValueError("schema_version must be 2")
    if policy.get("product") != "TRACER":
        raise ValueError("product must be TRACER")
    latest = version(policy.get("latest_version"))
    warning = version(policy.get("warning_below_version"))
    blocked = version(policy.get("blocked_below_version"))
    if not blocked <= warning <= latest:
        raise ValueError("require blocked_below_version <= warning_below_version <= latest_version")
    if policy.get("minimum_supported_version") != policy["blocked_below_version"]:
        raise ValueError("minimum_supported_version must mirror blocked_below_version")
    blocked_versions = policy.get("blocked_versions")
    if not isinstance(blocked_versions, list) or len(blocked_versions) > 100:
        raise ValueError("blocked_versions must be a list of at most 100 versions")
    parsed = [version(item) for item in blocked_versions]
    if len(set(parsed)) != len(parsed) or any(item > latest for item in parsed):
        raise ValueError("blocked_versions must be unique and no newer than latest_version")
    for field in ("warning_message", "blocked_message", "message"):
        value = policy.get(field)
        if not isinstance(value, str) or len(value) > 1000 or any(ord(char) < 32 for char in value):
            raise ValueError(f"{field} must be plain text of at most 1000 characters")
    if not policy["warning_message"].strip() or not policy["blocked_message"].strip():
        raise ValueError("warning and blocked messages must not be empty")
    if policy.get("channel") not in ("beta", "stable"):
        raise ValueError("channel must be beta or stable")
    stale = policy.get("stale_after_days")
    if type(stale) is not int or not 1 <= stale <= 365:
        raise ValueError("stale_after_days must be an integer from 1 through 365")
    try:
        value = policy["release_date"]
        if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
            raise ValueError()
    except (KeyError, ValueError):
        raise ValueError("release_date must be YYYY-MM-DD") from None
    endpoint = policy.get("usage_endpoint", "missing")
    if endpoint is not None:
        if not isinstance(endpoint, str) or len(endpoint) > 2048:
            raise ValueError("usage_endpoint must be null or an HTTPS URL")
        try:
            url = urlsplit(endpoint)
            port = url.port
        except ValueError:
            raise ValueError("invalid usage_endpoint") from None
        if (
            url.scheme != "https" or not url.hostname or url.username or url.password
            or url.query or url.fragment or not url.path.startswith("/")
            or any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in endpoint)
            or (port is not None and not 1 <= port <= 65535)
        ):
            raise ValueError("usage_endpoint requires HTTPS without credentials, query, or fragment")
    return policy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", nargs="?", type=Path, default=ROOT / "version.json")
    args = parser.parse_args()
    try:
        load_policy(args.manifest)
    except (OSError, ValueError, RecursionError) as error:
        print(f"validate_policy: {error}", file=sys.stderr)
        return 1
    print("Version policy is valid (schema 2).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
