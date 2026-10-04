# Build with packaging/build.ps1 on Windows x64. Preserve package-relative assets.
from pathlib import Path
import tomllib

ROOT = Path(SPECPATH).parent
version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
if version != "1.0.0":
    raise ValueError("Update the release configuration deliberately before changing version")

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[(str(path), "filepilot/ui/assets")
           for path in sorted((ROOT / "filepilot/ui/assets").glob("*.svg"))],
    # Qt's SVG icon/image engines load dynamically; this activates the QtSvg hook.
    hiddenimports=["PySide6.QtSvg"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "tests", "verification", "tkinter", "PyQt5", "PyQt6", "PySide2"],
    noarchive=False,
    optimize=0,
)
# These pinned Qt wheels import Windows' ICU API. A third-party ICU on the
# builder's PATH can share these filenames but export incompatible symbols.
# Use the supported Windows OS component; never redistribute a stray ICU DLL.
a.binaries = [entry for entry in a.binaries
              if Path(entry[0]).name.lower() not in {"icuuc.dll", "icuin.dll", "icudt.dll"}]
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="FilePilot",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=str(ROOT / "packaging/assets/FilePilot.ico"),
    version=str(ROOT / "packaging/version_info.txt"),
    uac_admin=False,
    uac_uiaccess=False,
    # application_directory() derives the protected root from module __file__.
    # Flat onedir keeps that root equal to the full distribution/install folder.
    contents_directory=".",
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="FilePilot")
