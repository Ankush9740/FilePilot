"""Verify release contents and optionally smoke the real GUI executable.

--launch uses a disposable LOCALAPPDATA and read-only fixture, never real history.
The GUI remains open for native page/theme inspection; close it to finish the check.
"""
from __future__ import annotations

import argparse
import ctypes
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import struct
import subprocess
import tempfile
import time

import pefile

ROOT = Path(__file__).resolve().parents[1]


def verify(exe: Path) -> dict:
    exe = exe.resolve(strict=True)
    bundle = exe.parent
    pe = pefile.PE(str(exe))
    assert pe.FILE_HEADER.Machine == 0x8664, "Expected x64 executable"
    assert pe.OPTIONAL_HEADER.Subsystem == 2, "Expected Windows GUI subsystem, no console"
    versions = {}
    for group in pe.FileInfo:
        for entry in group:
            if entry.Key == b"StringFileInfo":
                for table in entry.StringTable:
                    versions.update({key.decode(): value.decode() for key, value in table.entries.items()})
    expected = {"ProductName": "FilePilot", "FileDescription": "FilePilot",
                "FileVersion": "1.0.0", "ProductVersion": "1.0.0", "OriginalFilename": "FilePilot.exe"}
    assert all(versions.get(key) == value for key, value in expected.items()), versions
    resource_types = {entry.id for entry in pe.DIRECTORY_ENTRY_RESOURCE.entries}
    assert {3, 14}.issubset(resource_types), "Missing Windows icon resources"
    manifest_entry = next(entry for entry in pe.DIRECTORY_ENTRY_RESOURCE.entries if entry.id == 24)
    manifest_data = manifest_entry.directory.entries[0].directory.entries[0].data.struct
    manifest = pe.get_data(manifest_data.OffsetToData, manifest_data.Size)
    assert b'asInvoker' in manifest and b'requireAdministrator' not in manifest
    pe.close()
    assets = ROOT / "filepilot/ui/assets"
    for source in assets.glob("*.svg"):
        assert (bundle / "filepilot/ui/assets" / source.name).read_bytes() == source.read_bytes(), source.name
    required = ["Qt6Core.dll", "Qt6Gui.dll", "Qt6Widgets.dll", "Qt6Svg.dll", "qwindows.dll",
                "qsvg.dll", "qsvgicon.dll", "_sqlite3.pyd"]
    contents = list(bundle.rglob("*"))
    names = {path.name for path in contents if path.is_file()}
    assert not {"icuuc.dll", "icuin.dll", "icudt.dll"}.intersection(name.lower() for name in names), \
        "Do not bundle third-party ICU DLLs over Windows' system ICU"
    assert all(name in names for name in required), sorted(set(required) - names)
    assert any(name.startswith("python3") and name.endswith(".dll") for name in names)
    assert not {"pytest", "tests", "verification", "docs", "screenshots", ".git", ".venv"}.intersection(
        path.name for path in contents if path.is_dir()), "Development content found in distribution"
    icon = (ROOT / "packaging/assets/FilePilot.ico").read_bytes()
    assert struct.unpack_from("<HHH", icon) == (0, 1, 7)
    assert tuple((struct.unpack_from("<BBBBHHII", icon, 6 + i * 16)[0] or 256)
                 for i in range(7)) == (16, 24, 32, 48, 64, 128, 256)
    return {"exe": str(exe), "sha256": hashlib.sha256(exe.read_bytes()).hexdigest(),
            "subsystem": "Windows GUI", "architecture": "x64", "version": versions,
            "assets": "7 SVGs identical to source", "qt_plugins": "Windows + SVG present",
            "python": "bundled runtime", "privileges": "asInvoker"}


def launch(exe: Path, timeout: int) -> dict:
    with tempfile.TemporaryDirectory(prefix="filepilot-package-") as temporary:
        base = Path(temporary)
        local = base / "LocalAppData"
        local.mkdir()
        fixture = base / "scan-fixture"
        fixture.mkdir()
        for name, content in (("read-only.txt", b"FilePilot packaged scan fixture"),
                              ("picture.png", b"Metadata fixture, not an image")):
            (fixture / name).write_bytes(content)
        originals = {path.name: path.read_bytes() for path in fixture.iterdir()}
        environment = os.environ.copy()
        environment["LOCALAPPDATA"] = str(local)
        # Do not inherit a development Python/Qt installation through PATH or env.
        system_buffer = ctypes.create_unicode_buffer(32768)
        assert ctypes.windll.kernel32.GetSystemDirectoryW(system_buffer, len(system_buffer))
        system_directory = Path(system_buffer.value)
        environment["SystemRoot"] = str(system_directory.parent)
        environment["PATH"] = str(system_directory)
        for key in tuple(environment):
            if key.startswith(("PYTHON", "QT_", "PYSIDE", "VIRTUAL_ENV")):
                environment.pop(key)
        log_path = base / "startup.log"
        with log_path.open("wb") as log:
            process = subprocess.Popen([str(exe), "--folder", str(fixture)], cwd=base,
                                       env=environment, stdout=log, stderr=log)
            try:
                database = local / "FilePilot/filepilot.sqlite3"
                deadline = time.monotonic() + 120
                while not database.exists() and process.poll() is None and time.monotonic() < deadline:
                    time.sleep(0.1)
                assert database.exists(), "Packaged app did not create its isolated default database"
                assert process.poll() is None, "Packaged app exited during startup"
                print(json.dumps({"pid": process.pid, "isolated_default_database": str(database),
                                  "fixture": str(fixture), "runtime_path": environment["PATH"],
                                  "action": "Inspect all six pages and Light/Dark/System, then close FilePilot."}), flush=True)
                code = process.wait(timeout=timeout)
                assert code == 0, f"Packaged GUI exited with code {code}"
                with closing(sqlite3.connect(database)) as connection:
                    table_names = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")]
                    assert "operations" in table_names
                    assert connection.execute("SELECT COUNT(*) FROM operations").fetchone()[0] == 0
                assert {path.name: path.read_bytes() for path in fixture.iterdir()} == originals
                assert not log_path.read_bytes(), f"Startup diagnostics: {log_path.read_text(errors='replace')}"
                return {"launch": "passed", "exit_code": code, "isolated_default_database": True,
                        "real_history_used": False, "read_only_fixture_unchanged": True,
                        "startup_stdout_stderr": "empty", "python_on_child_path": False}
            finally:
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=10)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, default=ROOT / "dist/FilePilot/FilePilot.exe")
    parser.add_argument("--launch", action="store_true")
    parser.add_argument("--timeout", type=int, default=900)
    args = parser.parse_args()
    result = verify(args.exe)
    print(json.dumps(result, indent=2), flush=True)
    if args.launch:
        result.update(launch(args.exe.resolve(), args.timeout))
        print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
