# FilePilot

**Organize smarter. Find what matters.**

FilePilot is a local-first Windows desktop application for understanding crowded folders, finding exact duplicates, and organizing files with a preview before changes. Review storage usage, search your files, and move them into category folders with a verified way back through operation history.

Everything runs on your computer, with no account, cloud processing or telemetry. FilePilot combines a warm-paper light theme and graphite dark theme with forest-green and sage accents, keeping the focus on your files and the decisions you make about them.

## Preview

![FilePilot Dashboard in light mode](assets/screenshots/dashboard-light.png)

Native Qt interface, shown with disposable test files. FilePilot opens with an empty workspace. [View the dark Dashboard](assets/screenshots/dashboard-dark.png).

| Light | Dark |
| --- | --- |
| ![Files in light mode](assets/screenshots/files-light.png) | ![Files in dark mode](assets/screenshots/files-dark.png) |
| ![Exact duplicates in light mode](assets/screenshots/duplicates-light.png) | ![Exact duplicates in dark mode](assets/screenshots/duplicates-dark.png) |

<details>
<summary>See organization, History and Settings</summary>

| Light | Dark |
| --- | --- |
| ![Organization preview in light mode](assets/screenshots/organize-light.png) | ![Organization preview in dark mode](assets/screenshots/organize-dark.png) |
| ![History in light mode](assets/screenshots/history-light.png) | ![History in dark mode](assets/screenshots/history-dark.png) |
| ![Settings in light mode](assets/screenshots/settings-light.png) | ![Settings in dark mode](assets/screenshots/settings-dark.png) |

</details>

## Highlights

- **Read-only folder analysis:** recursive scans, category storage breakdowns, largest files and large/older-file insights.
- **File browsing:** filename search, category and extension filters, size/date sorting, copyable full paths and Show in Explorer.
- **Exact duplicates:** identical-size candidates are verified with chunked SHA-256 hashing. Extra-copy space is reported for review; files are never automatically deleted.
- **Preview before moving:** inspect each source and proposed destination, nested-file restructuring, conflicts and already-organized files.
- **Conflict-safe moves:** explicit confirmation, no overwrites, and skipped existing or proposed filename collisions.
- **Verified Undo:** persistent move history, individual file outcomes, conservative restoration and retries for partial restores.
- **Safe Clear History:** remove only terminal records with nothing left to restore, keeping actionable and retryable operations.
- **Local preferences:** Light/Dark/System themes, review thresholds and editable category destination names.
- **Background work:** scanning, hashing and file operations run off the UI thread; browsing stays available while conflicting actions are disabled.

## Safety by design

- **Scans and previews are read-only.** Duplicate analysis reads file contents and never deletes duplicates.
- **Moves require confirmation.** Existing destinations are never overwritten. Missing, changed, locked or inaccessible files are skipped individually.
- **Operations stay within the selected root.** Category destinations are validated; symbolic links, junctions and other reparse points are skipped, and existing ancestors are checked. Application and data directories are protected.
- **Undo verifies before restoring.** File identity and SHA-256 fingerprints must match. Replaced or modified files and occupied original locations are refused; partial restores stay recorded for retry.
- **Folder cleanup is conservative.** After complete restoration, only verified, empty category directories created by that operation may be removed. Preexisting, nonempty, changed, protected or still-referenced folders remain. Removal is never recursive, and cleanup failures do not change restored-file counts.
- **Interrupted operations remain traceable.** SQLite records intent before each move or restore. Startup recovery checks the journal without moving files; ambiguous items remain available for manual review. Filesystem changes and database commits are not one atomic transaction.
- **Clear History changes only the journal.** It requires confirmation, preserves future Undo and never moves, restores or deletes files or directories.

History is a move journal, not a backup. FilePilot is intended for normal local Windows filesystems; it does not lock every external process against concurrent changes. Rescan when another application is modifying the folder.

## Getting started

Install **Python 3.12 or newer** with the Windows Python launcher, then run these commands in PowerShell:

```powershell
git clone https://github.com/Ankush9740/FilePilot.git
cd FilePilot
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

This source setup requires Python. Packaged Windows builds bundle Python and Qt, so users do not need to install Python. Downloading the source and installing dependencies requires internet access; the application itself runs locally.

Optionally open with a read-only scan:

```powershell
.\.venv\Scripts\python.exe main.py --folder "C:\YourFolder"
```

Developers can follow the [Windows build instructions](packaging/README.md), then run `./packaging/build.ps1`. The application is produced at `dist/FilePilot/FilePilot.exe`; adding `-Installer` with Inno Setup installed produces `dist/installer/FilePilot-Setup-1.0.0.exe`. No published download is available yet.

## How it works

1. **Choose Folder** to scan recursively.
2. Review **Dashboard** and **Files** to understand storage and find what matters.
3. Use **Duplicates > Find duplicates** if you want to compare exact file contents.
4. Open **Organize > Create preview** and review destinations and skipped conflicts. Nested files may be moved into the root's category folders; the preview shows this explicitly.
5. Select **Apply Organization > Move files** to confirm the move. The dialog defaults to Cancel.
6. Select an operation in **History** and use **Undo** when needed. FilePilot verifies each file and refreshes the scan after apply or undo.

**Clear history** optionally removes fully undone or skipped-only terminal records after confirmation. Completed operations with moved files, partial restores and unresolved operations are kept. Clearing records cannot be undone and never changes working-folder contents.

Shortcuts: **Ctrl+O** choose folder, **Ctrl+R** rescan, **Ctrl+F** search files. Cancelled scans must be rescanned before creating an organization preview.

## Privacy

Everything runs locally. There is no telemetry, analytics, upload, account requirement or external API. Filenames, paths, operation metadata and hashes stay on your computer. File contents are streamed only when hashing is needed and are not stored in SQLite. Scan results live in memory and are not persisted.

History and preferences are stored at:

```text
%LOCALAPPDATA%\FilePilot\filepilot.sqlite3
```

Use `--data-dir "C:\YourDevelopmentData"` to isolate development storage. Tests use temporary databases and test-created files.

## Tech stack

- Python 3.12+
- PySide6 / Qt 6
- SQLite and the Python standard library
- pytest and QtTest

## Architecture

The core is independent of Qt. Typed dataclasses represent scans, files, duplicate groups, plans and outcomes. Services handle analysis, preview, apply, undo and recovery; SQLite persists the operation journal and preferences. The Qt shell coordinates native dialogs, shared state and cancellable QThread workers. Model-backed tables support browsing without creating a widget for every row.

```text
FilePilot/
|-- main.py                  # Desktop entry point
|-- pyproject.toml           # Package and test configuration
|-- requirements.txt
|-- filepilot/
|   |-- core/                # Categories, paths and safety primitives
|   |-- models/              # Typed records
|   |-- services/            # Scan, analysis, duplicates, organize and undo
|   |-- database/            # Versioned SQLite journal
|   +-- ui/                  # Pages, shared controls, themes and workers
|-- tests/                   # Core and Qt integration tests
|-- assets/screenshots/      # Native interface captures
|-- docs/                    # Detailed engineering and verification reports
+-- verification/            # Native startup and workflow/UI audits
```

Hashing uses one-megabyte chunks and ignores singleton size groups during duplicate analysis. The journal records move/restore intent and directory provenance. Schema migrations preserve existing history and settings; databases from a newer version are refused rather than modified.

## Testing

Latest verified result: **149 passed, 1 skipped** on Windows with Python 3.14.6, PySide6 6.11.2 and pytest 9.1.1. The skipped case requires Windows Developer Mode or privileges to create symbolic links; separate junction tests pass.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q filepilot main.py tests verification
.\.venv\Scripts\python.exe verification\startup_smoke.py
```

Coverage includes read-only scanning, exact duplicates, conflicts, no-overwrite moves, changed-file refusal, interruption recovery, partial Undo/retry, directory cleanup, transactional Clear History, migrations, settings and UI responsiveness.

Native Windows UI verification covers all six pages in Light/Dark/System at 1440 x 900, 1280 x 800 and 1000 x 680, with the smaller sizes also checked at 125% scaling. The 40-file workflow moved and restored all files with 0 skipped, safely cleaned seven created categories, and cleared the eligible history record without changing files or folders. Compilation and native startup checks passed.

Detailed evidence: [final product review](docs/product-polish-report.md), [safe Undo and directory cleanup](docs/production-readiness-report.md), and [History rendering regression](docs/history-rendering-fix.md).

## Limitations / Roadmap

- Duplicate detection is for review; duplicate deletion is not implemented.
- No filesystem watcher or persistent scan cache. Rescan to pick up changes.
- Organization is limited to the same volume and applies all conflict-free preview rows; selective rows are not yet supported.
- Reported storage uses logical file sizes, which may differ from occupied disk space for hard links, sparse files or compression.

Future work includes signed Windows releases, configurable exclusions, selective organization and larger-scale benchmarking while preserving local, private operation.

