from __future__ import annotations

from base64 import b64decode
from datetime import datetime
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from qfluentwidgets import CaptionLabel

from app.format import toDockSpeed, toReadableSize, toReadableTime
from app.view.dialogs.task_drawer import DetailCard, DetailTable, InfoRow

from .session import btSession
from .swarm import SwarmInfo, TrackerStatus, toEndpointText, toTorrentMeta

if TYPE_CHECKING:
    from .swarm import PeerInfo, TrackerInfo
    from .task import BTTask


def toRateText(rate: int) -> str:
    return toDockSpeed(rate) if rate > 0 else ""


def toCountText(count: int) -> str:
    return str(count) if count >= 0 else ""


class TorrentCard(DetailCard):
    def __init__(self, task: BTTask, coroutineRunner, parent=None):
        super().__init__(self.tr("种子"), parent)
        self._task = task
        self._coroutineRunner = coroutineRunner
        self.hashV1Row = InfoRow(self.tr("Info Hash v1"), self.card)
        self.hashV2Row = InfoRow(self.tr("Info Hash v2"), self.card)
        self.commentRow = InfoRow(self.tr("注释"), self.card)
        self.creatorRow = InfoRow(self.tr("创建者"), self.card)
        self.createdRow = InfoRow(self.tr("创建时间"), self.card)
        self.piecesRow = InfoRow(self.tr("分块"), self.card)
        self.seedsRow = InfoRow(self.tr("做种"), self.card)
        self.peersRow = InfoRow(self.tr("下载者"), self.card)
        self.copiesRow = InfoRow(self.tr("可用副本"), self.card)
        self.uploadedRow = InfoRow(self.tr("已上传"), self.card)
        self.downloadedRow = InfoRow(self.tr("已下载"), self.card)
        self.ratioRow = InfoRow(self.tr("分享率"), self.card)
        self.announceRow = InfoRow(self.tr("下次汇报"), self.card)
        self._initWidget()
        self._initLayout()

    def _initWidget(self) -> None:
        self.hashV1Row.addCopyButton()
        self.hashV2Row.addCopyButton()
        meta = toTorrentMeta(b64decode(self._task.torrentData)) if self._task.torrentData else None
        self.hashV1Row.setValue(meta.infoHashV1 if meta else "")
        self.hashV2Row.setValue(meta.infoHashV2 if meta else "")
        self.commentRow.setValue(meta.comment if meta else "")
        self.creatorRow.setValue(meta.creator if meta else "")
        self.createdRow.setValue(datetime.fromtimestamp(meta.createdAt).strftime("%Y-%m-%d %H:%M:%S")
                                 if meta and meta.createdAt else "")
        self.piecesRow.setValue(f"{meta.pieceCount} × {toReadableSize(meta.pieceSize)}"
                                + (self.tr("（私有）") if meta.isPrivate else "") if meta else "")
        for row in (self.hashV1Row, self.hashV2Row, self.commentRow, self.creatorRow, self.createdRow, self.piecesRow):
            row.setVisible(bool(row.valueLabel.text()))
        self._setSwarm(None)

    def _initLayout(self) -> None:
        for row in (self.hashV1Row, self.hashV2Row, self.commentRow, self.creatorRow, self.createdRow,
                    self.piecesRow, self.seedsRow, self.peersRow, self.copiesRow, self.uploadedRow,
                    self.downloadedRow, self.ratioRow, self.announceRow):
            self.bodyLayout.addWidget(row)

    def refresh(self) -> None:
        taskId = self._task.taskId

        async def swarmInfo():
            return btSession.swarmInfo(taskId)

        self._coroutineRunner.submit(swarmInfo(), self._setSwarm, owner=self)

    def _setSwarm(self, swarm: SwarmInfo | None) -> None:
        for row in (self.seedsRow, self.peersRow, self.copiesRow, self.uploadedRow, self.downloadedRow, self.announceRow):
            row.setVisible(swarm is not None)
        task = self._task
        self.ratioRow.setValue(self.tr("{0}，已做种 {1}").format(
            f"{task.shareRatioPercent / 100:.2f}", toReadableTime(task.seedingTimeSeconds)))
        if swarm is None:
            return
        self.seedsRow.setValue(self.tr("已连接 {0}，共 {1}").format(swarm.seeds, toCountText(swarm.totalSeeds) or "?"))
        self.peersRow.setValue(self.tr("已连接 {0}，共 {1}").format(swarm.peers, toCountText(swarm.totalPeers) or "?"))
        self.copiesRow.setValue(f"{swarm.distributedCopies:.2f}")
        self.uploadedRow.setValue(toReadableSize(swarm.totalUpload))
        self.downloadedRow.setValue(toReadableSize(swarm.totalDownload))
        self.announceRow.setValue(toReadableTime(max(swarm.nextAnnounceSeconds, 0)))


class TrackerCard(DetailCard):
    def __init__(self, task: BTTask, coroutineRunner, parent=None):
        super().__init__(self.tr("Tracker"), parent)
        self._task = task
        self._coroutineRunner = coroutineRunner
        self.table = DetailTable(
            [self.tr("地址"), self.tr("状态"), self.tr("做种"), self.tr("下载"), self.tr("Peer")],
            stretchColumns=(0, 1), elideMode=Qt.TextElideMode.ElideMiddle, parent=self.card)
        self.idleLabel = CaptionLabel(self.tr("任务运行时显示"), self.card)
        self.bodyLayout.addWidget(self.table)
        self.bodyLayout.addWidget(self.idleLabel)

    def refresh(self) -> None:
        taskId = self._task.taskId

        async def trackers():
            return btSession.trackers(taskId)

        self._coroutineRunner.submit(trackers(), self._setTrackers, owner=self)

    def _setTrackers(self, trackers: tuple[TrackerInfo, ...]) -> None:
        self.table.setVisible(bool(trackers))
        self.idleLabel.setVisible(not trackers)
        self.table.setRows([
            (tracker.url, self._toStatusText(tracker), toCountText(tracker.seeds),
             toCountText(tracker.leeches), toCountText(tracker.peers))
            for tracker in trackers
        ])

    def _toStatusText(self, tracker: TrackerInfo) -> str:
        text = {
            TrackerStatus.WORKING: self.tr("工作中"),
            TrackerStatus.UPDATING: self.tr("更新中"),
            TrackerStatus.NOT_CONTACTED: self.tr("未联系"),
            TrackerStatus.ERROR: self.tr("出错"),
            TrackerStatus.DISABLED: self.tr("已禁用"),
        }[tracker.status]
        return self.tr("{0}：{1}").format(text, tracker.message) if tracker.message else text


class PeerCard(DetailCard):
    def __init__(self, task: BTTask, coroutineRunner, parent=None):
        super().__init__(self.tr("Peer"), parent)
        self._task = task
        self._coroutineRunner = coroutineRunner
        self.table = DetailTable(
            [self.tr("地址"), self.tr("客户端"), self.tr("下载"), self.tr("上传")],
            stretchColumns=(0, 1), elideMode=Qt.TextElideMode.ElideMiddle, parent=self.card)
        self.idleLabel = CaptionLabel(self.tr("任务运行时显示"), self.card)
        self.bodyLayout.addWidget(self.table)
        self.bodyLayout.addWidget(self.idleLabel)

    def refresh(self) -> None:
        taskId = self._task.taskId

        async def peers():
            return btSession.peers(taskId)

        self._coroutineRunner.submit(peers(), self._setPeers, owner=self)

    def _setPeers(self, peers: tuple[PeerInfo, ...]) -> None:
        self.table.setVisible(bool(peers))
        self.idleLabel.setVisible(not peers)
        ordered = sorted(peers, key=lambda peer: (peer.downloadRate, peer.uploadRate), reverse=True)
        self.table.setRows(
            [(peer.host, peer.client, toRateText(peer.downloadRate), toRateText(peer.uploadRate)) for peer in ordered],
            [self.tr("{0}\n{1}\n标志 {2}  进度 {3}").format(
                toEndpointText((peer.host, peer.port)), peer.client, peer.flags or "-", f"{peer.progress * 100:.1f}%")
             for peer in ordered],
        )
