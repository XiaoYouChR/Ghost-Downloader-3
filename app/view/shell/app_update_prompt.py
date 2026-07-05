from __future__ import annotations

from pathlib import Path
from typing import Callable, TYPE_CHECKING

from PySide6.QtCore import QObject, Qt
from PySide6.QtWidgets import QApplication
from qfluentwidgets import (
    FluentIcon, InfoBar, InfoBarPosition, PrimaryPushButton, StateToolTip,
)

from app.format import toReadableSize
from app.services.app_update_service import appUpdateService
from app.signal_bus import signalBus

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget


class AppUpdatePrompt(QObject):
    """应用更新 UI 提示管理器

    负责显示应用下载进度（StateToolTip）和完成通知（InfoBar）
    """

    def __init__(self, currentWindow: Callable[[], "QWidget | None"], parent=None):
        super().__init__(parent)
        self._currentWindow = currentWindow
        self._stateToolTip: StateToolTip | None = None
        self._infoBar: InfoBar | None = None

        appUpdateService.downloadStarted.connect(self._onDownloadStarted)
        appUpdateService.progressChanged.connect(self._onProgressChanged)
        appUpdateService.downloadSucceeded.connect(self._onDownloadSucceeded)
        appUpdateService.downloadFailed.connect(self._onDownloadFailed)
        signalBus.activationRequested.connect(self._onWindowShown)

    def _onDownloadStarted(self) -> None:
        """解析阶段立即显示 StateToolTip"""
        toolTip = self._ensureStateToolTip()
        if toolTip is not None:
            toolTip.setContent(self.tr("正在解析下载链接..."))

    def _onProgressChanged(self, percent: float, speed: int) -> None:
        """更新下载进度"""
        toolTip = self._ensureStateToolTip()
        if toolTip is not None:
            toolTip.setContent(f"{percent:.1f}%  ·  {toReadableSize(speed)}/s")

    def _onDownloadSucceeded(self, installerPath: str) -> None:
        """下载成功"""
        if self._stateToolTip is not None:
            self._stateToolTip.setContent(self.tr("下载完成"))
            self._stateToolTip.setState(True)
            self._stateToolTip = None

        window = self._currentWindow()
        if window is not None:
            self._showInstallPrompt(window)
        else:
            self._notifyDownloaded(installerPath)

    def _onDownloadFailed(self) -> None:
        """下载失败"""
        if self._stateToolTip is not None:
            self._stateToolTip.setContent(self.tr("下载新版本失败"))
            self._stateToolTip.setState(True)
            self._stateToolTip = None

    def _onWindowShown(self) -> None:
        """窗口显示时恢复状态"""
        window = self._currentWindow()
        if window is None:
            return

        if appUpdateService.installerPath and self._infoBar is None:
            self._showInstallPrompt(window)
        elif appUpdateService.isDownloading:
            self._ensureStateToolTip()

    def _ensureStateToolTip(self) -> StateToolTip | None:
        """确保 StateToolTip 存在"""
        if self._stateToolTip is not None:
            return self._stateToolTip

        window = self._currentWindow()
        if window is None:
            return None

        toolTip = StateToolTip(self.tr("正在下载新版本"), "0%", window)
        toolTip.move(toolTip.getSuitablePos())
        toolTip.destroyed.connect(self._onStateToolTipDestroyed)
        toolTip.show()
        self._stateToolTip = toolTip
        return toolTip

    def _onStateToolTipDestroyed(self) -> None:
        self._stateToolTip = None

    def _showInstallPrompt(self, window: QWidget) -> None:
        """显示安装提示"""
        infoBar = InfoBar(
            icon=FluentIcon.UPDATE,
            title=self.tr("新版本已下载"),
            content=self.tr("是否立即安装？安装程序启动后软件将退出。"),
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            duration=-1,
            position=InfoBarPosition.BOTTOM_RIGHT,
            parent=window,
        )
        installButton = PrimaryPushButton(FluentIcon.PLAY, self.tr("立即安装"))
        installButton.clicked.connect(self._install)
        infoBar.addWidget(installButton)
        infoBar.destroyed.connect(self._onInfoBarDestroyed)
        infoBar.show()
        self._infoBar = infoBar

    def _onInfoBarDestroyed(self) -> None:
        self._infoBar = None

    def _notifyDownloaded(self, installerPath: str) -> None:
        """通过系统通知提示下载完成"""
        from app.platform.desktop_notification import notifier
        if notifier is None:
            return

        from app.services.coroutine_runner import coroutineRunner
        coroutineRunner.submit(notifier.send(
            title=self.tr("新版本已下载"),
            message=self.tr("点击以安装 {0}").format(Path(installerPath).name),
            on_clicked=lambda: signalBus.activationRequested.emit(),
        ))

    def _install(self) -> None:
        """启动安装程序"""
        from app.platform.desktop import launchInstaller

        try:
            launchInstaller(appUpdateService.installerPath)
        except OSError:
            window = self._currentWindow()
            if window is not None:
                InfoBar.error(
                    window.tr("启动安装程序失败"),
                    window.tr("请手动运行安装程序完成更新"),
                    duration=-1,
                    position=InfoBarPosition.BOTTOM_RIGHT,
                    parent=window,
                )
            return

        QApplication.instance().quit()
