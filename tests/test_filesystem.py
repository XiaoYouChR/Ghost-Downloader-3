from __future__ import annotations

from pathlib import Path

from app.platform.filesystem import isExisting, isFolder


def test_probe_unreadable_path_as_missing(tmp_path: Path):
    file = tmp_path / "file"
    file.write_text("x")
    for path in (file / "child", tmp_path / "a\0b"):
        assert isExisting(path) is False
        assert isFolder(path) is False
