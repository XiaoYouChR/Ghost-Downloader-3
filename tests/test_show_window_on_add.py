"""添加任务后自动显示主界面的开关 — #478。"""
from __future__ import annotations

import pytest

from app.config.cfg import cfg


@pytest.fixture
def toggle():
    original = cfg.shouldShowWindowOnTaskAdded.value
    originalFile = cfg.file
    yield cfg.shouldShowWindowOnTaskAdded
    cfg.set(cfg.shouldShowWindowOnTaskAdded, original, save=False)
    cfg.file = originalFile


class TestShowWindowOnTaskAdded:

    def test_default_is_off(self):
        assert cfg.shouldShowWindowOnTaskAdded.defaultValue is False

    def test_survives_save_and_load(self, tmp_path, toggle):
        from qfluentwidgets import qconfig

        cfg.file = tmp_path / "config.json"
        cfg.set(toggle, True)
        cfg.set(toggle, False, save=False)

        qconfig.load(cfg.file, cfg)
        assert toggle.value is True

    def test_raises_window_only_when_enabled(self, qapp, toggle, monkeypatch):
        from app.view.windows import main_window

        raised = []
        monkeypatch.setattr("app.platform.desktop.raiseWindow", raised.append)

        cfg.set(toggle, False, save=False)
        main_window.MainWindow._onTaskConfirmed(object(), task=None, autoStart=True)
        assert raised == []

        cfg.set(toggle, True, save=False)
        window = object()
        main_window.MainWindow._onTaskConfirmed(window, task=None, autoStart=True)
        assert raised == [window]
