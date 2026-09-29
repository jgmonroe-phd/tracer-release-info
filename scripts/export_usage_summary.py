#!/usr/bin/env python3
"""Export only validated aggregate counts; never write to GitHub from a client."""

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

try:
    from validate_policy import version
except ModuleNotFoundError:
    from scripts.validate_policy import version


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def validate_summary(summary):
    fields = {"schema_version", "generated_at", "window_start", "retention_days", "launches", "distinct_installations", "by_version"}
    if not isinstance(summary, dict) or set(summary) != fields:
        raise ValueError("unexpected summary fields")
    if type(summary["schema_version"]) is not int or summary["schema_version"] != 1:
        raise ValueError("summary schema_version must be 1")
    for field in ("retention_days", "launches", "distinct_installations"):
        if type(summary[field]) is not int or summary[field] < 0:
            raise ValueError(f"invalid {field}")
    if not 1 <= summary["retention_days"] <= 3650:
        raise ValueError("invalid retention window")
    times = []
    for field in ("window_start", "generated_at"):
        value = summary[field]
        if not isinstance(value, str):
            raise ValueError("invalid summary timestamp")
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            raise ValueError("summary timestamps require timezones")
        times.append(timestamp)
    if times[0] > times[1]:
        raise ValueError("summary window starts after generation")
    rows = summary["by_version"]
    if not isinstance(rows, list) or len(rows) > 1000:
        raise ValueError("invalid version summary")
    versions = set()
    total = 0
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"version", "launches", "distinct_installations"}:
            raise ValueError("unexpected per-version fields")
        parsed = version(row["version"])
        if parsed in versions:
            raise ValueError("duplicate version summary")
        versions.add(parsed)
        if any(type(row[field]) is not int or row[field] < 0 for field in ("launches", "distinct_installations")):
            raise ValueError("invalid per-version counts")
        if row["distinct_installations"] > row["launches"]:
            raise ValueError("invalid per-version distinct count")
        total += row["launches"]
    if total != summary["launches"] or summary["distinct_installations"] > total:
        raise ValueError("inconsistent summary totals")
    return summary


def fetch_summary(url, token):
    parts = urlsplit(url)
    if (
        parts.scheme != "https" or not parts.hostname or parts.username or parts.password
        or parts.query or parts.fragment or not parts.path.endswith("/v1/summary")
        or any(char.isspace() for char in url)
    ):
        raise ValueError("use the direct HTTPS admin summary URL without credentials/query/fragment")
    if len(token.encode()) < 32:
        raise ValueError("set TRACER_USAGE_ADMIN_TOKEN in the environment")
    request = Request(url, headers={"Authorization": "Bearer " + token, "Accept": "application/json"})
    with build_opener(NoRedirects()).open(request, timeout=10) as response:
        data = response.read(65537)
    if len(data) > 65536:
        raise ValueError("summary exceeds 64 KiB")
    return validate_summary(json.loads(data))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="direct HTTPS /v1/summary URL")
    parser.add_argument("--output", required=True, type=Path, help="new local aggregate JSON file")
    args = parser.parse_args()
    try:
        summary = fetch_summary(args.url, os.environ.get("TRACER_USAGE_ADMIN_TOKEN", ""))
        with args.output.open("x", encoding="utf-8") as output:
            json.dump(summary, output, indent=2)
            output.write("\n")
    except (OSError, ValueError):
        # HTTP error text can contain endpoint details. Keep errors free of secrets.
        print("export_usage_summary: export failed; check endpoint, token, response, and new output path", file=sys.stderr)
        return 1
    print("Validated aggregate summary exported. Review before publishing.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
