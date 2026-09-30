# Warning and blocking policy

`version.json` is the public policy consumed by new enforcement-capable TRACER clients. Existing clients that only show advisory warnings will still behave that way. Updating this repository cannot rewrite an already distributed executable, force it online, or remove its local files. Replace old binaries through managed distribution. If GenAI service authorization supports minimum client versions, enforce that separately on the server; a self-reported version is not proof of an approved executable.

## Current safe starting policy

| Field | Initial value | Meaning |
| --- | --- | --- |
| `schema_version` | `2` | Explicit policy contract |
| `latest_version` | `0.9.10` | Actual currently advertised release; do not advance before binaries are published |
| `warning_below_version` | `0.9.10` | Warn at any lower version that is not blocked |
| `blocked_below_version` | `0.8.8` | Stop at any lower version |
| `minimum_supported_version` | `0.8.8` | Compatibility mirror of blocking floor |
| `blocked_versions` | `[]` | Stop these exact versions, including versions otherwise above the floor |
| `warning_message` | Plain text | Explain the warning and update action |
| `blocked_message` | Plain text | Explain why work cannot continue and how to update |
| `usage_endpoint` | `null` | Counts remain inactive until an operator deploys the separate service |

Other retained fields: `product` must be `TRACER`; `release_date` is the latest release's date; `channel` is `beta` or `stable`; `message` is an optional public release note. `stale_after_days` remains solely for legacy readers and informational display. It does not grant new clients an offline grace period.

Versions are numeric `major.minor.patch` values, never string-sorted. Floors are exclusive: exactly equal to a floor passes that floor. Blocking always wins over warnings. A version equal to `warning_below_version` is allowed without the retirement warning unless explicitly blocked. An update may still be available above it.

The validator requires `blocked_below_version <= warning_below_version <= latest_version`, matching compatibility/blocking floors, and unique exact blocks. An exact block may include the latest release for emergency withdrawal, even if no safe replacement exists yet. Raising all floors beyond the advertised release is rejected. The JSON Schema describes the shape; `scripts/validate_policy.py` also checks these cross-field rules. Policy must be UTF-8 JSON of at most 64 KiB, without duplicate keys at any depth or non-finite numbers. Validation and release synchronization use the same strict raw loader; synchronization also checks serialized size before writing any output.

## Client contract

1. Perform a fresh HTTPS request at each launch, with a bounded timeout. Ask intermediaries not to reuse cached policy. A previous successful local response cannot authorize a new offline run. GitHub Pages/CDN propagation still takes time: this is not instantaneous revocation.
2. Require a valid schema-2 policy for TRACER and numerically compare the installed version.
3. If `installed < blocked_below_version` or installed is in `blocked_versions`, display the blocking message and update link, then stop before reviewing or modifying documents. GUI failures must be visibly prominent; CLI failures must exit nonzero. Blocking is an orderly refusal to run, not forced process termination while writing files.
4. Otherwise, if `installed < warning_below_version`, display the warning prominently and permit use.
5. Independently require authenticated GenAI connectivity before work. Missing credentials, rejected authentication, unreachable service, and an unusable model must produce actionable errors. Internet access alone does not establish GenAI readiness.
6. Unreachable policy, TLS failure, invalid JSON/schema, or offline operation stops new clients. Counter submission failure is best effort and must not be confused with these mandatory checks.

Administrative help and version display can remain available without performing a review. The application implementation defines exactly which startup actions count as launches; diagnostics should not inflate review counts. A single multi-report GUI session counts as one launch, not one event per report.

Only configure a usage endpoint on an HTTPS host operated for TRACER. Do not use URL credentials, query tokens, redirects to third parties, or a GitHub write token. The counter receives only the five documented event fields.

## Staged rollout after an actual 0.9.11 release

1. Merge and verify schema 2 on the public URL before distributing a client that requires it. Leave the existing safe floors unchanged while testing the new client against the public manifest.
2. Build, test, and publish 0.9.11 executables. Catalog synchronization then advertises `latest_version: "0.9.11"` and its actual release date. Ensure all affected users have a compatible download.
3. Warning stage: set `warning_below_version: "0.9.11"`; keep the old blocking floor and its mirror; set a message explaining the migration deadline. Record and communicate the deadline through your release process. This schema does not automatically change state on a date.
4. Blocking stage, after the warning period: set both `blocked_below_version` and `minimum_supported_version` to `"0.9.11"`; leave the warning floor at `"0.9.11"`; set a clear blocking message. Enforcement-capable clients below that version now refuse review. Previously shipped advisory-only clients still require managed replacement.
5. To withdraw a specific defective build, add that version to `blocked_versions`. Normally publish a safe replacement first. An emergency exact block may withdraw the current release immediately; users then remain blocked until an unblocked replacement is available. Make that availability impact explicit in the blocking message and incident communications.

Run these checks before each policy merge:

```bash
python3 scripts/validate_policy.py
python3 -m unittest discover -s tests -v
```

The catalog workflow validates policy before publishing. `sync_releases.py` preserves warning/blocking floors, exact blocks, messages, and the usage endpoint while advancing only actual release metadata. Do not merge changes directly to `main` as a workaround for required review.

For an erroneous block, correct the floor/list in a reviewed policy change and verify the public manifest after Pages deploys. Offline bypass is not a recovery procedure. Protect repository write access and release credentials: trusted policy is a powerful availability control.
