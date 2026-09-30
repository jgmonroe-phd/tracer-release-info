# Maintaining TRACER releases

For download and start-up instructions, see the [TRACER downloads README](../README.md).

This document covers publishing TRACER releases and maintaining the update service.

TRACER source code is maintained in a private repository on an internal server. Public executables belong in this repository's [GitHub Releases](https://github.com/jgmonroe-phd/tracer-release-info/releases), attached to a versioned release. Keep the binary files out of the Git file history.

Installed copies of TRACER continue to query the same public `version.json` URL. A separate `executables.json` lists the available release assets. The version manifest now uses schema 2 with additive warning, blocking, and optional usage fields. Older clients keep their original advisory behavior; they do not acquire enforcement from this repository alone.

## One-time Setup

1. Merge these files into `main`.
2. In **Settings → Pages → Build and deployment → Source**, choose **GitHub Actions**. The included workflow publishes the JSON endpoints and the download page.
3. Make sure repository or organization policy permits the workflow's declared `contents: write`, `actions: write`, `pages: write`, and `id-token: write` permissions. The metadata job commits to `main`; if branch protection requires pull requests, use an approved repository automation identity or adapt that step to your review process. Do not remove branch protection merely to enable this workflow.
4. In **Actions → Publish release catalog**, run the workflow on `main` to initialize the catalog. If the first push ran before Pages was configured, rerun it after completing step 2.
5. Verify both public JSON URLs below.

GitHub Pages can retain its default environment restriction allowing deployments only from `main`: release events dispatch a fresh workflow run on `main` before publishing. No additional personal access token is needed with the default repository permissions.

## Version policy and usage counts

TRACER checks `https://jgmonroe-phd.github.io/tracer-release-info/version.json`.

See [release policy and staged retirement](release-policy.md) for the schema, exact version boundaries, deployment order, and the limits of retiring legacy binaries. The checked-in manifest keeps `latest_version` at **0.9.10**, warning below **0.9.10**, blocking below **0.8.8**, and `usage_endpoint` at **null**. Publishing this change does not claim a 0.9.11 binary exists or that a counter has been deployed.

See [usage-service deployment](usage-service.md) to enable counts. GitHub Pages only serves static files; it cannot increment counters from a manifest fetch. The supplied separate service records launches and estimates distinct installations within a retention window. It does not identify unique people. Do not put a GitHub write token, administrator token, or user identity in the client or manifest.

## Executable Catalog

Browse available versions and files at:

https://github.com/jgmonroe-phd/tracer-release-info/releases

Applications can retrieve the generated download catalog at:

```text
https://jgmonroe-phd.github.io/tracer-release-info/executables.json
```

The catalog starts empty until the first release is uploaded and published. It is populated from actual published release attachments, so it never starts with placeholder download links. Each release entry contains:

| Field | Meaning |
| --- | --- |
| `version` | Numeric `major.minor.patch` version from the release tag |
| `channel` | `beta` for a GitHub prerelease, otherwise `stable` |
| `release_date` | Publication date in `YYYY-MM-DD` format |
| `release_url` | Version-specific release notes and download page |
| `files` | Uploaded executable or package attachments |

Each file contains `name`, `url`, `size_bytes`, `sha256`, `platform`, and `architecture`. Platform and architecture come from explicit filename rules in `download-platforms.json`; unknown values remain `null`. The initial rule identifies the verified `TRACER_v0.8.8.zip` as Windows x64. Add a rule for each new build naming scheme after confirming its actual target. Conflicting rules fail synchronization. The checksum is `null` when GitHub does not supply a SHA-256 digest. File names should identify the platform and architecture, for example `TRACER-0.8.9-windows-x64.exe`; the catalog preserves names and does not guess compatibility. Checksums are metadata, not code signatures.

Supported attachments are `.exe`, `.msi`, `.msix`, `.zip`, `.tar.gz`, `.tgz`, `.dmg`, `.pkg`, `.AppImage`, `.deb`, and `.rpm`. GitHub's automatically generated source archives are not release attachments and are not included. Upload only distributable TRACER builds using these extensions. All entries describe versions/builds of TRACER; independently versioned companion tools would need a separate product/version mapping.

## Normal Release Procedure

1. Update the version in the private TRACER codebase, then build and test every executable you intend to distribute.
2. In this public repository, draft a GitHub Release with a tag such as `v0.8.9`. Tags must be `major.minor.patch` or `vmajor.minor.patch`, with no leading zeroes; mark beta releases as **pre-release** in GitHub instead of adding a tag suffix.
3. Attach all intended executable/package files to the draft. Use versioned, platform-specific names. Keep private source code and internal information out of public release notes and packaged files.
4. Add or update the asset rules in `download-platforms.json` for verified operating systems and architectures. Commit those rules to `main` before publishing. ZIP packages are the preferred download when the same platform also has a standalone `.exe`.
5. Publish the release only after its uploads have completed.
6. The **Publish release catalog** workflow refreshes `executables.json`, advances `latest_version` and `release_date` when an eligible higher version exists, refreshes the download section in `README.md`, commits changed files, and publishes GitHub Pages.
7. Verify the workflow succeeded and the public JSON endpoints reflect the release.
8. Edit warning/blocking fields deliberately under the [policy rollout procedure](release-policy.md), validate, and merge through review. Keep `minimum_supported_version` equal to `blocked_below_version`. Release synchronization preserves all policy, messages, and usage endpoint fields; it does not automatically retire a version.

A `beta` manifest can advance to either a prerelease or stable build. A `stable` manifest advances only to stable builds. The catalog includes both channels, sorted by numeric version. Draft releases and releases without an uploaded supported attachment cannot advance the manifest. The script does not automatically lower `latest_version`, and it retains the existing date when the version is unchanged.

Attach every required platform build before publishing: the script requires at least one supported attachment and cannot infer which platforms are mandatory. The current version must be available for all users who receive its update warning.

The existing `0.9.10` version remains advertised until you publish a higher eligible version. The historical first-release procedure is retained in [the v0.8.8 release checklist](release-v0.8.8.md). Upload binaries as Release assets, keeping them out of Git history.

Release publication, editing, deletion, and unpublishing request a synchronization. For asset-only changes, run **Actions → Publish release catalog → Run workflow** on `main`; an asset upload/deletion alone may not trigger a release event. If you remove the currently recommended release, deliberately review and edit `latest_version` and `release_date` after resyncing; the script does not silently select an older release.

If another workflow creates releases using `GITHUB_TOKEN`, it must explicitly dispatch this workflow after uploading the files:

```bash
gh workflow run release-catalog.yml --repo jgmonroe-phd/tracer-release-info --ref main
```

That caller needs `actions: write`. GitHub does not trigger a new release-event workflow for releases created with the workflow token, but explicit workflow dispatch is supported.

## User notifications

New enforcement-capable clients fetch the policy at every launch, show a prominent warning in the warning stage, and stop before review in the blocking stage or when online policy validation fails. They also require authenticated GenAI access. This repository supplies policy; the private TRACER application must implement it. Existing advisory-only binaries cannot be stopped by this JSON change.

GitHub users can subscribe through **Watch → Custom → Releases**. Publishing JSON alone does not send email or push notifications.

## Local Verification

Run the focused synchronization tests with Python 3.10 or newer:

```bash
python3 scripts/validate_policy.py
python3 -m unittest discover -s tests -v
```

To preview a sync locally with GitHub CLI authentication:

```bash
set -o pipefail
gh api --paginate --slurp 'repos/jgmonroe-phd/tracer-release-info/releases?per_page=100' | jq 'add // []' > /tmp/tracer-releases.json
python3 scripts/sync_releases.py --releases /tmp/tracer-releases.json --repository jgmonroe-phd/tracer-release-info
git diff -- version.json executables.json README.md
```

The generated public endpoints are published explicitly in the same workflow because commits made with `GITHUB_TOKEN` do not trigger branch-based GitHub Pages builds. A failed push or deployment should be investigated in Actions and rerun after its cause is resolved.

## Testing the Manifest

After changing `version.json`, open:

```text
https://jgmonroe-phd.github.io/tracer-release-info/version.json
```

Confirm that:

* the page loads successfully;
* the JSON is valid;
* `latest_version` matches the release you intended to publish;
* warning and blocking floors are correct, and `minimum_supported_version` mirrors the blocking floor;
* any emergency exact block of the recommended release is intentional and clearly communicated;
* `usage_endpoint` is null until the service is deployed and verified;
* `release_date` is correct;
* no private information is present.

GitHub Pages deployment may take a short period after a commit before the public file reflects the change.

## How current clients use this file

The intended new client checks a fresh online schema-2 manifest before work. Blocking takes precedence over warnings. A cached previous success cannot authorize an offline launch. Network, TLS, malformed-policy, and required GenAI failures produce visible errors. See [the policy contract](release-policy.md).

`minimum_supported_version`, `stale_after_days`, and `message` remain for compatibility with old clients. These compatibility fields cannot make an older advisory-only build enforce blocking or an internet requirement. Replace those builds through your software distribution process; server-side GenAI authorization can independently withdraw their access where supported.

## PyInstaller Builds

The same mechanism is intended to work with packaged TRACER `.exe` releases.

The installed version and build date are bundled into the executable. Any display cache and random installation ID are stored outside the executable in the user's application-data directory. A display cache cannot authorize offline use.

This means the mechanism works with both normal Python execution and PyInstaller-packaged releases, including one-file builds.

## Security and Privacy

Treat everything in this repository as fully public.

Do not add:

* private Git repository URLs;
* internal server names;
* internal network paths;
* API keys or credentials;
* user information;
* internal release notes that should not be public;
* source code that is not intended for public release;
* installer locations that expose internal infrastructure.

Only upload executables approved for public distribution. Anyone can download assets in this public repository.

Keep the Git repository small by storing executables as Release assets. GitHub currently permits release attachments smaller than 2 GiB each.

## Quick reference

For a routine release, publish and qualify binaries before advertising a higher `latest_version`. Catalog synchronization updates that field and `release_date` from actual assets, preserving policy.

For retirement, first raise `warning_below_version` and set `warning_message`; after the warning period, raise `blocked_below_version` and matching `minimum_supported_version`, then set `blocked_message`. Normally keep the recommended version permitted. Exact known-bad builds can go in `blocked_versions`; blocking the current release is allowed for emergency withdrawal and may leave users unable to run until a replacement is available.

For counts, deploy the HTTPS service and then configure `usage_endpoint`; leave it null while undeployed. Admin summaries are private and contain aggregate counts only.

## GitHub References

* [Binary release assets and limits](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases)
* [Release workflow events](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#release)
* [Workflow token trigger behavior](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow)
* [GitHub Pages publishing configuration](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site)
* [Custom Pages workflows](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)
* [Release notification subscriptions](https://docs.github.com/en/subscriptions-and-notifications/how-tos/managing-subscriptions-for-activity-on-github/viewing-your-subscriptions)

## Maintaining the download instructions

The workflow replaces only the section between `<!-- downloads:start -->` and `<!-- downloads:end -->` in the root README. Keep those markers intact. Edit the introduction and start-up instructions outside that section. The generated download choices always match `version.json.latest_version`; missing builds produce an unavailable message rather than pointing users to an older release.

The website reads both manifests and applies the same recommended-version policy. Assets with an unknown operating system or architecture remain labeled as unspecified; the website never guesses a computer's compatibility from its browser.
