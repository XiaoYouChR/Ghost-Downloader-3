from __future__ import annotations

from pathlib import Path

from app.platform.filesystem import isExisting, isFolder


def test_isExisting_missing(tmp_path: Path):
    assert isExisting(tmp_path / "missing") is False


def test_isExisting_present(tmp_path: Path):
    file = tmp_path / "file"
    file.write_text("x")
    assert isExisting(file) is True
    assert isFolder(file) is False
    assert isFolder(tmp_path) is True


def test_isExisting_stat_failure(tmp_path: Path, monkeypatch):
    def fail(self, *, follow_symlinks=True):
        error = OSError(22, "参数错误")
        error.winerror = 87
        raise error

    monkeypatch.setattr(Path, "stat", fail)
    assert isExisting(tmp_path / "zh-cn_windows_11.iso") is False
    assert isFolder(tmp_path / "zh-cn_windows_11.iso") is False
