"""RuntimeInstallPage（OOBE 推荐组件页）的逐分支测试。

覆盖：
  - mount 过滤：canInstall=False / title 未声明的 runtime 不出现
  - mount 排序：推荐组件在前，组内保持 pack 加载序（稳定排序）
  - 已安装 runtime：展示但不可勾选
  - 未安装 runtime：勾选默认值 = isRecommended
  - mount 幂等
  - selectedRuntimes 只返回勾选项
  - 四个真实 pack 的自描述声明齐全
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QApplication
from qfluentwidgets import FluentIcon

app = QApplication.instance() or QApplication(sys.argv)

from app.models.pack import BinaryRuntime


class FakeRuntime(BinaryRuntime):

    def __init__(self, title="组件", name="bin", canInstall=True,
                 isRecommended=False, installedPath=""):
        self.title = title
        self.description = f"{title} 的说明"
        self.icon = FluentIcon.VIDEO
        self.name = name
        self.canInstall = canInstall
        self.isRecommended = isRecommended
        self._installedPath = installedPath

    def path(self) -> str:
        return self._installedPath


@pytest.fixture()
def page():
    from app.view.windows.oobe_window import RuntimeInstallPage
    p = RuntimeInstallPage()
    p._card.addGroup = MagicMock()
    return p


def _mount(page, monkeypatch, runtimes):
    monkeypatch.setattr(
        "app.services.feature_service.featureService",
        MagicMock(runtimes=MagicMock(return_value=runtimes)),
    )
    page.mount()


def _shownTitles(page) -> list[str]:
    return [call.args[1] for call in page._card.addGroup.call_args_list]


class TestMountFiltering:

    def test_excludes_not_installable(self, page, monkeypatch):
        _mount(page, monkeypatch, [
            FakeRuntime(title="可装"),
            FakeRuntime(title="不可装", canInstall=False),
        ])
        assert _shownTitles(page) == ["可装"]

    def test_excludes_without_title(self, page, monkeypatch):
        _mount(page, monkeypatch, [
            FakeRuntime(title="有自描述"),
            FakeRuntime(title=""),
        ])
        assert _shownTitles(page) == ["有自描述"]


class TestMountOrdering:

    def test_recommended_first_stable(self, page, monkeypatch):
        _mount(page, monkeypatch, [
            FakeRuntime(title="普通"),
            FakeRuntime(title="推荐甲", isRecommended=True),
            FakeRuntime(title="推荐乙", isRecommended=True),
        ])
        assert _shownTitles(page) == ["推荐甲", "推荐乙", "普通"]


class TestMountInstalledState:

    def test_installed_runtime_has_no_checkbox(self, page, monkeypatch):
        _mount(page, monkeypatch, [
            FakeRuntime(title="已装", installedPath="C:/bin/x.exe"),
            FakeRuntime(title="未装"),
        ])
        assert len(_shownTitles(page)) == 2
        assert [rt.title for _, rt in page._checkBoxes] == ["未装"]

    def test_checkbox_follows_recommendation(self, page, monkeypatch):
        _mount(page, monkeypatch, [
            FakeRuntime(title="推荐", isRecommended=True),
            FakeRuntime(title="普通", isRecommended=False),
        ])
        checkedByTitle = {rt.title: cb.isChecked() for cb, rt in page._checkBoxes}
        assert checkedByTitle == {"推荐": True, "普通": False}


class TestMountIdempotent:

    def test_mount_twice_adds_once(self, page, monkeypatch):
        runtimes = [FakeRuntime(title="唯一")]
        _mount(page, monkeypatch, runtimes)
        _mount(page, monkeypatch, runtimes)
        assert page._card.addGroup.call_count == 1
        assert len(page._checkBoxes) == 1


class TestSelectedRuntimes:

    def test_returns_only_checked(self, page, monkeypatch):
        _mount(page, monkeypatch, [
            FakeRuntime(title="推荐", isRecommended=True),
            FakeRuntime(title="普通", isRecommended=False),
        ])
        assert [rt.title for rt in page.selectedRuntimes()] == ["推荐"]

        for checkBox, _ in page._checkBoxes:
            checkBox.setChecked(not checkBox.isChecked())
        assert [rt.title for rt in page.selectedRuntimes()] == ["普通"]


class TestPackDeclarations:
    """四个真实 pack 的 runtime 自描述齐全，策展值固化。"""

    def test_all_runtimes_self_described(self):
        sys.path.insert(0, "features")
        from ffmpeg_pack.config import FFmpegRuntime
        from m3u8_pack.config import M3U8Runtime
        from yt_dlp_pack.config import YouTubeRuntime
        from ed2k_pack.config import ED2kRuntime

        expected = {
            FFmpegRuntime: True,
            M3U8Runtime: True,
            YouTubeRuntime: True,
            ED2kRuntime: False,
        }
        for cls, isRecommended in expected.items():
            assert cls.title, cls.__name__
            assert cls.description, cls.__name__
            assert cls.icon is not None, cls.__name__
            assert cls.isRecommended is isRecommended, cls.__name__


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
