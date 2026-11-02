#!/usr/bin/env python3
"""Stage approved legacy files and an independently generated NEXUS policy."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

try:
    from .generate_nexus_policy import (
        CLOCK_SKEW, CONFIG_FIELDS, MAX_POLICY_BYTES, VALIDITY,
        load_config, render_policy, validate_config,
    )
    from .validate_legacy_policy import validate_legacy_policy
    from .validate_policy import reject_constant, unique_object
except ImportError:
    from generate_nexus_policy import (
        CLOCK_SKEW, CONFIG_FIELDS, MAX_POLICY_BYTES, VALIDITY,
        load_config, render_policy, validate_config,
    )
    from validate_legacy_policy import validate_legacy_policy
    from validate_policy import reject_constant, unique_object


ROOT = Path(__file__).resolve().parents[1]
LEGACY_FILES = ("version.json", "version.schema.json", "executables.json", "index.html")
NEXUS_FILE = "nexus-tracer.json"


def _regular_bytes(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Publication input must be a regular file: {path.name}")
    return path.read_bytes()


def _clock(now):
    current = datetime.now(timezone.utc) if now is None else now
    if not isinstance(current, datetime) or current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("Publication checks require a timezone-aware clock")
    return current.astimezone(timezone.utc)


def validate_staged_site(source_dir, output_dir, *, now=None):
    """Check exactly the files that will be uploaded, without changing them."""
    source, output = Path(source_dir), Path(output_dir)
    current = _clock(now)
    if output.is_symlink() or not output.is_dir():
        raise ValueError("Staged site must be a regular directory")
    if {p.name for p in output.iterdir()} != set(LEGACY_FILES) | {NEXUS_FILE}:
        raise ValueError("Staged site contains missing or unexpected files")
    baseline = source / "compatibility/legacy-version.json"
    validate_legacy_policy(source / "version.json", baseline)
    validate_legacy_policy(output / "version.json", baseline)
    for name in LEGACY_FILES:
        if _regular_bytes(output / name) != _regular_bytes(source / name):
            raise ValueError(f"Staged legacy file differs from its validated source: {name}")
    raw = _regular_bytes(output / NEXUS_FILE)
    if len(raw) > MAX_POLICY_BYTES:
        raise ValueError("Staged NEXUS policy exceeds 64 KiB")
    policy = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object,
                        parse_constant=reject_constant)
    if not isinstance(policy, dict) or set(policy) != CONFIG_FIELDS | {"issued_at", "expires_at"}:
        raise ValueError("Staged NEXUS policy has unexpected fields")
    config = validate_config({key: policy[key] for key in CONFIG_FIELDS})
    if config != load_config(source / "nexus-tracer-policy.json"):
        raise ValueError("Staged NEXUS approvals differ from the reviewed allowlist")
    try:
        issued = datetime.fromisoformat(policy["issued_at"].replace("Z", "+00:00"))
        expires = datetime.fromisoformat(policy["expires_at"].replace("Z", "+00:00"))
        if issued.utcoffset() is None or expires.utcoffset() is None:
            raise ValueError("NEXUS timestamps must be timezone-aware")
        if expires - issued != VALIDITY or issued > current + CLOCK_SKEW or expires <= current:
            raise ValueError("Staged NEXUS policy has an invalid or expired validity window")
    except (AttributeError, TypeError) as error:
        raise ValueError("Staged NEXUS timestamps must be ISO strings") from error


def prepare_site(source_dir, output_dir, *, now=None):
    """Validate all inputs before creating a new output directory."""
    source, output = Path(source_dir), Path(output_dir)
    current = _clock(now)
    if output.exists() or output.is_symlink():
        raise ValueError("Site output already exists; choose a new staging directory")
    validate_legacy_policy(source / "version.json", source / "compatibility/legacy-version.json")
    files = {name: _regular_bytes(source / name) for name in LEGACY_FILES}
    files[NEXUS_FILE] = render_policy(load_config(source / "nexus-tracer-policy.json"), now=current)
    output.mkdir(parents=True)
    for name, raw in files.items():
        (output / name).write_bytes(raw)
    validate_staged_site(source, output, now=current)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, default=ROOT / "_site")
    parser.add_argument("--check", action="store_true", help="Check an existing artifact without writing")
    args = parser.parse_args(argv)
    try:
        if args.check:
            validate_staged_site(args.source, args.output)
        else:
            prepare_site(args.source, args.output)
    except (OSError, ValueError, TypeError, OverflowError, RecursionError) as error:
        print(f"prepare_site: {error}", file=sys.stderr)
        return 1
    print("Publication verified: legacy files preserved; NEXUS policy matches reviewed approvals.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
