# NEXUS TRACER composition policy

The NEXUS development runtime reads a separate policy from this repository's
existing GitHub Pages site:

```text
https://jgmonroe-phd.github.io/tracer-release-info/nexus-tracer.json
```

This endpoint becomes available only after the change is merged into `main` and
the **Publish release catalog** workflow successfully deploys Pages. A pull request
does not publish it. The existing application's `version.json` contract, download
page, executable catalog, and release workflow remain in service.

## Approval source and published document

Maintainers review `nexus-tracer-policy.json`. It contains the product, policy ID,
and exact approved composition hashes. The initial entry is the C06 development
composition, for bounded live qualification and comparison. It is not a declaration
of production acceptance, full capability parity, or native document-output quality.

```json
{
  "schema_version": 1,
  "product": "NEXUS-TRACER",
  "policy_id": "nexus-tracer-c06",
  "approved_compositions": [
    "460bc22125a604941e10669af6deac2a1074d7fd49325385e67b92c292d88e88"
  ]
}
```

The publishing workflow adds `issued_at` and `expires_at` when it generates
`_site/nexus-tracer.json`. Issue time is five minutes before generation to tolerate
small client clock differences. Expiry is exactly 24 hours after issue time,
leaving 23 hours and 55 minutes of validity at generation. Clients require a
current, timezone-aware window of no more than 24 hours. Incorrect client clocks
can still cause rejection.

Generation validates strict UTF-8 JSON, exact fields, identifiers, unique lowercase
SHA-256 values, and the 64 KiB input/output limits. An empty allowlist is valid and
withdraws every composition. Generation never discovers or approves a hash from
a release, branch, installation, or download automatically.

The allowlist represents a continuing maintainer decision until changed. Scheduled
generation refreshes publication freshness; it does not represent another human
review or a daily extension of a separately time-limited approval. If approval
must end at a specific time, remove the hash through the release process; this
format does not automate an approval sunset.

## Publication and withdrawal

The existing Pages publisher runs on `main` changes and manual dispatches, and now
also requests a refresh every six hours at minute 17 UTC. It validates and tests
the checked-out main revision, retains the existing public files, and generates
the NEXUS document immediately before artifact upload. It checks that remote main
still matches its checkout before generation and again before deployment, refusing
a known superseded revision. Main publishing runs remain serialized.

To approve a different reviewed composition, add its exact hash to
`nexus-tracer-policy.json` in a reviewed change. To withdraw one, remove its hash;
use `[]` to withdraw all. Merge, then verify the resulting Pages deployment and
the actual endpoint response. Protect repository writes and workflow permissions.
HTTPS and repository control establish trust; the document is not a code signature.
An opaque composition hash does not independently attest the entire installation.

Revocation is subject to deployment/CDN delay and client operation-admission
timing. A main update during an in-flight deployment is not an instantaneous
withdrawal. A failed superseded run should be followed by a successful run from
current main. Generated JSON is a Pages artifact, not a file committed on each run.

## Availability and recovery

Scheduled Actions are best effort and may be delayed or dropped. Public-repository
schedules can be disabled after 60 days without repository activity. Monitor
Actions and the endpoint's `expires_at`; scheduled refreshes do not guarantee
unattended availability. If refresh/deployment stops, the NEXUS runtime refuses
new work after the last published document expires. The original TRACER release
manifest does not use this new expiration field.

After correcting the publishing failure or re-enabling a disabled schedule, run:

```bash
gh workflow run release-catalog.yml --repo jgmonroe-phd/tracer-release-info --ref main
```

Verify the deployed JSON, not merely a green validation job. Do not recover by
disabling TLS, extending the client maximum lifetime, or reusing a cached approval.
See [GitHub's schedule behavior](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

## Client configuration and rollout

After the endpoint is published, set the integration's `policy_url` to the HTTPS
URL above and `policy_id` to `nexus-tracer-c06`. Leave live qualification disabled
while checking configuration and policy connectivity. Verify that the actual
response has the expected product and policy ID, a current issue/expiry window,
and the exact intended composition. A separate bounded live qualification and
same-process document comparison follow that check.

The C06 client requires direct HTTP 200 without redirects or interactive login,
validates TLS certificates, and requests fresh JSON with a nonce query parameter.
It sends no GenAI credentials or document content to this endpoint. The policy
does not enable quota enforcement or qualify a model. Existing client policy
checks and key handling are unchanged by this publishing addition.

Everything in this repository is public. Keep private packages, settings, keys,
catalogs, documents, internal hostnames, and paths outside this repository. Only
the opaque composition identifier is needed for this endpoint.

## Local checks

```bash
python3 scripts/validate_policy.py
python3 scripts/generate_nexus_policy.py --check
python3 -m unittest discover -s tests -v
python3 scripts/generate_nexus_policy.py --output /tmp/nexus-tracer.json
```

The generated file contains time-dependent validity fields. It must match the
installed client's exact protocol; do not point a NEXUS client at the original
`version.json`, or an original TRACER client at this endpoint.
