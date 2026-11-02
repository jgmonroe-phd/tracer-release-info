# Protecting installed TRACER during NEXUS development

The original TRACER application remains in use. Its shared `version.json` is a
production service: an invalid policy can prevent application startup. NEXUS
development uses the separate `nexus-tracer.json` composition policy.

## Approved legacy publication

`compatibility/legacy-version.json` records the policy restored after the
November 2, 2026 startup incident. `version.json` must match its bytes exactly.
The recommendation and warning threshold are `2026.9.23`; both minimum-supported
and blocking floors are `0.8.8`. No individual versions are blocked and usage
collection remains disabled. A newer installed application is not required to
downgrade to the advertised recommendation.

The publication checker independently requires three-part wire version labels
and validates the policy's raw JSON and semantics. Its compatibility cases cover
representative older and year-major application versions. Those cases describe
the known policy contract; they do not certify every distributed executable or
perform a live GenAI review.

This publication freeze deliberately rejects even formatting or message changes
until reviewed. Do not regenerate the baseline in automation. Changing a legacy
recommendation or retiring a version requires its own reviewed change, evidence
from the supported client readers and actual executable identity, and an explicit
update to the approved baseline and applicable compatibility expectations.
NEXUS composition approval is not authorization to change legacy client access.

## Publication boundaries

The workflow runs release synchronization with `--catalog-only`. It can discover
new downloads and refresh the README while preserving all `version.json` bytes.
Newer catalog entries do not automatically become the recommendation. Unknown
four-part public tags still require a verified explicit alias.

`prepare_site.py` validates every input before creating a new staging directory.
It copies the four legacy/static files exactly and generates only the separate
NEXUS policy. The staged artifact is checked before upload and again before
deployment. Missing, extra, symbolic-link or altered files are rejected; NEXUS
approvals and validity windows must match the reviewed configuration and clock.
The existing remote-main checks also reject a known superseded checkout.

```bash
python3 scripts/validate_legacy_policy.py
python3 -m unittest discover -s tests -v
python3 scripts/prepare_site.py --output /tmp/tracer-site-new
python3 scripts/prepare_site.py --output /tmp/tracer-site-new --check
```

Choose an output directory that does not already exist. Staging never overwrites
an existing directory. No key, document or GenAI request is needed for these checks.

## Owner-controlled deployment protections

The October 29 invalid policy was published by a separate branch-based Pages
deployment despite the custom validation job failing. Repository code cannot
prevent a different deployment path from bypassing its checks.

The repository owner must select **Settings > Pages > Build and deployment >
Source: GitHub Actions**, and protect `main` with required PR validation. Restrict
who can edit workflows, the compatibility baseline and deployment settings.
Do not remove branch protection to accommodate catalog automation; configure an
approved automation identity or use a reviewed catalog update instead.

The workflow now reads the Pages `build_type` in PR validation and immediately
before publishing; it requires `workflow`. A permission failure or another mode
stops this workflow with an owner action message. This detects the configuration
at that time; it cannot prevent an administrator changing it later or another
authorized workflow publishing without these checks.

After deployment, verify the actual fresh public `version.json` against the
approved baseline and confirm an affected installed client can launch. A green
PR alone is not deployment evidence. Keep the last compatible policy available
for a reviewed recovery; do not bypass the application's policy checks.

References: [GitHub Pages publishing source](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site)
and [Pages API](https://docs.github.com/en/rest/pages/pages#get-a-github-pages-site).
