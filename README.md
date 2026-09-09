# TRACER Release Info

This repository provides a small public release-status file for TRACER.

TRACER itself is maintained in a private repository on an internal server. This public repository does **not** contain TRACER source code, installers, internal server information, or other private project content.

Its purpose is only to provide a stable public URL that installed copies of TRACER can query to determine whether they are current.

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

## Normal Release Procedure

When publishing a new TRACER version:

1. Update the version in the private TRACER codebase.
2. Build and test the new TRACER release.
3. Make the release available through the normal internal distribution process.
4. Update `version.json` in this repository.
5. Set `latest_version` to the new version.
6. Update `release_date`.
7. Decide whether `minimum_supported_version` also needs to change.
8. Update `message` only if there is useful release-specific information.
9. Commit and push the change to `main`.
10. Verify the GitHub Pages version of `version.json` in a browser.

For example, moving from 0.8.5 to 0.8.6 may require only:

```diff
{
  "product": "TRACER",
- "latest_version": "0.8.5",
+ "latest_version": "0.8.6",
  "minimum_supported_version": "0.8.4",
- "release_date": "2026-09-08",
+ "release_date": "2026-09-15",
  "channel": "beta",
  "stale_after_days": 14,
  "message": ""
}
```

If 0.8.4 is also no longer suitable for use:

```diff
- "minimum_supported_version": "0.8.4",
+ "minimum_supported_version": "0.8.5",
```

## Recommended Release Order

Prefer to make the internal TRACER release available **before** updating `latest_version`.

Otherwise, existing TRACER installations may warn users that a newer version exists before that version is actually available to them.

Recommended order:

```text
Finish release
    ↓
Test release
    ↓
Publish internally
    ↓
Update version.json
    ↓
Verify GitHub Pages
```

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

This repository should remain a very small public release-status endpoint.

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
