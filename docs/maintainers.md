# Maintaining TRACER releases

For download and start-up instructions, see the [TRACER downloads README](../README.md).

This document covers publishing TRACER releases and maintaining the update service.

TRACER source code is maintained in a private repository on an internal server. Public executables belong in this repository's [GitHub Releases](https://github.com/jgmonroe-phd/tracer-release-info/releases), attached to a versioned release. Keep the binary files out of the Git file history.

Installed copies of TRACER continue to query the same public `version.json` URL. A separate `executables.json` lists the available release assets without changing the existing version manifest's schema.

## One-time Setup

1. Merge these files into `main`.
2. In **Settings → Pages → Build and deployment → Source**, choose **GitHub Actions**. The included workflow publishes the JSON endpoints and the download page.
3. Make sure repository or organization policy permits the workflow's declared `contents: write`, `actions: write`, `pages: write`, and `id-token: write` permissions. The metadata job commits to `main`; if branch protection requires pull requests, use an approved repository automation identity or adapt that step to your review process. Do not remove branch protection merely to enable this workflow.
4. In **Actions → Publish release catalog**, run the workflow on `main` to initialize the catalog. If the first push ran before Pages was configured, rerun it after completing step 2.
5. Verify both public JSON URLs below.

GitHub Pages can retain its default environment restriction allowing deployments only from `main`: release events dispatch a fresh workflow run on `main` before publishing. No additional personal access token is needed with the default repository permissions.

## Public Version Manifest

TRACER checks:

```text
https://jgmonroe-phd.github.io/tracer-release-info/version.json
```

The file is published through GitHub Pages.

A typical `version.json` looks like:

```json
{
  "product": "TRACER",
  "latest_version": "0.8.5",
  "minimum_supported_version": "0.8.4",
  "release_date": "2026-09-08",
  "channel": "beta",
  "stale_after_days": 14,
  "message": ""
}
```

## Fields

### `product`

Identifies the application.

```json
"product": "TRACER"
```

This should normally never need to change.

### `latest_version`

The most recent TRACER version that users should be running.

```json
"latest_version": "0.8.5"
```

When an installed copy of TRACER has a lower version, the application can display an update-available warning.

Use normal semantic version numbering:

```text
major.minor.patch
```

Examples:

```text
0.8.4
0.8.5
0.9.0
1.0.0
```

Do not compare or order versions manually as strings in TRACER code. The application uses semantic version comparison.

### `minimum_supported_version`

The oldest version that should still be considered supported.

```json
"minimum_supported_version": "0.8.4"
```

This is different from `latest_version`.

For example:

```json
"latest_version": "0.8.7",
"minimum_supported_version": "0.8.5"
```

means:

* 0.8.7 is current.
* 0.8.6 should be encouraged to update, but is still supported.
* 0.8.5 should be encouraged to update, but is still supported.
* 0.8.4 and older should receive a stronger unsupported/outdated warning.

Do not raise `minimum_supported_version` just because a newer release exists. Raise it when there is a meaningful reason that older releases should no longer be used, such as a significant bug, compatibility issue, or workflow change.

### `release_date`

The release date of `latest_version`.

```json
"release_date": "2026-09-08"
```

Use ISO format:

```text
YYYY-MM-DD
```

This is primarily informational and can also help diagnose release/version mismatches.

### `channel`

Describes the maturity of the current release series.

During active development:

```json
"channel": "beta"
```

A future stable release may use:

```json
"channel": "stable"
```

TRACER can use this field to adjust how aggressively it warns about old builds.

### `stale_after_days`

The number of days after which an offline TRACER installation should be considered potentially stale.

```json
"stale_after_days": 14
```

During beta testing, TRACER changes frequently, so 14 days is currently appropriate.

Important: TRACER also contains a local fallback stale threshold. This is necessary because if GitHub cannot be reached, TRACER cannot retrieve this field.

The remote value can therefore control normal behavior after a successful version check, while the locally bundled default provides the offline fallback.

For a future stable release, this may be increased substantially, for example:

```json
"stale_after_days": 90
```

### `message`

Optional release-specific information to show to users.

Normally this can remain empty:

```json
"message": ""
```

It can be used when there is something users should know about a release:

```json
"message": "Update recommended. This release fixes DOCX revision handling."
```

Keep this message short and appropriate for all TRACER users.

Do not include internal repository URLs, server names, credentials, implementation details, sensitive information, or anything that should not be publicly visible.

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
8. Edit `minimum_supported_version` or `message` separately when needed, then commit to `main`. Publishing a release does not automatically change support policy, stale thresholds, or your public message. An existing message is retained, so clear any message that no longer applies.

A `beta` manifest can advance to either a prerelease or stable build. A `stable` manifest advances only to stable builds. The catalog includes both channels, sorted by numeric version. Draft releases and releases without an uploaded supported attachment cannot advance the manifest. The script does not automatically lower `latest_version`, and it retains the existing date when the version is unchanged.

Attach every required platform build before publishing: the script requires at least one supported attachment and cannot infer which platforms are mandatory. The current version must be available for all users who receive its update warning.

The existing `0.8.8` version remains advertised until you publish a higher eligible version. To make the current build downloadable as well, publish a `v0.8.8` release with its actual executable attached. The supplied first-release package is documented in [the v0.8.8 release checklist](release-v0.8.8.md); upload the ZIP as a Release asset, keeping it out of Git history.

Release publication, editing, deletion, and unpublishing request a synchronization. For asset-only changes, run **Actions → Publish release catalog → Run workflow** on `main`; an asset upload/deletion alone may not trigger a release event. If you remove the currently recommended release, deliberately review and edit `latest_version` and `release_date` after resyncing; the script does not silently select an older release.

If another workflow creates releases using `GITHUB_TOKEN`, it must explicitly dispatch this workflow after uploading the files:

```bash
gh workflow run release-catalog.yml --repo jgmonroe-phd/tracer-release-info --ref main
```

That caller needs `actions: write`. GitHub does not trigger a new release-event workflow for releases created with the workflow token, but explicit workflow dispatch is supported.

## User Notifications

The JSON is an update-check endpoint. TRACER must fetch it, compare its installed version using semantic version comparison, and show the update warning. The existing mechanism described below continues to use the same fields. To add a download button, the private TRACER application can open the public Releases page or select a matching file from `executables.json`; this repository does not modify the application itself.

GitHub users can also subscribe through **Watch → Custom → Releases** on the repository to receive GitHub release notifications. Publishing JSON alone does not send email or push notifications.

## Local Verification

Run the focused synchronization tests with Python 3.10 or newer:

```bash
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
* `minimum_supported_version` is correct;
* `release_date` is correct;
* no private information is present.

GitHub Pages deployment may take a short period after a commit before the public file reflects the change.

## How TRACER Uses This File

TRACER contains its own installed version and release date.

At runtime it can compare those values with this manifest.

Typical behavior is:

```text
Installed version = latest version
    → no warning

Installed version < latest version
    → update available warning

Installed version < minimum supported version
    → stronger unsupported/outdated warning

GitHub unavailable + build is recent
    → continue silently

GitHub unavailable + build exceeds stale threshold
    → warn that the build may be outdated
```

Failure to access this repository must never prevent TRACER from starting.

The version check is advisory and should fail gracefully when a user has no internet access, GitHub is unavailable, a proxy blocks the request, or the manifest cannot be parsed.

## Local Cache

TRACER caches successful version-check information in the user's application-data directory so it does not need to query GitHub on every launch.

On Windows, this is stored alongside other TRACER configuration data under the application's Local AppData configuration directory.

The cache is disposable. Deleting it should simply cause TRACER to perform another version check.

The cache is not the authoritative source of release information. The authoritative sources are:

1. the version bundled into the installed TRACER application; and
2. this public `version.json` manifest.

## PyInstaller Builds

The same mechanism is intended to work with packaged TRACER `.exe` releases.

The installed version and build date are bundled into the executable. The update cache is stored outside the executable in the user's application-data directory.

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

## Quick Reference

For a routine patch release, the fields most likely to change are:

```json
{
  "latest_version": "NEW_VERSION",
  "release_date": "YYYY-MM-DD"
}
```

Occasionally also change:

```json
"minimum_supported_version"
```

when older versions should no longer be used.

During beta, normally leave:

```json
"channel": "beta",
"stale_after_days": 14
```

Once TRACER becomes stable, reconsider both values.

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
