from __future__ import annotations

from pathlib import Path

from app.platform.filesystem import probe, probeDirectory


def test_probe_missing(tmp_path: Path):
    assert probe(tmp_path / "missing") is False


def test_probe_present(tmp_path: Path):
    file = tmp_path / "file"
    file.write_text("x")
    assert probe(file) is True
    assert probeDirectory(file) is False
    assert probeDirectory(tmp_path) is True


def test_probe_stat_failure(tmp_path: Path, monkeypatch):
    def fail(self, *, follow_symlinks=True):
        error = OSError(22, "参数错误")
        error.winerror = 87
        raise error

    monkeypatch.setattr(Path, "stat", fail)
    assert probe(tmp_path / "zh-cn_windows_11.iso") is False
    assert probeDirectory(tmp_path / "zh-cn_windows_11.iso") is False
