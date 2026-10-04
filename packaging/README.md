# FilePilot 1.0.0 Windows packaging

The release is a **Windows x64, one-folder PyInstaller application** wrapped by a
per-user Inno Setup installer. The complete folder contains Python and Qt; users
do not need Python, an account, administrator privileges, or internet access to
run it. Keep `FilePilot.exe` and all companion files/directories together. Do not distribute the EXE
alone. The source launch workflow and application version remain unchanged.

## Audit and design

- `main.py` calls `filepilot.main:main`. The production build uses that launcher,
  with no alternate application entry point, verification hook, or runtime patch.
- The icon and theme chevrons resolve relative to module `__file__`. The spec
  mirrors `filepilot/ui/assets/*.svg` inside the distribution, preserving those paths.
- `contents_directory="."` uses a flat one-folder layout. The existing
  `application_directory()` then resolves to the full distribution/install root,
  preserving its safety protection for every application file. The default
  `_internal/` layout would protect only that nested runtime directory.
- The default database stays at `%LOCALAPPDATA%\FilePilot\filepilot.sqlite3`.
  The installer uses `%LOCALAPPDATA%\Programs\FilePilot`; these are separate paths.
- One-folder avoids repeated runtime extraction and temporary execution paths.
  It is easier to inspect and diagnose, and starts directly from installed files.
- PyInstaller's PySide6 hooks collect the imported Qt components and Windows
  platform plugin. Explicit `PySide6.QtSvg` collection includes the dynamically
  loaded SVG image/icon engines. The spec enables neither UPX nor admin elevation.
- The build isolates PATH and excludes unversioned ICU DLLs. These Qt wheels
  use Windows' native ICU; an unrelated third-party `icuuc.dll` with incompatible
  exports must not shadow it. The package verifier rejects this contamination.
- Runtime dependencies are unchanged. `requirements-windows.txt` pins the build
  tools and Qt wheels separately from normal source requirements. No tests,
  screenshots, verification scripts, repository files or development tools are
  intentionally collected.

## Build environment

Use Windows 10 (1809+) or Windows 11 and **x64 Python 3.12+**. The reference build
uses CPython **3.14.6 x64**, PyInstaller **6.22.3**, hooks **2026.8** and
PySide6 **6.11.2**. Prefer the same interpreter and exact pins for repeat builds.
Build Windows artifacts on Windows; PyInstaller is not a cross compiler.

From the repository root in PowerShell:

```powershell
py -3 -m venv .venv-build
.\.venv-build\Scripts\python.exe -m pip install -r packaging\requirements-windows.txt
.\packaging\build.ps1
```

The script also works when invoked by its full path from another directory.
`-Python "C:\Path\To\python.exe"` selects another prepared x64 environment.
The script validates dependency pins before building; it does not silently
install dependencies or system software. If local script policy prevents running
it, a process-scoped invocation is:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\packaging\build.ps1
```

No system execution policy is changed. Build/download access is required only
when preparing the toolchain; the resulting application has no runtime network
dependency. Build output remains unsigned.

## Outputs and safe cleanup

- Application: `dist/FilePilot/FilePilot.exe` with the complete `dist/FilePilot/` tree.
- Installer: `dist/installer/FilePilot-Setup-1.0.0.exe` when compiled.
- PyInstaller analysis/warnings/cache: `build/filepilot-packaging/`.

Only `build/filepilot-packaging/`, `dist/FilePilot/`, and, when requested,
`dist/installer/` are cleaned. Existing destinations must contain the ownership
marker written by this build script. Unmarked directories and reparse points
are refused. The script never deletes `build/` or `dist/` wholesale and does not
clean user data, source files, virtual environments, or unrelated outputs. Do
not keep unrelated files inside these marked, disposable output directories.
All generated directories and `.venv-build/` are ignored by Git. Packaging
configuration and the ICO remain checked-in source assets.

## Icon and version resources

The identity source is the unchanged `filepilot/ui/assets/filepilot.svg`.
`generate_icon.py` uses the pinned Qt SVG renderer to render each size directly
on a transparent surface: **16, 24, 32, 48, 64, 128, 256** pixels. It assembles a
standard ICO using 32-bit BGRA DIB images with transparency masks for the smaller
sizes and PNG for 256px. There is no resampling, logo redesign, or image service.
The forest-green/warm-paper colors come directly from the original SVG.

```powershell
.\.venv-build\Scripts\python.exe packaging\generate_icon.py
```

Repeated generation with the reference toolchain produces identical ICO bytes.
The spec embeds it and `version_info.txt` into the executable, with ProductName
and FileDescription `FilePilot`, FileVersion and ProductVersion `1.0.0`, and
OriginalFilename `FilePilot.exe`. No company or publisher identity is invented.
The spec refuses an unexpected project version rather than silently producing
an installer with mismatched metadata.

## Inno Setup

Install the official **Inno Setup compiler** separately from
[JRSoftware's download page](https://jrsoftware.org/isdl.php). The reference
configuration targets **Inno Setup 6.7.3** (ISCC.exe). The application can be
built and inspected even when this prerequisite is absent; no installer is
claimed until compilation succeeds.

```powershell
.\packaging\build.ps1 -Installer
```

The script searches PATH, common installations and uninstall registry entries.
For a custom installation:

```powershell
.\packaging\build.ps1 -Installer -IsccPath "C:\Path\To\Inno Setup\ISCC.exe"
```

`FilePilot.iss` installs the EXE and complete distribution tree, without build
ownership markers. It uses a stable AppId, `PrivilegesRequired=lowest`, per-user
Programs storage, a Start Menu shortcut and an optional, unchecked Desktop
shortcut. Standard uninstall removes installed files and shortcuts. It never
deletes `%LOCALAPPDATA%\FilePilot` history/preferences. No PATH change, file
association, shell extension, startup service, telemetry or network step exists.
Compression is normal LZMA2 without solid compression. Windows ARM64 may run
the x64 package through OS emulation; native ARM64 is not built or verified.

## Verification

`build.ps1` checks the actual PE GUI subsystem, x64 architecture, icon and version
resources, asInvoker manifest, SQLite/Python runtime, Qt plugins and identical
SVG assets. To launch the actual distribution for a native smoke test:

```powershell
.\.venv-build\Scripts\python.exe packaging\verify_package.py --launch
```

This creates a disposable default `LOCALAPPDATA` and two-file read-only scan
fixture, removes development Python/Qt environment variables, and launches with
a system-only PATH. Inspect all six pages, Light/Dark/System, folder selection,
asset rendering and the completed scan. Close the window to complete the test.
The harness checks a clean process exit, no captured startup diagnostics, empty
operation history, and unchanged fixture contents. The temporary directory is
removed; real FilePilot data is never used. Empty diagnostics alone cannot
prove the absence of every internal error in a windowed process, so visible
startup and controls must also be checked. The harness does not install Python
on an end-user machine or alter the host's Python installation.

Regression checks use the existing source test environment:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q filepilot main.py tests verification packaging
.\.venv\Scripts\python.exe verification\startup_smoke.py
```

Before distributing a compiled installer, use a disposable install directory,
shortcut name/group and an isolated `LOCALAPPDATA` for the launched application.
Verify installed startup, shortcut targets, HKCU uninstall registration, then
uninstall that test installation. Confirm binaries/shortcuts are removed and
the isolated data directory survives. Do not overwrite or uninstall an existing
production FilePilot installation. Installation/uninstallation have not been
verified when the Inno compiler is unavailable; see `release-verification.md`.

## Release limits

Pinned dependencies and scripts make the process repeatable, not a promise of
bit-for-bit identical EXEs/installers across Python/Windows/compiler versions
or timestamps. Capture the interpreter/compiler versions with each release.
The unsigned application/installer can trigger Windows SmartScreen or publisher
warnings; code signing requires a real certificate and a separately authorized
signing process. A fresh Windows machine without Python and any installed Qt
remains a useful final release acceptance environment.

References: [PyInstaller runtime asset paths](https://pyinstaller.org/en/stable/runtime-information.html),
[one-folder operation](https://pyinstaller.org/en/stable/operating-mode.html),
and [Inno Setup non-admin privileges](https://jrsoftware.org/ishelp/topic_setup_privilegesrequired.htm).
