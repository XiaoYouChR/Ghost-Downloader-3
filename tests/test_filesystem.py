from __future__ import annotations

import sys
from pathlib import Path

from app.platform.filesystem import deletePath, isExisting, isFolder


def test_probe_unreadable_path_as_missing(tmp_path: Path):
    file = tmp_path / "file"
    file.write_text("x")
    for path in (file / "child", tmp_path / "a\0b"):
        assert isExisting(path) is False
        assert isFolder(path) is False


def createFolder(path: Path) -> Path:
    target = Path(f"\\\\?\\{path}") if sys.platform == "win32" else path
    target.mkdir(parents=True)
    return target


def test_delete_deep_folder_removes_tree(tmp_path: Path):
    root = tmp_path / ("a" * 120)
    deep = createFolder(root / ("b" * 100) / ("c" * 100))
    (deep / "seg.ts").write_bytes(b"data")

    deletePath(root)
    assert not root.exists()


def test_delete_trailing_space_folder_removes_tree(tmp_path: Path):
    root = tmp_path / "part"
    spaced = createFolder(root / "tmp" / "name ")
    (spaced / "chunk.ts").write_bytes(b"data")

    deletePath(root)
    assert not root.exists()
