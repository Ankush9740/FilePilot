import os
from pathlib import Path
from threading import Event

import pytest

from filepilot.core.categories import Category, classify, human_size
from filepilot.core.safety import SafetyError, SafetyPolicy
from filepilot.models.records import Settings
from filepilot.services.analysis import analyze
from filepilot.services.duplicates import find_duplicates
from filepilot.services.scanner import Scanner


@pytest.mark.parametrize("name,expected", [
    ("REPORT.PDF", Category.DOCUMENTS), ("photo.jpeg", Category.IMAGES),
    ("video.mkv", Category.VIDEOS), ("song.flac", Category.AUDIO),
    ("bundle.tar.gz", Category.ARCHIVES), ("setup.msi", Category.INSTALLERS),
    ("app.tsx", Category.CODE), ("README", Category.OTHER),
    ("strange.xyz", Category.OTHER),
])
def test_categories(name, expected):
    assert classify(name) == expected


@pytest.mark.parametrize("size,expected", [
    (0, "0 B"), (1, "1 B"), (1023, "1023 B"), (1024, "1.0 KB"),
    (1536, "1.5 KB"), (1024 ** 2, "1.0 MB"), (1024 ** 3, "1.0 GB"),
    (1024 ** 4, "1.0 TB"), (-1, "0 B"),
])
def test_sizes(size, expected):
    assert human_size(size) == expected


def test_scan_read_only_nested_and_metadata(tmp_path):
    (tmp_path / "nested").mkdir()
    file = tmp_path / "nested" / "notes.txt"
    file.write_bytes(b"hello")
    (tmp_path / "empty.bin").touch()
    before = file.stat()
    result = Scanner(SafetyPolicy()).scan(tmp_path)
    assert len(result.files) == 2 and result.total_size == 5
    record = next(f for f in result.files if f.name == "notes.txt")
    assert record.path == file and record.category == Category.DOCUMENTS
    assert record.modified_ns == before.st_mtime_ns
    assert record.created is not None if os.name == "nt" else True
    assert file.read_bytes() == b"hello" and file.stat().st_mtime_ns == before.st_mtime_ns
    assert not result.issues


def test_scan_skips_protected_files(tmp_path):
    private = tmp_path / "private"
    private.mkdir()
    (private / "database.sqlite3").write_bytes(b"protected")
    (tmp_path / "photo.png").write_bytes(b"photo")
    result = Scanner(SafetyPolicy((private,))).scan(tmp_path)
    assert [f.name for f in result.files] == ["photo.png"]
    assert result.skipped_protected == 1
    with pytest.raises(SafetyError):
        Scanner(SafetyPolicy((private,))).scan(private)


def test_scan_inaccessible_directory_continues(tmp_path, monkeypatch):
    locked = tmp_path / "locked"
    locked.mkdir()
    (tmp_path / "readable.txt").write_text("okay")
    original = os.scandir
    def guarded(path):
        if Path(path) == locked:
            raise PermissionError("test access denied")
        return original(path)
    monkeypatch.setattr(os, "scandir", guarded)
    result = Scanner(SafetyPolicy()).scan(tmp_path)
    assert len(result.files) == 1
    assert result.issues[0].path == locked


def test_cancel_scan(tmp_path):
    cancel = Event()
    cancel.set()
    result = Scanner(SafetyPolicy()).scan(tmp_path, cancel)
    assert result.cancelled and not result.files


def test_symlink_loop_is_skipped(tmp_path):
    (tmp_path / "file.txt").write_text("safe")
    try:
        (tmp_path / "loop").symlink_to(tmp_path, target_is_directory=True)
    except OSError:
        pytest.skip("Creating symbolic links requires Windows developer mode or privileges")
    result = Scanner(SafetyPolicy()).scan(tmp_path)
    assert len(result.files) == 1 and result.skipped_links == 1
    with pytest.raises(SafetyError):
        Scanner(SafetyPolicy()).scan(tmp_path / "loop")


@pytest.mark.skipif(os.name != "nt", reason="Windows junction behavior")
def test_windows_junction_loop_is_skipped_without_symlink_privileges(tmp_path):
    import subprocess
    (tmp_path / "safe.txt").write_text("safe")
    link = tmp_path / "junction"
    result = subprocess.run(["cmd.exe", "/c", "mklink", "/J", str(link), str(tmp_path)],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    try:
        scan = Scanner(SafetyPolicy()).scan(tmp_path)
        assert len(scan.files) == 1 and scan.skipped_links == 1
        with pytest.raises(SafetyError):
            Scanner(SafetyPolicy()).scan(link)
    finally:
        # rmdir removes only this test-created junction, never its target.
        os.rmdir(link)


def test_duplicates_hash_content_not_names_and_redundant_space(tmp_path):
    for name in ("first.txt", "second.pdf", "third.bin"):
        (tmp_path / name).write_bytes(b"identical content")
    (tmp_path / "different.txt").write_bytes(b"different content")
    (tmp_path / "unique.bin").write_bytes(b"different size")
    scan = Scanner(SafetyPolicy()).scan(tmp_path)
    result = find_duplicates(scan.files)
    assert len(result.groups) == 1
    assert len(result.groups[0].files) == 3
    assert result.extra_copies == 2
    assert result.redundant_size == 2 * len(b"identical content")
    assert result.hashed_files == 4
    assert len(result.groups[0].digest) == 64


def test_empty_files_are_exact_duplicates(tmp_path):
    (tmp_path / "a").touch()
    (tmp_path / "b").touch()
    result = find_duplicates(Scanner(SafetyPolicy()).scan(tmp_path).files)
    assert len(result.groups) == 1 and result.redundant_size == 0


def test_changed_and_disappeared_candidates_report_issues(tmp_path):
    first, second = tmp_path / "a.txt", tmp_path / "b.txt"
    first.write_text("same")
    second.write_text("same")
    scan = Scanner(SafetyPolicy()).scan(tmp_path)
    first.write_text("changed")
    second.unlink()
    result = find_duplicates(scan.files)
    assert not result.groups and len(result.issues) == 2


def test_duplicate_cancel(tmp_path):
    for name in ("a", "b"):
        (tmp_path / name).write_bytes(b"same")
    event = Event()
    event.set()
    result = find_duplicates(Scanner(SafetyPolicy()).scan(tmp_path).files, event)
    assert result.cancelled and result.hashed_files == 0


def test_large_and_old_insights_use_real_thresholds(tmp_path):
    file = tmp_path / "old.bin"
    file.write_bytes(b"x" * (1024 * 1024))
    os.utime(file, (1_000_000, 1_000_000))
    result = analyze(Scanner(SafetyPolicy()).scan(tmp_path).files, Settings(old_days=30, large_mb=1))
    assert len(result.large) == 1 and len(result.old) == 1
    assert result.total_size == 1024 * 1024
    assert result.largest[0].name == "old.bin"


def test_hash_detects_file_modified_during_chunked_read(tmp_path):
    from filepilot.core.safety import hash_file
    source = tmp_path / "large.bin"
    source.write_bytes(b"a" * (3 * 1024 * 1024))
    record = Scanner(SafetyPolicy()).scan(tmp_path).files[0]
    calls = []
    def change_after_chunk(length):
        calls.append(length)
        if len(calls) == 1:
            with source.open("ab") as stream:
                stream.write(b"changed during read")
    with pytest.raises(SafetyError):
        hash_file(record, activity=change_after_chunk)
    assert calls and max(calls) <= 1024 * 1024
