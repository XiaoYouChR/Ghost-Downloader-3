from __future__ import annotations

import time
from typing import TYPE_CHECKING

from PySide6.QtCore import QCoreApplication
from qfluentwidgets import CaptionLabel

from app.format import toDockSpeed, toReadableSize, toReadableTime
from app.view.dialogs.task_drawer import DetailCard, DetailTable, InfoRow
from .cards import toHeldText
from .kelpie import Link, Source
from .session import ed2kSession

if TYPE_CHECKING:
    from .task import ED2kTask

PART_SIZE = 9728000


def toPartCount(size: int) -> int:
    return -(-size // PART_SIZE)


def toAichHash(url: str) -> str:
    for field in url.split("|"):
        if field.startswith("h="):
            return field[2:]
    return ""


def toSourceStatusText(source: Source) -> str:
    match source.status:
        case "transferring":
            return QCoreApplication.translate("ED2kSourceCard", "传输中")
        case "queued" if source.rank > 0:
            return QCoreApplication.translate("ED2kSourceCard", "排队 #{0}").format(source.rank)
        case "queued":
            return QCoreApplication.translate("ED2kSourceCard", "排队")
        case "connecting":
            return QCoreApplication.translate("ED2kSourceCard", "连接中")
        case "held":
            return QCoreApplication.translate("ED2kSourceCard", "暂缓")
        case _:
            return source.status


def toChannelText(channel: str) -> str:
    match channel:
        case "link":
            return QCoreApplication.translate("ED2kSourceCard", "链接")
        case "server":
            return QCoreApplication.translate("ED2kSourceCard", "服务器")
        case "kad":
            return "KAD"
        case "exchange":
            return QCoreApplication.translate("ED2kSourceCard", "来源交换")
        case "incoming":
            return QCoreApplication.translate("ED2kSourceCard", "对方连入")
        case _:
            return channel


class ED2kCard(DetailCard):
    def __init__(self, task: ED2kTask, parent=None):
        super().__init__(self.tr("eD2k"), parent)
        self._task = task
        self.hashRow = InfoRow(self.tr("文件哈希"), self.card)
        self.aichRow = InfoRow(self.tr("AICH 根哈希"), self.card)
        self.partsRow = InfoRow(self.tr("分块"), self.card)
        self.speedRow = InfoRow(self.tr("速度"), self.card)
        self.peersRow = InfoRow(self.tr("来源"), self.card)
        self.heldRow = InfoRow(self.tr("暂缓"), self.card)
        self.uploadedRow = InfoRow(self.tr("已上传"), self.card)
        self.ratioRow = InfoRow(self.tr("分享率"), self.card)
        self._initWidget()
        self._initLayout()

    def _initWidget(self) -> None:
        self.hashRow.addCopyButton()
        self.hashRow.setValue(Link.parse(self._task.url).hash)
        self.aichRow.addCopyButton()
        self.aichRow.setValue(toAichHash(self._task.url))
        self.aichRow.setVisible(bool(self.aichRow.valueText.text()))
        self.partsRow.setValue(f"{toPartCount(self._task.fileSize)} × {toReadableSize(PART_SIZE)}")

    def _initLayout(self) -> None:
        for row in (self.hashRow, self.aichRow, self.partsRow, self.speedRow, self.peersRow, self.heldRow,
                    self.uploadedRow, self.ratioRow):
            self.bodyLayout.addWidget(row)

    def refresh(self) -> None:
        task = self._task
        progress = ed2kSession.progressOf(task)
        for row in (self.speedRow, self.peersRow):
            row.setVisible(progress is not None)
        if progress is not None:
            self.speedRow.setValue(self.tr("下载 {0}，上传 {1}").format(
                toDockSpeed(progress.downloadRate), toDockSpeed(progress.uploadRate)))
            self.peersRow.setValue(self.tr("传输中 {0}，共 {1}").format(progress.activePeers, progress.peers))
        heldText = toHeldText(progress, int(time.time() * 1000))
        self.heldRow.setVisible(heldText is not None)
        if heldText is not None:
            self.heldRow.setValue(heldText)
        self.uploadedRow.setValue(toReadableSize(task.uploadedBytes))
        self.ratioRow.setValue(self.tr("{0}，已做种 {1}").format(
            f"{task.shareRatioPercent / 100:.2f}", toReadableTime(task.seedingTimeSeconds)))


class ED2kSourceCard(DetailCard):
    def __init__(self, task: ED2kTask, parent=None):
        super().__init__(self.tr("来源"), parent)
        self._task = task
        self.table = DetailTable(
            [self.tr("地址"), self.tr("客户端"), self.tr("状态"), self.tr("下载"), self.tr("渠道")],
            stretchColumns=(1,), parent=self.card)
        self.idleLabel = CaptionLabel(self.tr("任务运行时显示"), self.card)
        self.bodyLayout.addWidget(self.table)
        self.bodyLayout.addWidget(self.idleLabel)

    def refresh(self) -> None:
        progress = ed2kSession.progressOf(self._task)
        sources = progress.sources if progress is not None else ()
        self.table.setVisible(bool(sources))
        self.idleLabel.setVisible(not sources)
        self.table.setRows([
            (source.address, source.software, toSourceStatusText(source),
             toDockSpeed(source.downloadRate) if source.downloadRate > 0 else "", toChannelText(source.channel))
            for source in sources
        ])
