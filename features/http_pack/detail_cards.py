from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QSizePolicy
from qfluentwidgets import CaptionLabel

from app.format import toDockSpeed, toReadableSize
from app.models.task import TaskStatus, toHost
from app.view.dialogs.task_drawer import DetailCard, DetailTable

if TYPE_CHECKING:
    from .task import HttpSource, HttpTask


class SourceCard(DetailCard):
    def __init__(self, task: HttpTask, parent=None):
        super().__init__(self.tr("下载源"), parent)
        self._task = task
        self.table = DetailTable(
            [self.tr("来源"), self.tr("状态"), self.tr("速度"), self.tr("已下载")], parent=self.card)
        self.verificationLabel = CaptionLabel(self)
        self.verificationLabel.setContentsMargins(0, 6, 0, 0)
        self.layout().addWidget(self.verificationLabel)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        self.bodyLayout.setContentsMargins(0, 0, 0, 0)
        self.bodyLayout.addWidget(self.table)

    def refresh(self) -> None:
        step = self._task.mirrorStep
        self.setVisible(step is not None)
        if step is None:
            return
        expected = self._task.expectedSha256
        self.verificationLabel.setVisible(step.mirror is not None)
        if expected and self._task.checksums.get("sha256") == expected:
            self.verificationLabel.setText(self.tr("整文件 SHA-256 校验通过"))
        elif expected:
            self.verificationLabel.setText(self.tr("整文件 SHA-256 尚未通过校验"))
        else:
            self.verificationLabel.setText(self.tr("仅抽样匹配"))
        rows, hosts = [], []
        for index, source in enumerate(step.sources):
            role = self.tr("原下载源") if index == 0 else self.tr("追加源")
            isActive = step.isSourceActive(source) and not source.isUnavailable
            rows.append((f"{role} · {source.host}", self._toStatusText(source, isActive),
                         toDockSpeed(source.speed if isActive else 0), toReadableSize(source.receivedBytes)))
            hosts.append(f"{role} · {source.host}" if not source.effectiveUrl else
                         f"{role} · {source.host} → {toHost(source.effectiveUrl)}")
        self.table.setRows(rows, toolTips=hosts)
        self.card.setFixedHeight(self.table.height() + 2)

    def _toStatusText(self, source: HttpSource, isActive: bool) -> str:
        if source.isDisabled:
            return self.tr("不可用")
        if source.isUnavailable and self._task.status == TaskStatus.RUNNING:
            return self.tr("等待重试")
        if isActive:
            return self.tr("下载中")
        if self._task.status == TaskStatus.PAUSED:
            return self.tr("已暂停")
        if self._task.status == TaskStatus.COMPLETED:
            return self.tr("已完成")
        if self._task.status == TaskStatus.FAILED:
            return self.tr("已停止")
        return self.tr("等待区段")
