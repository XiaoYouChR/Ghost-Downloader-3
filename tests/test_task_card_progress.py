"""任务卡进度条协议的回归测试。

背景：UniversalTaskCard.refresh() 曾假设进度条实现 stop()/error() 等
qfluentwidgets 专有方法，SegmentedProgressBar / ProgressBar 缺少 stop()
导致 COMPLETED 且 fileSize<=0 时 AttributeError 崩溃。

覆盖：
  - 7 种 FeaturePack 卡片 × 全部状态分支 × fileSize {0, >0}，refresh 不抛异常
  - COMPLETED 隐藏进度条，回到 RUNNING 重新显示（redownload 回归）
  - 基类 refresh 只使用收窄后的进度条协议动词
  - SegmentedProgressBar 仅在大小已知且多线程时被选择
  - FAILED 时 SegmentedProgressBar 进入错误配色
  - pack 特有分支：BT 做种、YtDlp 播放列表、M3U8 未知大小百分比、
    M3U8 直播录制、FTP/HuggingFace 多文件计数
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "features"))

app = QApplication.instance() or QApplication(sys.argv)

from app.models.task import Task, TaskStatus
from app.view.cards.task_cards import UniversalTaskCard

from bittorrent_pack.cards import BTTaskCard
from bittorrent_pack.task import BTFile, BTTask, BTTaskStep
from ftp_pack.cards import FtpTaskCard
from ftp_pack.task import FtpConnectionInfo, FtpFile, FtpTask
from http_pack.cards import HttpTaskCard, SegmentedProgressBar
from http_pack.task import HttpTask, HttpTaskStep
from huggingface_pack.cards import HuggingFaceTaskCard
from huggingface_pack.task import HuggingFaceFile, HuggingFaceTask
from m3u8_pack.cards import M3U8LiveTaskCard, M3U8TaskCard
from m3u8_pack.task import M3U8Task, M3U8TaskStep
from yt_dlp_pack.cards import YtDlpTaskCard
from yt_dlp_pack.task import YouTubeExtractStep, YouTubeTask

ALL_STATUSES = [
    TaskStatus.WAITING,
    TaskStatus.RUNNING,
    TaskStatus.PAUSED,
    TaskStatus.FAILED,
    TaskStatus.COMPLETED,
]

ALLOWED_PROGRESS_VERBS = {"setValue", "setError", "pause", "show", "hide", "setGeometry"}


class StubCategoryService(QObject):
    categoriesChanged = Signal()

    def categories(self):
        return []

    def categoryById(self, cid):
        return None


@pytest.fixture(autouse=True)
def categoryStub(monkeypatch):
    monkeypatch.setattr(
        "app.services.category_service.categoryService", StubCategoryService()
    )


@pytest.fixture()
def makeCard():
    cards = []

    def make(cardFactory):
        card = cardFactory()
        cards.append(card)
        card.show()
        return card

    yield make
    for card in cards:
        card.close()
        card.deleteLater()
    app.processEvents()


# ─── 各 pack 的任务/卡片构造 ─────────────────────────────────


def buildHttpTask(fileSize=100, canUseRangeRequests=True, subworkerCount=8):
    url = "https://example.com/file.bin"
    step = HttpTaskStep(
        stepIndex=0,
        url=url,
        fileSize=fileSize,
        canUseRangeRequests=canUseRangeRequests,
        subworkerCount=subworkerCount,
    )
    return HttpTask(name="file.bin", url=url, fileSize=fileSize, steps=[step])


def buildHttpCard(fileSize):
    return HttpTaskCard(buildHttpTask(fileSize=fileSize))


def buildYtDlpCard(fileSize):
    task = YouTubeTask(
        name="video", url="https://youtube.com/watch?v=x", fileSize=fileSize
    )
    return YtDlpTaskCard(task)


def buildBtCard(fileSize):
    files = [BTFile(index=0, relativePath="file.bin", size=fileSize)] if fileSize else []
    task = BTTask(
        name="file.bin",
        url="magnet:?xt=urn:btih:0",
        files=files,
        steps=[BTTaskStep(stepIndex=0)],
    )
    return BTTaskCard(task)


def buildM3U8Card(fileSize):
    task = M3U8Task(
        name="video",
        url="https://example.com/index.m3u8",
        fileSize=fileSize,
        steps=[M3U8TaskStep(stepIndex=0)],
    )
    return M3U8TaskCard(task)


def buildM3U8LiveCard(fileSize):
    task = M3U8Task(
        name="live",
        url="https://example.com/live.m3u8",
        fileSize=fileSize,
        isLive=True,
        steps=[M3U8TaskStep(stepIndex=0)],
    )
    return M3U8LiveTaskCard(task)


def buildFtpCard(fileSize):
    task = FtpTask(
        name="file.bin",
        url="ftp://127.0.0.1/file.bin",
        connectionInfo=FtpConnectionInfo(
            scheme="ftp",
            host="127.0.0.1",
            port=21,
            username="",
            password="",
            sourcePath="/file.bin",
        ),
        fileSize=fileSize,
    )
    return FtpTaskCard(task)


def buildHuggingFaceCard(fileSize):
    task = HuggingFaceTask(
        name="model", url="https://huggingface.co/org/model", fileSize=fileSize
    )
    return HuggingFaceTaskCard(task)


CARD_BUILDERS = {
    "http": buildHttpCard,
    "ytdlp": buildYtDlpCard,
    "bt": buildBtCard,
    "m3u8": buildM3U8Card,
    "m3u8live": buildM3U8LiveCard,
    "ftp": buildFtpCard,
    "huggingface": buildHuggingFaceCard,
}


# ─── 全 pack × 全状态矩阵 ────────────────────────────────────


@pytest.mark.parametrize("fileSize", [0, 100], ids=["unknownSize", "knownSize"])
@pytest.mark.parametrize("buildCard", CARD_BUILDERS.values(), ids=CARD_BUILDERS.keys())
class TestRefreshMatrix:

    def test_refresh_covers_every_status(self, makeCard, buildCard, fileSize):
        card = makeCard(lambda: buildCard(fileSize))
        for status in ALL_STATUSES:
            card._task.status = status
            card.refresh(force=True)

    def test_completed_hides_bar_and_running_shows_again(self, makeCard, buildCard, fileSize):
        card = makeCard(lambda: buildCard(fileSize))
        card._task.status = TaskStatus.COMPLETED
        card.refresh(force=True)
        assert card.progressBar.isHidden()

        card._task.status = TaskStatus.RUNNING
        card.refresh(force=True)
        assert not card.progressBar.isHidden()


# ─── 协议钉死：基类只用收窄后的动词 ──────────────────────────


def test_refresh_only_uses_shared_progress_verbs(makeCard):
    task = Task(name="file.bin", url="https://example.com/file.bin", packId="test")
    card = makeCard(lambda: UniversalTaskCard(task))
    bar = MagicMock()
    card.progressBar = bar
    app.processEvents()
    bar.reset_mock()

    for status in ALL_STATUSES:
        task.status = status
        card.refresh(force=True)

    calledVerbs = {name.split(".")[0] for name, _, _ in bar.method_calls}
    assert calledVerbs <= ALLOWED_PROGRESS_VERBS


# ─── SegmentedProgressBar 选择守卫 ───────────────────────────


@pytest.mark.parametrize(
    "fileSize,canUseRangeRequests,subworkerCount,expectSegmented",
    [
        (100, True, 8, True),
        (0, True, 8, False),
        (100, False, 8, False),
        (100, True, 1, False),
    ],
    ids=["knownSizeMultiWorker", "unknownSize", "noRangeRequests", "singleWorker"],
)
def test_segmented_bar_requires_known_size(
    makeCard, fileSize, canUseRangeRequests, subworkerCount, expectSegmented
):
    task = buildHttpTask(
        fileSize=fileSize,
        canUseRangeRequests=canUseRangeRequests,
        subworkerCount=subworkerCount,
    )
    card = makeCard(lambda: HttpTaskCard(task))
    assert isinstance(card.progressBar, SegmentedProgressBar) is expectSegmented


def test_failed_segmented_bar_enters_error_state(makeCard):
    card = makeCard(lambda: buildHttpCard(100))
    assert isinstance(card.progressBar, SegmentedProgressBar)
    card._task.status = TaskStatus.FAILED
    card.refresh(force=True)
    assert card.progressBar._isError


# ─── pack 特有分支 ───────────────────────────────────────────


def test_bt_seeding_hides_bar_and_shows_status(makeCard):
    card = makeCard(lambda: buildBtCard(100))
    card._task.isSeeding = True
    card._task.status = TaskStatus.RUNNING
    card.refresh(force=True)
    assert card.progressBar.isHidden()
    assert "做种中" in card.statusLabel.text()

    card._task.isSeeding = False
    card.refresh(force=True)
    assert not card.progressBar.isHidden()


def test_ytdlp_playlist_completed_shows_video_count(makeCard):
    task = YouTubeTask(
        name="playlist",
        url="https://youtube.com/playlist?list=x",
        isPlaylist=True,
        steps=[
            YouTubeExtractStep(stepIndex=i, receivedBytes=25) for i in range(4)
        ],
    )
    card = makeCard(lambda: YtDlpTaskCard(task))
    task.status = TaskStatus.COMPLETED
    card.refresh(force=True)
    assert "个视频" in card.sizeLabel.text()
    assert not card.sizeLabel.isHidden()


def test_m3u8_running_unknown_size_shows_percent(makeCard):
    card = makeCard(lambda: buildM3U8Card(0))
    step = card._task.steps[0]
    step.progress = 42.0
    step.receivedBytes = 1000
    card._task.status = TaskStatus.RUNNING
    card.refresh(force=True)
    assert "%" in card.sizeLabel.text()


def test_m3u8_live_running_shows_recording(makeCard):
    card = makeCard(lambda: buildM3U8LiveCard(0))
    card._task.status = TaskStatus.RUNNING
    card.refresh(force=True)
    assert card.sizeLabel.text() == "录制中"

    card._task.steps[0].liveStatus = "Waiting"
    card.refresh(force=True)
    assert card.sizeLabel.text() == "等待中"


def test_ftp_multifile_shows_selection_count(makeCard):
    task = FtpTask(
        name="folder",
        url="ftp://127.0.0.1/dir",
        sourceType="dir",
        connectionInfo=FtpConnectionInfo(
            scheme="ftp",
            host="127.0.0.1",
            port=21,
            username="",
            password="",
            sourcePath="/dir",
        ),
        fileSize=100,
        files=[
            FtpFile(index=0, relativePath="a.bin", size=50, remotePath="/a.bin"),
            FtpFile(index=1, relativePath="b.bin", size=50, remotePath="/b.bin"),
        ],
    )
    card = makeCard(lambda: FtpTaskCard(task))
    card._task.status = TaskStatus.WAITING
    card.refresh(force=True)
    assert "2/2" in card.statusLabel.text()
    assert card.selectFilesButton is not None


def test_huggingface_multifile_shows_selection_count(makeCard):
    task = HuggingFaceTask(
        name="model",
        url="https://huggingface.co/org/model",
        files=[
            HuggingFaceFile(index=0, relativePath="a.safetensors", size=50),
            HuggingFaceFile(index=1, relativePath="b.safetensors", size=50),
        ],
    )
    card = makeCard(lambda: HuggingFaceTaskCard(task))
    card._task.status = TaskStatus.WAITING
    card.refresh(force=True)
    assert card.selectFilesButton is not None
    assert "2/2" in card.statusLabel.text()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
