from __future__ import annotations

from pathlib import Path

import pytest

from app.platform.filesystem import isExisting, isFolder, toNumberedFilename, toSafeFilename


def test_probe_unreadable_path_as_missing(tmp_path: Path):
    file = tmp_path / "file"
    file.write_text("x")
    for path in (file / "child", tmp_path / "a\0b"):
        assert isExisting(path) is False
        assert isFolder(path) is False


@pytest.mark.parametrize("length", [193, 194, 195, 196, 197, 200, 260])
def test_numbering_changes_name_at_length_limit(length: int):
    name = toSafeFilename("x" * length + ".mp4")
    numbered = [toNumberedFilename(name, index) for index in range(1, 6)]

    assert all(len(candidate) <= 200 for candidate in numbered)
    assert len(set(numbered)) == len(numbered)


def test_numbering_keeps_counter_before_extension():
    assert toNumberedFilename("a.zip", 1) == "a(1).zip"
    assert toNumberedFilename("archive.tar.gz", 2) == "archive(2).tar.gz"
    assert toNumberedFilename(".gitignore", 1) == ".gitignore(1)"
