# TRACER release v2026.0.9.23

The public Windows release is **v2026.0.9.23**, with asset **v2026_0_9_23.zip**, published on **2026-10-19**. The corresponding source build identifies itself as application version **2026.9.23**.

The exact mapping in `release-version-aliases.json` lets the catalog recommend your existing release and download URLs. The website and README show release **2026.0.9.23** and application version **2026.9.23**. The client policy retains the three-component application version because distributed TRACER executables reject four-component policy versions. The release tag and ZIP filename do not need to change.

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

The executable's filename and About version can remain `2026.9.23` while it is distributed under public release `v2026.0.9.23`.

Test the executable on another supported Windows machine without Python installed. Confirm startup, authenticated GenAI access, a small document review, output creation, pending review decisions, and clean-copy export. Recipients still need network access and GenAI credentials. Pandoc is separately required for LaTeX conversion; optional OCR may need Tesseract. The release-info repository update checks the uploaded executable's architecture without executing it and does not establish that these native or live GenAI checks passed.

## Maintain the published release

1. Keep tag **`v2026.0.9.23`** and its Windows ZIP. No re-upload is required for this catalog correction.
2. Preserve the exact mapping **`"v2026.0.9.23": "2026.9.23"`**. Configure future nonstandard public tags individually after confirming the corresponding application version; do not globally rewrite all four-component tags.
3. The exact filename rule for `v2026_0_9_23.zip` identifies **Windows x64**. Its downloaded bytes matched GitHub's SHA-256, and the contained `dist/TRACER_v2026.9.23.exe` has PE machine value `0x8664`. The executable was inspected but not run. Verify other assets independently before adding their platform rules.
4. Keep private source code, report documents, test evidence and credentials out of public attachments. Add the public release notes below if desired.
5. The **Publish release catalog** workflow updates `executables.json`, advances the application `latest_version` and actual publication date, refreshes the README download table, and deploys Pages. Run it manually on `main` after asset-only changes.
6. Verify [version.json](https://jgmonroe-phd.github.io/tracer-release-info/version.json), [executables.json](https://jgmonroe-phd.github.io/tracer-release-info/executables.json), and the [download page](https://jgmonroe-phd.github.io/tracer-release-info/). The policy should say `2026.9.23`; the catalog should additionally identify `v2026.0.9.23` and retain its original asset URL.

The update warning now applies below application version `2026.9.23`, corresponding to public release `v2026.0.9.23`. Supported older builds may continue after the warning. Blocking below `0.8.8`, no exact blocked versions, and disabled usage counting remain unchanged. This change does not newly block any version.

## Public release notes

TRACER release 2026.0.9.23 (application version 2026.9.23) separates completed processing with pending human decisions from unfinished review execution.

- **Completed—review required** means processing finished and review decisions remain. Failed requests, cancellation, missing coverage, limits and output failures still produce **Incomplete**, with explanations and available results retained.
- **05_Final_review.docx** retains pending tracked proposals and comments so reviewers can make the remaining decisions in Word.
- **Export reviewed clean copy…** creates **06_Clean_copy.docx** after remaining revisions and comments have been addressed. It preserves the reviewed source and does not silently accept unresolved changes.
- Reference-check request planning, GenAI compatibility and Windows packaging fixes from the preceding build are retained.

Review the final document and its coverage before publication. A completed run or clean copy does not certify scientific accuracy or publication readiness.
