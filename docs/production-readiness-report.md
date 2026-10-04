# FilePilot production-readiness audit

Verified on Windows on 2026-10-04 with Python 3.14.6, PySide6 6.11.2, and pytest 9.1.1. This pass fixes empty category folders after undo and audits the approved application without redesigning it. All filesystem mutations used disposable fixtures and temporary databases. The user's working folders and normal LocalAppData database were not used.

## 1. Changes

Organization now journals category-directory provenance. After complete, durable file restoration, undo attempts conservative cleanup of that operation's verified empty directories. Cleanup errors are separate from file restoration counts and cannot roll back successful restores. History renders `Skipped`, `Restore skipped`, and `Partial restore` consistently; `Moved`, `Restored`, `Completed`, and `Undone` remain clear. Fully undone operations show `No moves to undo` with the action disabled.

## 2. Exact source and documentation inventory

Modified:

| File | Change |
| --- | --- |
| `filepilot/database/store.py` | Additive schema migration, provenance journal, shared-operation checks and cleanup writer guard |
| `filepilot/services/organizer.py` | Exclusive category creation and conservative post-restore cleanup |
| `filepilot/ui/pages/history.py` | Outcome/status text only |
| `tests/test_organizer.py` | Schema-version expectation and cancellation/cleanup regression |
| `tests/test_ui.py` | Cleanup assertions and two History regression tests |
| `README.md` | Accurate cleanup, schema and verification documentation |

Added:

| File | Purpose |
| --- | --- |
| `tests/test_directory_cleanup.py` | 31 cleanup/provenance regression cases |
| `tests/test_migrations.py` | Four compatibility/rollback/idempotence cases |
| `verification/production_audit.py` | Real native workflow, independent hashes, confirmations, navigation and exact restoration audit |
| `docs/production-readiness-report.md` | This report |

Generated evidence is under `verification/output`: `production-baseline.json`, `production-preservation.json`, `production-audit/` (JSON and six screenshots), `refinement-native/` (JSON and 123 screenshots, including contact sheets), and `native-startup.png`. Existing verification scripts were reused unchanged.

## 3. Persistent ownership and migration

SQLite schema version 2 adds `operation_directories`, keyed by operation ID and path. It records state, device, inode, creation timestamp where available, and cleanup error. Creation intent (`creating`) is committed before an exclusive `mkdir()` with neither `parents=True` nor `exist_ok=True`. Successful creation records `created` and filesystem identity. An already-existing path records `existing`; that operation never owns it. Cleanup records `removed` or `missing`.

The version-1-to-2 migration adds only this table and updates `PRAGMA user_version` within a transaction. Existing operations, item records, settings and file counts are preserved. Failed migration rolls back both table creation and version change. Legacy operations receive no guessed ownership. An interruption between mkdir and ownership recording leaves uncertain intent, so the folder remains. Startup recovery continues to make no filesystem changes. Newer schema versions are still refused.

## 4. Exact removal rules

Undo first performs the existing identity/content/occupied-path checks and restores files without overwriting. It persists the final file state before considering cleanup. Cleanup runs only when no moved, restore-skipped or restoring items remain and at least one file has been restored. Partial undo conservatively retains all created folders until file restoration completes.

A candidate must have a durable `created` row for that operation, be a direct category child of the selected working root, and pass the existing protected-path, confinement, ancestor and reparse-point policy. Immediately before removal, its real-directory identity must match the recorded device, nonzero inode and available birth timestamp. Replaced directories are retained.

Other operations' unfinished file intents are checked against both their original and destination paths, including descendants. A SQLite `BEGIN IMMEDIATE` writer guard spans this check, the final safety/identity validation, `rmdir()` and the cleanup completion write. Instances sharing the same journal cannot publish another intent between validation and removal.

The only deletion primitive is `Path.rmdir()`. Its atomic emptiness requirement preserves normal files, hidden files, and even empty child folders. There is no recursive deletion. Preexisting, unrelated, legacy, uncertain, nonempty, shared, changed, protected and reparse-point directories are retained. Cancellation stops further cleanup. Removal or journal errors produce an issue and best-effort journal note, while restored counts and `Undone` status stay accurate. Filesystem/database changes are not one atomic transaction; an unrecorded completed removal can be reconciled as `missing` on a service retry.

## 5. Tests added

38 cases were added: 31 directory cases (including parametrization), four migrations, one apply-cancellation case and two UI History cases. Existing tests were preserved; only the expected supported schema version changed from 1 to 2, with the future-version refusal test retained.

Coverage includes all five requested scenarios: created folder removed; preexisting folder retained; new unrelated contents retained; partial undo retained; and multiple operations safely sharing destinations. Additional cases cover hidden contents, empty child folders, partial retry, original-path references, replacement before and during the reference check, writer serialization, permission failures, cleanup query/completion failures, new contents arriving at removal, cancellation, missing/unverifiable identity, uncertain creation after interruption, invalid paths, protected paths, and a Windows junction replacement. Migration tests cover exact legacy history/preferences preservation, legacy undo, new operations after migration, real SQLite authorizer-induced rollback, and repeated reopening.

## 6. Complete test results and workflow audit

Final full suite: **117 passed, 1 skipped in 95.30s (0:01:35)**. The sole skip is `tests/test_analysis.py:90`: creating symbolic links requires Windows Developer Mode or privileges. Windows junction tests pass. The cleanup/migration/organizer subset passed **70 tests in 5.20s**; the standalone Qt suite passed **18 tests in 80.04s**. No existing test was removed, weakened or newly skipped.

The native production audit used 40 files / 251.5 MB, nested folders, duplicates with different names, a Windows-hidden file, large files and long values. It exercised the Choose Folder entry point, three recursive scans, search/category/large/older filters, size/date sorting, two duplicate analyses verified against independent SHA-256 hashes, two previews, actual native confirmation dialogs, apply, History, undo, automatic rescan and persisted Settings. Folder selection was directed to the disposable fixture using a deterministic picker stub; both mutation confirmations were real QMessageBoxes with Cancel as default.

Read-only stages preserved the file/folder snapshot. Apply moved 40 files. Undo restored 40, skipped 0, left 0 remaining, removed 7 owned categories, preserved the preexisting category and unrelated empty folder, and exactly restored original file contents, paths, sizes, modification times, Windows attributes and folder tree. During actual hashing/move/restore workers, 53 rapid page-navigation events succeeded. Settings persisted. There were no Qt messages or error notices.

The full suite additionally exercises filename/destination conflicts, different contents with identical filenames, inaccessible and missing paths, Unicode, zero-byte files, modified source/destination content, no-overwrite moves/restores, cancellation, interrupted recovery, confinement and traversal. Duplicate analysis and scanning remain read-only; SHA-256 remains authoritative. No network, telemetry, upload or duplicate-deletion behavior was added.

Evidence: `verification/output/production-audit/report.json`.

## 7. Compilation and static checks

`python -m compileall -q filepilot main.py tests verification` passed. Every application, test and verification Python file also passed AST parsing. SHA-256 baseline comparisons constrain existing application changes to the organizer, database store and History labels; all other application files match the pre-audit baseline. Package configuration and dependency requirements are unchanged. Source inspection confirms cleanup uses only nonrecursive `rmdir()` and introduces no networking imports. No packaging build, installer or release was requested or produced.

Evidence: `verification/output/production-preservation.json`.

## 8. Native startup

The real desktop entry point passed `verification/startup_smoke.py` on Qt's `windows` platform with an isolated database and two read-only fixture files. Database creation succeeded, the scan found both files, and initial History was empty. The production audit separately exercised the native GUI at 1280×800 logical pixels and device pixel ratio 1.25.

## 9. UI regression

The current native matrix covers all six pages in Light, Dark and System at 1440×900, 1280×800 and 1000×680: 123 captures, zero geometry errors and zero Qt messages. All nine page contact sheets were visually reviewed, plus representative minimum-size scroll positions, Settings bottom, empty states, long-value details and confirmations. Tables intentionally elide long values while full details/tooltips remain available. Dashboard summary values stay visible during scrolling. History shows partial restore and retry correctly, followed by an accurate fully undone state.

The full matrix used process-local scaling to obtain device pixel ratio 1.0 on the available 1080p monitor; no Windows display setting was changed. The separate final production workflow ran at the normal 1.25 ratio. Existing Qt tests verify keyboard navigation/focus, tooltips/copyable details, disabled conflicting actions, loading/background browsing, System palette behavior, success/error feedback and responsive empty states. No layout, palette, icon, theme, shell, state or worker source changed.

Evidence: `verification/output/refinement-native/report.json`, contact sheets and `production-audit/history-after-cleanup.png`.

## 10. Remaining limits and manual verification

Legacy or uncertain directory ownership is intentionally retained. Partial/cancelled undo, shared operations, changed identities, permissions or cleanup-journal errors can leave folders in place without misreporting file restoration. A shared folder may remain after another operation finishes; there is no background garbage collector. The organizer service can retry cleanup on an already-restored operation, but the GUI correctly disables Undo when no files remain and adds no cleanup-only action.

The writer guard coordinates instances using the same SQLite database. It cannot lock unrelated external filesystem processes or instances using different journals. The established local-filesystem threat model remains: final path/identity checks reduce races, and `rmdir()` always refuses contents, but the app does not claim protection against deliberate concurrent path substitution. Long paths remain subject to the existing Windows/filesystem configuration. The requested size matrix passed; this is not an installer/signing or every-monitor certification.

The workspace is ready for final manual verification using `python main.py` and a disposable user-selected folder. That normal launch will migrate an existing local v1 database; automated migration verification used temporary databases only.

## 11. Stable architecture preserved

SHA-256 comparison confirms all unrelated application files are byte-for-byte unchanged, including the approved warm-paper/forest-green palette, layouts, navigation, scanner, duplicate verification, safety primitives, dataclasses, settings UI, QThread workers and shell. Only directory provenance/cleanup, the additive store migration and History wording changed. Preview-first confirmation, local SQLite persistence, read-only scanning, no-overwrite file operations and chunked SHA-256 hashing retain their existing architecture. No new dependencies were installed. Git was not initialized; no commit, push, release or installer was created.
