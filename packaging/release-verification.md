# FilePilot 1.0.0 Windows packaging verification

Verified on 2026-10-04. Application behavior and version were not modified.

## Result and approach

The actual **Windows x64 GUI application built and launched successfully**.
PyInstaller uses **onedir with `contents_directory="."`**, without a console,
UPX, elevation, an alternate entry point, or a custom runtime hook. Python and
the required Qt/PySide6 components are included in the distribution.

One-folder starts directly without one-file runtime extraction. The flat
layout preserves the existing `application_directory()` calculation, keeping
the full distribution/install directory protected by the existing safety
policy. Assets retain their `filepilot/ui/assets/` relative paths. The default
database path remains `%LOCALAPPDATA%\FilePilot\filepilot.sqlite3`.

**Inno Setup was not installed.** The installer script is prepared, but installer
compilation, installation, shortcut/uninstall registration and uninstall/data
retention checks could not be executed. No setup EXE is claimed or present.
Install the official **Inno Setup compiler**, reference version **6.7.3**, from
[JRSoftware](https://jrsoftware.org/isdl.php), then run the installer build below.
No system software was installed by this task.

## Files added or modified

Modified:

- `.gitignore`: ignore the isolated `.venv-build/`; existing `build/`, `dist/`,
  `.uv-cache/` and bytecode rules already cover generated outputs/caches.
- `README.md`: minimal developer build link/command, output locations,
  bundled-Python explanation and signing roadmap update. The public design and
  source workflow remain intact; no release download link was added.

Added:

- `packaging/requirements-windows.txt`: exact build-only dependency pins.
- `packaging/FilePilot.spec`: checked-in production PyInstaller configuration.
- `packaging/version_info.txt`: executable product/file metadata at 1.0.0.
- `packaging/generate_icon.py`: reproducible conversion from the existing SVG.
- `packaging/assets/FilePilot.ico`: seven-resolution Windows icon.
- `packaging/build.ps1`: repository-relative build, safe cleanup, output checks,
  optional Inno compilation and clear artifact paths.
- `packaging/FilePilot.iss`: per-user installer/uninstaller configuration.
- `packaging/verify_package.py`: focused PE/content checks and real-EXE smoke
  harness with disposable storage and fixture files.
- `packaging/README.md`: detailed audit, prerequisites, build and verification.
- `packaging/release-verification.md`: this report.

No files under `filepilot/`, `tests/`, existing `verification/` scripts, `docs/`
or `assets/` were changed. A before/after comparison of 76 existing non-generated
files in those trees found no byte changes or added files. `main.py`,
`pyproject.toml` and `requirements.txt` are also unchanged.

## Configuration and reproducibility

Reference toolchain:

| Component | Version |
| --- | --- |
| Windows | Windows 11, build 26200 |
| CPython | 3.14.6 x64 |
| PyInstaller | 6.22.3 |
| PyInstaller hooks | 2026.8 |
| PySide6 / Qt | 6.11.2 |
| Application | 1.0.0 |

The root `main.py` launcher calls `filepilot.main:main`. The spec collects all
seven SVGs, explicitly includes `PySide6.QtSvg` for its dynamically loaded SVG
engines, and lets the standard Qt hooks collect the Windows platform and
imported Qt runtime. It excludes pytest, test/verification packages, alternative
Qt bindings and tkinter. It does not collect repository screenshots or docs.

The build uses exact separate dependency pins and checks them before cleaning
or compiling. Repeat icon generation produced identical bytes. The final build
also succeeded when invoked by absolute path with the working directory set to
`packaging/`, confirming no dependency on `C:\FilePilot` as a hardcoded location
or the current directory. Repeatable build inputs do not promise byte-identical
EXEs across interpreter/compiler/Windows versions or timestamps.

Cleanup is confined to marked, packaging-owned output directories. Existing
unmarked destinations and reparse points are refused. Whole `build/`/`dist/`
trees and user data are never deleted. All invoked tools use resolved paths;
the builder's PATH is temporarily isolated and restored afterward.

## Icon and executable metadata

`generate_icon.py` renders the unchanged original FilePilot SVG through Qt's
pinned SVG renderer at **16, 24, 32, 48, 64, 128 and 256 px**. It encodes small
images as 32-bit BGRA DIBs with transparency masks and the 256px image as PNG.
No resizing from a small raster, logo redesign or extra imaging dependency is
used. Qt loaded the ICO and reported all seven resolutions.

ICO SHA-256:

```text
1af7e62a7b84a48074a110037c223eb07259137ba80db8e3628b528962b21acc
```

The actual executable resources passed checks for:

- ProductName and FileDescription: `FilePilot`.
- FileVersion and ProductVersion: `1.0.0` (numeric resource 1.0.0.0).
- OriginalFilename: `FilePilot.exe`.
- Embedded icon and icon-group resources.
- x64 PE machine and Windows GUI subsystem 2.
- `asInvoker` execution manifest, with no administrator request.

No company/publisher was invented. The binary is unsigned.

## Build commands and artifacts

Prepare a separate development/build environment from the repository root:

```powershell
py -3 -m venv .venv-build
.\.venv-build\Scripts\python.exe -m pip install -r packaging\requirements-windows.txt
.\packaging\build.ps1
```

The verified executable is:

```text
C:\FilePilot\dist\FilePilot\FilePilot.exe
```

Distribute the **entire `dist/FilePilot/` tree**, not the EXE alone. The final
uncompressed distribution contains 221 files, about 156.2 MiB including its
local build ownership marker. Installer collection excludes that marker.

Final EXE SHA-256:

```text
8b4928bd0499698e31a1600dcba079c2cc675e8609f03e5bd25f9af90361dc2d
```

When Inno Setup is available:

```powershell
.\packaging\build.ps1 -Installer
```

Expected installer location after successful compilation:

```text
C:\FilePilot\dist\installer\FilePilot-Setup-1.0.0.exe
```

That installer file **does not exist yet**. The script supports `-IsccPath` for
a custom compiler location and never downloads/installs Inno itself.

## Actual packaged application verification

The verification harness ran the release EXE, not source Python. It set a
disposable `LOCALAPPDATA`, passed a two-file fixture with `--folder`, removed
development Python/Qt environment variables and used a **System32-only PATH**.
It did not pass `--data-dir`, so default persistence resolution was exercised.

Native inspection used the Windows computer-use skill at a **1280 x 800 client
size**. On the final flat-layout build:

- The main window appeared, and the application/title-bar icon loaded.
- Dashboard, Files, Duplicates, Organize, History and Settings all opened in Light.
- Dark and System selections saved and rendered correctly in Settings. System
  followed the host's dark appearance; no Windows appearance setting was changed.
- File filter/table arrows in Light and settings spin arrows in Dark rendered;
  the SVG runtime/assets were available. No page redesign or clipping was seen.
- The folder picker opened in the packaged process and was cancelled safely.
- The fixture scan completed: **2 files, 61 bytes**, with no changes to contents.
- The default SQLite database appeared under the disposable
  `LOCALAPPDATA/FilePilot/`, outside the distribution, with empty operation history.
- Process module inspection showed Python, Qt and SVG/platform plugins loaded
  from `dist/FilePilot/`, and `icuuc.dll` loaded from Windows System32.
- The final GUI exited with **code 0**, captured stdout/stderr was empty, fixture
  contents were unchanged, and temporary verification storage was removed.

The test host has Python installed, but the executable ran without Python on
its PATH and used bundled Python DLLs. A separate clean Windows machine with
no Python/Qt installation was not available; that acceptance check remains
recommended before publication. Empty stderr alone is not proof against all
windowed Qt diagnostics; visible native inspection also passed.

## Packaging risks found and resolved

1. **SVG runtime collection:** assets load through Qt image/icon engines rather
   than explicit QtSvg calls. Explicit QtSvg analysis collects both engines;
   actual SVG icons and control arrows rendered in the packaged window.
2. **Build PATH contamination:** the first build copied an incompatible
   third-party `icuuc.dll` from an unrelated tool on PATH. Native startup failed
   importing QtCore. Source process inspection showed Qt uses Windows System32
   ICU. The build now isolates PATH, the spec excludes unversioned ICU DLLs, and
   the package verifier rejects them. Final startup and loaded-module checks pass.
3. **Application-directory protection:** default `_internal/` placement would
   make the existing module-relative protection cover only the runtime folder.
   Flat onedir preserves protection of the full distribution without modifying
   safety/scanner logic or adding runtime patches.

`warn-FilePilot.txt` was reviewed. Remaining entries are optional non-Windows
modules (`pwd`, `grp`, `fcntl`, etc.) and frozen/import aliases. The Python 3.14
`collections.abc` entry maps to `_collections_abc`; that module is in the bundled
base library and actual application imports/scan passed. No required packaging,
import or resource error remained in the final startup check.

## Installer status and intended behavior

Inno Setup detection covered PATH, common Program Files/per-user paths and
HKCU/HKLM uninstall registry entries. It was absent. No installer compilation,
installation, Start Menu/Desktop shortcut check, uninstall registry check or
test uninstall was performed. Those results are pending, not passed.

The checked-in configuration installs the full flat distribution under
`{localappdata}\Programs\FilePilot`, uses `PrivilegesRequired=lowest`, a Start
Menu shortcut, an optional unchecked Desktop shortcut, stable AppId and standard
uninstall support. It does not modify PATH, associations, shell extensions or
services, perform network steps or remove `{localappdata}\FilePilot` data.
These settings require compiled-installer verification before claiming they
have passed an actual install/uninstall cycle.

## Tests, static checks and repository hygiene

- Full existing suite: **149 passed, 1 skipped in 135.16 seconds** on the final
  packaging refinement. The skipped symlink case requires Windows Developer
  Mode/privileges. No existing test was edited, removed or weakened.
- Compilation: `compileall` passed for `filepilot`, root launcher, tests,
  verification scripts and packaging scripts.
- PowerShell build script: AST parsing passed with no errors.
- Existing native source startup smoke: Windows platform, 2 files, database
  created, empty history; passed.
- Focused new packaging checks are in `verify_package.py`, invoked by every
  build. They validate actual artifacts and a separate real-EXE smoke, so they do
  not change the pytest case count.
- `git diff --check` passed. Git emitted its existing LF-to-CRLF conversion
  notices; no Git configuration was changed.
- `git check-ignore` confirmed build/dist/cache/venv outputs ignored and required
  packaging configuration/icon files unignored.
- Final status: modified `.gitignore` and `README.md`; the ten new packaging
  files listed above are untracked. No binaries were staged or committed.

No commit, push, tag, GitHub Release, publication, upload or installer build was
performed. Scanning, duplicates, SHA-256, moves, organization, Undo, History,
cleanup, database provenance, settings and UI application code were unchanged.
The user's actual FilePilot history was never opened or modified by verification.

## Remaining release limitations

The application and future installer are unsigned. Downloaded unsigned or
unrecognized applications may show Windows publisher/SmartScreen warnings.
Signing is a separate release step, and signing alone does not guarantee instant
SmartScreen reputation; see [Microsoft's developer guidance](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/smartscreen-reputation).
Installer compilation/installation verification and a clean-machine test remain
pending. Windows x64 is the built/verified target; native ARM64 and older Windows
versions were not tested. Nothing was published.
