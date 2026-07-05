from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget
from qfluentwidgets import (
    FluentIcon, InfoBar, InfoBarPosition, PrimaryPushButton, StateToolTip,
)

from app.format import toReadableSize

if TYPE_CHECKING:
    from app.models.pack import BinaryRuntime


class RuntimeUpdatePrompt:
    """运行时更新 UI 提示管理器

    负责显示运行时下载进度（StateToolTip）和完成通知（InfoBar）
    """

    def __init__(self, window: QWidget):
        self._window = window
        self._toolTips: dict[str, StateToolTip] = {}

    def showProgress(self, runtimeId: str, runtimeName: str) -> None:
        """显示下载进度提示"""
        if runtimeId in self._toolTips:
            return

        toolTip = StateToolTip(
            self._window.tr("正在下载 {0}").format(runtimeName),
            "0%",
            self._window
        )
        toolTip.move(toolTip.getSuitablePos())
        toolTip.destroyed.connect(lambda: self._onToolTipDestroyed(runtimeId))
        toolTip.show()
        self._toolTips[runtimeId] = toolTip

    def updateProgress(self, runtimeId: str, progress: float, speed: int) -> None:
        """更新下载进度"""
        toolTip = self._toolTips.get(runtimeId)
        if toolTip is not None:
            toolTip.setContent(f"{progress:.1f}%  ·  {toReadableSize(speed)}/s")

    def showSuccess(self, runtimeId: str, runtimeName: str) -> None:
        """显示下载成功"""
        toolTip = self._toolTips.get(runtimeId)
        if toolTip is not None:
            toolTip.setContent(self._window.tr("下载完成"))
            toolTip.setState(True)
            self._toolTips.pop(runtimeId, None)

        InfoBar.success(
            self._window.tr("安装成功"),
            self._window.tr("{0} 已安装完成").format(runtimeName),
            duration=3000,
            position=InfoBarPosition.TOP,
            parent=self._window,
        )

    def showError(self, runtimeId: str, runtimeName: str, errorMsg: str) -> None:
        """显示下载失败"""
        toolTip = self._toolTips.get(runtimeId)
        if toolTip is not None:
            toolTip.setContent(self._window.tr("下载失败"))
            toolTip.setState(True)
            self._toolTips.pop(runtimeId, None)

        InfoBar.error(
            self._window.tr("安装失败"),
            self._window.tr("{0}: {1}").format(runtimeName, errorMsg),
            duration=-1,
            position=InfoBarPosition.TOP,
            parent=self._window,
        )

    def _onToolTipDestroyed(self, runtimeId: str) -> None:
        self._toolTips.pop(runtimeId, None)


class BatchRuntimeUpdateCard(QWidget):
    """批量运行时更新卡片

    提供"检查全部更新"和批量下载功能
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
        self._checkAllButton.clicked.connect(self._onCheckAllClicked)
        self._updateAllButton.clicked.connect(self._onUpdateAllClicked)

    def _onCheckAllClicked(self) -> None:
        """检查所有运行时更新"""
        from app.services.runtime_status import runtimeStatusService

        # 刷新所有运行时状态
        for runtime in self._runtimes:
            if runtime.canInstall:
                runtimeStatusService.refresh(runtime, force=True)

        # TODO: 实现版本比对逻辑，当前直接启用"全部更新"按钮
        self._updateAllButton.setEnabled(True)

        InfoBar.info(
            self.tr("检查完成"),
            self.tr("已刷新所有运行时状态"),
            duration=2000,
            position=InfoBarPosition.TOP,
            parent=self.window(),
        )

    def _onUpdateAllClicked(self) -> None:
        """更新所有可安装的运行时"""
        from app.services.runtime_update_service import runtimeUpdateService
        from app.services.runtime_status import runtimeStatusService

        updateCount = 0
        for runtime in self._runtimes:
            if not runtime.canInstall:
                continue

            # 检查是否已在下载中
            if runtimeUpdateService.isDownloading(runtime.runtimeId):
                continue

            # 启动下载
            runtimeUpdateService.downloadRuntime(runtime)
            updateCount += 1

        if updateCount > 0:
            InfoBar.info(
                self.tr("开始更新"),
                self.tr("正在更新 {0} 个运行时").format(updateCount),
                duration=3000,
                position=InfoBarPosition.TOP,
                parent=self.window(),
            )
        else:
            InfoBar.warning(
                self.tr("无可用更新"),
                self.tr("所有运行时都在下载中或不支持自动安装"),
                duration=3000,
                position=InfoBarPosition.TOP,
                parent=self.window(),
            )
