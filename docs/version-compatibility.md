# Current and historical TRACER versions

The original application source declares `APPLICATION_VERSION = "2026.1.2.6"`.
Its version comparison contract treats historical year.series.patch as major
zero. Publishing had retained a three-part-only parser, so it refused this real
application version before generating or deploying the separate NEXUS policy.

| Label | Comparison key |
| --- | --- |
| 0.8.8 | (0, 8, 8) |
| 2026.9.14 | (2026, 0, 9, 14) |
| 2026.9.23 | (2026, 0, 9, 23) |
| 2026.0.9.23 | (2026, 0, 9, 23) |
| 2026.1.2.6 | (2026, 1, 2, 6) |

Four-part versions require a four-digit year from 1000 through 9999. A lowercase
`v` prefix is accepted only for four-part application labels, matching the current
client. All components are numeric, with no leading zeroes, prerelease or local
suffixes; input length is at most 48 characters. Normalization affects comparisons,
not saved/displayed labels. Ordinary three-part versions keep their existing
ordering. Do not shorten 2026.1.2.6 to 2026.1.2 or reinterpret it as a date.

The validator, catalog ordering, canonical collisions, README recommendation and
download-page matching follow this contract. JSON Schema validates the formats;
the Python checker also enforces canonical ordering, equal floors and duplicate
block detection. The browser compares decimal strings without floating-point
rounding. Existing safe download URL checks remain in force.

## Release tags still need evidence

Unlisted four-part release tags remain excluded. Add a reviewed alias only after
verifying that executable's embedded application identity. An alias may now point
to a four-part year application version, including the same spelling as its tag
without `v`. This does not authorize automatic tag conversion or infer the contents
of a binary from a source checkout. The existing `v2026.0.9.23` to `2026.9.23`
mapping remains unchanged. Canonically identical versions in the same channel
are ambiguous and rejected, even if their strings differ.

## Approved floors and remaining deployment checks

The approved policy sets both `minimum_supported_version` and
`blocked_below_version` to `2026.9.14`, keeping `warning_below_version` at
`2026.9.23`. This changes the former inconsistent minimum-supported value from
`2026.9.23` to match the existing blocking floor. The recommendation remains
`2026.1.2.6`; release aliases, platform mappings and NEXUS composition approvals
are unchanged.

| Installed version | Result from these floors |
| --- | --- |
| Below 2026.9.14 | Block |
| 2026.9.14 through versions below 2026.9.23 | Warn; permit continued use |
| 2026.9.23 and above, including 2026.1.2.6 | No floor-based warning or block |

Other explicit blocks and application checks still apply. The existing
`test_current_policy_valid` remains unchanged and now accepts the consistent
checked-in policy. Do not remove that test or skip workflow validation.

Before publication:

1. The floor decision above is complete. Confirm the intended recommendation,
   channel and exact release-to-executable identity. Review all version-bearing
   fields; an approved floor does not verify a downloadable binary.
2. Verify the client generations that consume this endpoint. Current source
   supports the contract above; older three-part-only binaries will still reject
   four-part values. Qualify their migration or keep a compatible release policy
   until the affected installations are ready. This repair proves no binary rollout.
3. Repository owner confirms Pages Source is GitHub Actions. A passing source
   check alone does not establish the hosting setting or successful deployment.
4. Run policy/schema, release-sync and download-page checks; then publish and
   verify the actual fresh HTTPS policy through the installed runtime.
5. Review C07's composition separately before adding its approval. The existing
   C06-only NEXUS policy is unchanged and remains a different contract from legacy
   TRACER version policy.

Python tests use `python3 -m unittest discover -s tests -v`. The download-page
tests execute the actual inline JavaScript with Node and local mocked data; they
explicitly skip if Node is unavailable. They do not perform browser layout or
live endpoint qualification. No GenAI call or operational document is involved.
