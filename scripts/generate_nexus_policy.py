#!/usr/bin/env python3
"""Publish a fresh NEXUS policy from an explicitly reviewed composition allowlist.

Refreshing timestamps never selects or approves another build. This generator
uses only the supplied local configuration and the current UTC clock.
"""

import argparse
from datetime import datetime, timedelta, timezone
import json
import math
import os
from pathlib import Path
import re
import tempfile


ROOT = Path(__file__).resolve().parents[1]
MAX_POLICY_BYTES = 64 * 1024
MAX_COMPOSITIONS = 1000
CLOCK_SKEW = timedelta(minutes=5)
VALIDITY = timedelta(hours=24)
CONFIG_FIELDS = {"schema_version", "product", "policy_id", "approved_compositions"}


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError("non-finite numbers are not valid policy JSON")


def _finite_float(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("non-finite numbers are not valid policy JSON")
    return number


def validate_config(config):
    """Return a detached allowlist after checking its exact publishing contract."""
    if not isinstance(config, dict) or set(config) != CONFIG_FIELDS:
        raise ValueError("NEXUS configuration must contain exactly the four documented fields")
    if type(config["schema_version"]) is not int or config["schema_version"] != 1:
        raise ValueError("NEXUS schema_version must be the integer 1")
    if config["product"] != "NEXUS-TRACER":
        raise ValueError("NEXUS product must be NEXUS-TRACER")
    policy_id = config["policy_id"]
    if (not isinstance(policy_id, str)
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}", policy_id) is None
            or "://" in policy_id):
        raise ValueError("policy_id must be an opaque identifier of at most 128 characters")
    approved = config["approved_compositions"]
    if not isinstance(approved, list) or len(approved) > MAX_COMPOSITIONS:
        raise ValueError("approved_compositions must be a list of at most 1000 hashes")
    if any(not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None
           for value in approved):
        raise ValueError("composition hashes must be lowercase SHA-256 values")
    if len(set(approved)) != len(approved):
        raise ValueError("composition hashes must be unique")
    return dict(schema_version=1, product="NEXUS-TRACER", policy_id=policy_id,
                approved_compositions=list(approved))


def load_config(path):
    """Read at most 64 KiB; reject ambiguous JSON before approving any build."""
    with Path(path).open("rb") as source:
        raw = source.read(MAX_POLICY_BYTES + 1)
    if len(raw) > MAX_POLICY_BYTES:
        raise ValueError("NEXUS configuration exceeds 64 KiB")
    return validate_config(json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object,
                                      parse_constant=_reject_constant, parse_float=_finite_float))


def render_policy(config, *, now=None):
    """Return C06-compatible bytes; a fixed aware clock produces identical bytes.

    Five minutes of backward clock tolerance is included within, not added to,
    the 24-hour validity window. Empty allowlists revoke all compositions.
    """
    policy = validate_config(config)
    current = datetime.now(timezone.utc) if now is None else now
    if not isinstance(current, datetime) or current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("policy generation requires a timezone-aware clock")
    issued = current.astimezone(timezone.utc) - CLOCK_SKEW
    policy["issued_at"] = issued.isoformat().replace("+00:00", "Z")
    policy["expires_at"] = (issued + VALIDITY).isoformat().replace("+00:00", "Z")
    raw = (json.dumps(policy, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    if len(raw) > MAX_POLICY_BYTES:
        raise ValueError("generated NEXUS policy exceeds 64 KiB")
    return raw


def generate_policy(config_path, output_path, *, now=None):
    """Validate first, then atomically replace only the requested output file."""
    source = Path(config_path)
    target = Path(output_path)
    if source.resolve() == target.resolve() or target.is_symlink():
        raise ValueError("policy output must be a separate regular file")
    raw = render_policy(load_config(source), now=now)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix="." + target.name + ".",
                                         mode="wb", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.chmod(0o644)
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return raw


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "nexus-tracer-policy.json")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--output", type=Path)
    action.add_argument("--check", action="store_true", help="Validate without writing a policy")
    args = parser.parse_args(argv)
    try:
        if args.check:
            render_policy(load_config(args.config))  # Also enforce the wire size cap.
            print("NEXUS composition allowlist validated; no policy file written.")
        else:
            generate_policy(args.config, args.output)
            print("NEXUS policy generated from the explicit composition allowlist.")
    except (OSError, ValueError, TypeError, OverflowError, RecursionError) as error:
        parser.exit(2, str(error) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
