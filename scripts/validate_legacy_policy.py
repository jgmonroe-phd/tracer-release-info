#!/usr/bin/env python3
"""Protect the reviewed legacy TRACER publication contract during NEXUS work.

The baseline is a reviewed publication snapshot, not a file this tool generates.
Passing these checks preserves the listed client decisions; it does not certify
every distributed executable or prove that a live endpoint has been deployed.
"""

import argparse
import json
from pathlib import Path
import re
import sys

try:
    from validate_policy import MAX_POLICY_BYTES, reject_constant, unique_object, validate_policy
except ModuleNotFoundError:
    from scripts.validate_policy import MAX_POLICY_BYTES, reject_constant, unique_object, validate_policy


ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "compatibility" / "legacy-version.json"
THREE_PART = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z")
YEAR_MAJOR = re.compile(r"v?([1-9][0-9]{3})\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z")
VERSION_FIELDS = (
    "latest_version", "minimum_supported_version", "warning_below_version",
    "blocked_below_version",
)
# Public compatibility expectations for the recovered policy. Changing these
# requires an explicit client migration review, as does replacing the baseline.
CLIENT_EXPECTATIONS = (
    ("0.8.7", "blocked"),
    ("0.8.8", "warning"),
    ("2026.9.12", "warning"),
    ("2026.9.14", "warning"),
    ("2026.9.23", "permitted"),
    ("2026.0.9.23", "permitted"),
    ("2026.1.1.0", "permitted"),
    ("2026.1.2.6", "permitted"),
)


def _check_wire_versions(policy):
    """Remain strict even if the general publisher later accepts new labels."""
    if not isinstance(policy, dict):
        raise ValueError("legacy policy must be a JSON object")
    values = [(name, policy.get(name)) for name in VERSION_FIELDS]
    blocked = policy.get("blocked_versions")
    if not isinstance(blocked, list):
        raise ValueError("legacy blocked_versions must be a list")
    values.extend(("blocked_versions", value) for value in blocked)
    for field, value in values:
        if not isinstance(value, str) or len(value) > 32 or not THREE_PART.fullmatch(value):
            raise ValueError(
                f"legacy {field} must remain strict three-part numeric text "
                "of at most 32 characters; review client migration before changing the endpoint"
            )


def _read_policy(path):
    # Read and validate the same bytes that will be compared. No second file read
    # can silently substitute different bytes after validation.
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_POLICY_BYTES + 1)
    if len(raw) > MAX_POLICY_BYTES:
        raise ValueError("legacy policy exceeds 64 KiB")
    policy = json.loads(
        raw.decode("utf-8"), object_pairs_hook=unique_object,
        parse_constant=reject_constant,
    )
    _check_wire_versions(policy)
    validate_policy(policy)
    return raw, policy


def _client_key(value):
    """Implement the documented year-major comparison for installed labels."""
    if not isinstance(value, str) or len(value) > 48:
        raise ValueError("invalid installed client version")
    match = THREE_PART.fullmatch(value)
    if match:
        parts = tuple(int(part) for part in match.groups())
        if 1000 <= parts[0] <= 9999:
            return parts[0], 0, parts[1], parts[2]
        return parts
    match = YEAR_MAJOR.fullmatch(value)
    if match:
        return tuple(int(part) for part in match.groups())
    raise ValueError("invalid installed client version")


def legacy_client_decision(policy, installed_version):
    """Return the floor/exact-block outcome for an already validated policy."""
    installed = _client_key(installed_version)
    if installed < _client_key(policy["blocked_below_version"]) or installed in {
        _client_key(item) for item in policy["blocked_versions"]
    }:
        return "blocked"
    if installed < _client_key(policy["warning_below_version"]):
        return "warning"
    return "permitted"


def validate_legacy_policy(manifest_path, baseline_path=BASELINE):
    """Validate strict policy bytes, approved snapshot and client decisions."""
    approved_raw, approved = _read_policy(baseline_path)
    manifest_raw, manifest = _read_policy(manifest_path)
    if manifest_raw != approved_raw:
        raise ValueError(
            "legacy policy differs from the reviewed compatibility baseline; "
            "restore version.json or review the intended legacy policy change and baseline together"
        )
    for installed, expected in CLIENT_EXPECTATIONS:
        # Check both inputs independently so future refactors cannot turn the
        # baseline into an unchecked authorization for altered client behavior.
        for policy in (approved, manifest):
            if legacy_client_decision(policy, installed) != expected:
                raise ValueError(
                    f"legacy policy changes the reviewed decision for TRACER {installed}; "
                    "review client migration before changing compatibility expectations"
                )
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", nargs="?", type=Path, default=ROOT / "version.json")
    args = parser.parse_args(argv)
    try:
        validate_legacy_policy(args.manifest)
    except (OSError, ValueError, RecursionError) as error:
        print(f"validate_legacy_policy: {error}", file=sys.stderr)
        return 1
    print("Legacy policy matches the reviewed baseline and client compatibility expectations.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
