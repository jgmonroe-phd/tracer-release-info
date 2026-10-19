# Publishing TRACER 2026.9.23

This is a publishing checklist, not an announcement that an executable is available. The source build identifies itself as **2026.9.23**, dated **2026-10-19**. Publish a tested native build before advertising it through `version.json`.

## Build on Windows in Command Prompt

Start in the updated TRACER source directory containing `build.py` and `pyproject.toml`. Installing a new wheel does not update an older source directory used for packaging. The application supports Python 3.11–3.13; these commands use installed 64-bit Python 3.11.

```bat
py -3.11 -m venv .venv-windows
.venv-windows\Scripts\python.exe -m pip install --upgrade pip
.venv-windows\Scripts\python.exe -m pip install -e . pyinstaller pywin32
.venv-windows\Scripts\python.exe -c "from tr_review.version import APPLICATION_VERSION; print(APPLICATION_VERSION)"
.venv-windows\Scripts\python.exe -c "import struct; print(struct.calcsize('P') * 8)"
.venv-windows\Scripts\python.exe -m tkinter
```

Confirm the output is `2026.9.23` and `64`. Close the Tk test window, then build and launch:

```bat
.venv-windows\Scripts\python.exe build.py
dist\TRACER_v2026.9.23.exe
```

Test the executable on another supported Windows machine without Python installed. Confirm startup, authenticated GenAI access, a small document review, output creation, pending review decisions, and clean-copy export. Recipients still need network access and GenAI credentials. Pandoc is separately required for LaTeX conversion; optional OCR may need Tesseract. This repository update does not claim those Windows or live GenAI checks have been performed.

## Publish the executable

1. Draft a release with tag **`v2026.9.23`** and title **`TRACER 2026.9.23`**. Use three numeric components; `v2026.0.9.23` is invalid for the catalog and application policy.
2. Attach the verified `TRACER_v2026.9.23.exe`, or a ZIP containing the tested package. Attach all intended platform builds before publishing. Keep private source code, report documents, test evidence and credentials out of public attachments.
3. After verifying the Windows x64 target, add an exact rule for the uploaded filename to `download-platforms.json` and merge it before publication. For the standalone executable:

   ```json
   {
     "pattern": "TRACER_v2026.9.23.exe",
     "platform": "windows",
     "architecture": "x64"
   }
   ```

   Add a separate exact rule for a ZIP if used. Do not label other builds by guessing from their filenames.
4. Add the public release notes below. Mark the GitHub release as a prerelease if it is still a beta; the existing beta manifest accepts either prerelease or stable builds.
5. Publish after uploads and checks finish. The **Publish release catalog** workflow updates `executables.json`, advances `latest_version` and `release_date` from the published release, refreshes the README download table, and deploys Pages. The public release date is the actual publication date, which may differ from the source build date.
6. Verify [version.json](https://jgmonroe-phd.github.io/tracer-release-info/version.json), [executables.json](https://jgmonroe-phd.github.io/tracer-release-info/executables.json), and the [download page](https://jgmonroe-phd.github.io/tracer-release-info/). Confirm version, asset link, size, checksum and platform. For asset-only changes, manually run the workflow on `main`.

The existing retirement policy remains in place: warning below `0.9.10`, blocking below `0.8.8`, no exact blocked versions, and usage counting disabled. Routine release synchronization preserves those settings. Version 2026.9.23 can pass that policy before it becomes the advertised release.

## Public release notes

TRACER 2026.9.23 separates completed processing with pending human decisions from unfinished review execution.

- **Completed—review required** means processing finished and review decisions remain. Failed requests, cancellation, missing coverage, limits and output failures still produce **Incomplete**, with explanations and available results retained.
- **05_Final_review.docx** retains pending tracked proposals and comments so reviewers can make the remaining decisions in Word.
- **Export reviewed clean copy…** creates **06_Clean_copy.docx** after remaining revisions and comments have been addressed. It preserves the reviewed source and does not silently accept unresolved changes.
- Reference-check request planning, GenAI compatibility and Windows packaging fixes from the preceding build are retained.

Review the final document and its coverage before publication. A completed run or clean copy does not certify scientific accuracy or publication readiness.
