from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QObject
from PySide6.QtWidgets import QWidget
from qfluentwidgets import (
    FluentIcon, InfoBar, InfoBarPosition, PrimaryPushButton, StateToolTip,
)

from app.format import toReadableSize

if TYPE_CHECKING:
    from app.models.pack import BinaryRuntime


class BatchRuntimeUpdateCard(QWidget):
    """批量运行时更新卡片

    点击"全部更新"后，并行启动所有运行时下载，并用一个 StateToolTip
    汇总显示：(已完成/总数) 当前任务名  X%  speed/s
    """

    def __init__(self, runtimes: list[BinaryRuntime], parent=None):
        super().__init__(parent)
        from qfluentwidgets import SettingCard

        self._runtimes = runtimes
        self._card = SettingCard(
            FluentIcon.SYNC,
            self.tr("运行时批量更新"),
            self.tr("一键检查并更新所有外部依赖运行时"),
            self
        )

        self._checkAllButton = PrimaryPushButton(self.tr("检查全部更新"), self)
        self._updateAllButton = PrimaryPushButton(self.tr("全部更新"), self)
        self._updateAllButton.setEnabled(False)

        # 批量下载状态追踪
        self._totalCount: int = 0
        self._completedCount: int = 0
        self._failedCount: int = 0
        # runtimeId -> (name, progress, speed)
        self._activeDownloads: dict[str, tuple[str, float, int]] = {}
        self._stateToolTip: StateToolTip | None = None

        self._initLayout()
        self._bind()

    def _initLayout(self) -> None:
        from PySide6.QtWidgets import QHBoxLayout
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._card)
        self._card.hBoxLayout.addWidget(self._updateAllButton, 0, Qt.AlignmentFlag.AlignRight)
        self._card.hBoxLayout.addSpacing(8)
        self._card.hBoxLayout.addWidget(self._checkAllButton, 0, Qt.AlignmentFlag.AlignRight)
        self._card.hBoxLayout.addSpacing(16)

    def _bind(self) -> None:
        from app.services.runtime_update_service import runtimeUpdateService
        self._checkAllButton.clicked.connect(self._onCheckAllClicked)
        self._updateAllButton.clicked.connect(self._onUpdateAllClicked)
        runtimeUpdateService.downloadStarted.connect(self._onDownloadStarted)
        runtimeUpdateService.progressChanged.connect(self._onProgressChanged)
        runtimeUpdateService.downloadSucceeded.connect(self._onDownloadSucceeded)
        runtimeUpdateService.downloadFailed.connect(self._onDownloadFailed)

    # ── 按钮事件 ────────────────────────────────────────────────

    def _onCheckAllClicked(self) -> None:
        from app.services.runtime_status import runtimeStatusService
        for runtime in self._runtimes:
            if runtime.canInstall:
                runtimeStatusService.refresh(runtime, force=True)
        self._updateAllButton.setEnabled(True)
        InfoBar.info(
            self.tr("检查完成"), self.tr("已刷新所有运行时状态"),
            duration=2000, position=InfoBarPosition.TOP, parent=self.window(),
        )

    def _onUpdateAllClicked(self) -> None:
        from app.services.runtime_update_service import runtimeUpdateService

        targets = [
            r for r in self._runtimes
            if r.canInstall and not runtimeUpdateService.isDownloading(r.runtimeId)
        ]
        if not targets:
            InfoBar.warning(
                self.tr("无可用更新"),
                self.tr("所有运行时都在下载中或不支持自动安装"),
                duration=3000, position=InfoBarPosition.TOP, parent=self.window(),
            )
            return

        # 初始化追踪状态
        self._totalCount = len(targets)
        self._completedCount = 0
        self._failedCount = 0
        self._activeDownloads.clear()
        self._updateAllButton.setEnabled(False)

        for runtime in targets:
            runtimeUpdateService.downloadRuntime(runtime)

    # ── 信号处理（只处理本次批量任务里的 runtimeId）───────────────

    def _isBatchMember(self, runtimeId: str) -> bool:
        return runtimeId in self._activeDownloads or self._totalCount > 0

    def _onDownloadStarted(self, runtimeId: str, name: str) -> None:
        """某个运行时开始解析/下载"""
        if self._totalCount == 0:
            return  # 不是由本卡片触发的批量任务
        # 只追踪本次批量里的运行时
        batchIds = {r.runtimeId for r in self._runtimes if r.canInstall}
        if runtimeId not in batchIds:
            return
        self._activeDownloads[runtimeId] = (name, 0.0, 0)
        self._refreshToolTip()

    def _onProgressChanged(self, runtimeId: str, progress: float, speed: int) -> None:
        if runtimeId not in self._activeDownloads:
            return
        name = self._activeDownloads[runtimeId][0]
        self._activeDownloads[runtimeId] = (name, progress, speed)
        self._refreshToolTip()

    def _onDownloadSucceeded(self, runtimeId: str, _path: str) -> None:
        if runtimeId not in self._activeDownloads:
            return
        self._completedCount += 1
        self._activeDownloads.pop(runtimeId)
        self._refreshToolTip()
        self._checkBatchDone()

    def _onDownloadFailed(self, runtimeId: str, _error: str) -> None:
        if runtimeId not in self._activeDownloads:
            return
        self._failedCount += 1
        self._activeDownloads.pop(runtimeId)
        self._refreshToolTip()
        self._checkBatchDone()

    # ── StateToolTip 管理 ──────────────────────────────────────

    def _ensureToolTip(self) -> StateToolTip:
        if self._stateToolTip is None:
            self._stateToolTip = StateToolTip(
                self.tr("正在更新运行时"), "", self.window()
            )
            self._stateToolTip.move(self._stateToolTip.getSuitablePos())
            self._stateToolTip.destroyed.connect(self._onToolTipDestroyed)
            self._stateToolTip.show()
        return self._stateToolTip

    def _onToolTipDestroyed(self) -> None:
        self._stateToolTip = None

    def _refreshToolTip(self) -> None:
        done = self._completedCount + self._failedCount
        total = self._totalCount
        if total == 0:
            return

        tip = self._ensureToolTip()

        # 汇总所有活跃下载的进度和速度
        totalSpeed = sum(s for _, _, s in self._activeDownloads.values())
        progresses = [p for _, p, _ in self._activeDownloads.values()]
        avgProgress = sum(progresses) / len(progresses) if progresses else 100.0

        # 找速度最快的那个作为"当前"显示名
        currentName = ""
        if self._activeDownloads:
            fastestId = max(self._activeDownloads, key=lambda k: self._activeDownloads[k][2])
            currentName = self._activeDownloads[fastestId][0]

        count_str = f"({done}/{total})"
        progress_str = f"{avgProgress:.1f}%"
        speed_str = toReadableSize(totalSpeed) + "/s" if totalSpeed > 0 else self.tr("解析中...")
        name_str = f"  {currentName}" if currentName else ""

        tip.setContent(f"{count_str}{name_str}  {progress_str}  {speed_str}")

    def _checkBatchDone(self) -> None:
        done = self._completedCount + self._failedCount
        if done < self._totalCount:
            return

        # 全部完成
        if self._stateToolTip is not None:
            self._stateToolTip.setContent(
                self.tr("全部完成 ({0} 成功，{1} 失败)").format(
                    self._completedCount, self._failedCount
                )
            )
            self._stateToolTip.setState(True)
            self._stateToolTip = None

        self._totalCount = 0
        self._updateAllButton.setEnabled(True)
