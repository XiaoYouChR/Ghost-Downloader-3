from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QProcess, QTimer, Qt, Signal
from PySide6.QtWidgets import QApplication
from loguru import logger
from qfluentwidgets import FluentIcon, InfoBar, InfoBarPosition, PushButton, StateToolTip

from app.config.paths import UPDATE_DIR
from app.format import toReadableSize

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget
    from app.update import ReleaseAsset


def isFullUpdateAsset(asset: ReleaseAsset) -> bool:
    """完整"下载→安装→退出"流程仅在 Windows 且资源为 .exe 时启用。"""
    return sys.platform == "win32" and asset.name.lower().endswith(".exe")


# 模块级单例：同一时刻只允许一个更新下载
_activeController: UpdateDownloadController | None = None


def startUpdateDownload(asset: ReleaseAsset, window: QWidget) -> None:
    """自更新的公共入口。所有入口（新版本 InfoBar、未来的版本详情弹窗）都汇入这里。

    - Windows + .exe：走完整流程（下载到 update 文件夹 → StateToolTip 进度
      → 完成 InfoBar → 立即安装并退出）。
    - 其余情况：回退为普通下载任务（进列表、留普通下载目录、不退出）。
    """
    global _activeController

    if not isFullUpdateAsset(asset):
        _fallbackDownload(asset, window)
        return

    # 单例防护：已有更新下载在进行。用 isValid 排除已被 Qt 销毁（如下载中关窗）的悬空引用。
    from shiboken6 import isValid
    if _activeController is not None and isValid(_activeController):
        InfoBar.info(
            window.tr("更新下载中"), window.tr("新版本正在下载，请稍候"),
            duration=3000, position=InfoBarPosition.BOTTOM_RIGHT, parent=window,
        )
        return

    _activeController = UpdateDownloadController(asset, window)
    _activeController.finished.connect(_onControllerFinished)
    _activeController.start()


def _onControllerFinished() -> None:
    global _activeController
    _activeController = None


def _fallbackDownload(asset: ReleaseAsset, window: QWidget) -> None:
    """非 exe / 非 Windows：沿用普通任务下载逻辑（进列表、持久化、普通下载目录）。"""
    from app.models.task import TaskOptions
    from app.services.coroutine_runner import coroutineRunner
    from app.services.feature_service import featureService
    from app.services.task_service import taskService

    def onParseFailed(error: str) -> None:
        InfoBar.error(
            window.tr("创建下载任务失败"), str(error),
            duration=3000, position=InfoBarPosition.BOTTOM_RIGHT, parent=window,
        )

    coroutineRunner.submit(
        featureService.parse(TaskOptions(url=asset.downloadUrl)),
        done=taskService.add,
        failed=onParseFailed,
        owner=window,
    )
    InfoBar.info(
        window.tr("开始下载更新"), window.tr("更新包将下载到默认下载目录，请下载完成后手动安装"),
        duration=5000, position=InfoBarPosition.BOTTOM_RIGHT, parent=window,
    )


class UpdateDownloadController(QObject):
    """驱动一次 Windows exe 的完整更新流程：下载 → 进度提示 → 安装并退出。"""

    finished = Signal()  # 无论成功/失败/取消，结束时发出，用于释放单例

    def __init__(self, asset: ReleaseAsset, window: QWidget):
        super().__init__(window)
        self._asset = asset
        self._window = window
        self._task = None
        self._stateToolTip: StateToolTip | None = None
        self._progressTimer = QTimer(self)
        self._progressTimer.setInterval(1000)
        self._progressTimer.timeout.connect(self._refreshProgress)

    def start(self) -> None:
        from app.config.paths import clearUpdateDir
        from app.models.task import TaskOptions
        from app.services.coroutine_runner import coroutineRunner
        from features.http_pack.pack import buildHttpTask
        from features.http_pack.task import UpdateTask

        clearUpdateDir()  # 下载前清空，确保目录干净
        UPDATE_DIR.mkdir(parents=True, exist_ok=True)

        self._stateToolTip = StateToolTip(
            self._window.tr("正在下载新版本"),
            self._window.tr("准备中..."),
            self._window,
        )
        self._stateToolTip.move(self._stateToolTip.getSuitablePos())
        self._stateToolTip.show()

        options = TaskOptions(url=self._asset.downloadUrl, outputFolder=UPDATE_DIR)
        coroutineRunner.submit(
            buildHttpTask(options, taskClass=UpdateTask),
            done=self._onTaskBuilt,
            failed=self._onDownloadFailed,
            owner=self,
        )

    def _onTaskBuilt(self, task) -> None:
        from app.services.task_service import taskService

        self._task = task
        taskService.transientCompleted.connect(self._onTransientCompleted)
        taskService.transientFailed.connect(self._onTransientFailed)
        taskService.addTransient(task)
        self._progressTimer.start()

    def _refreshProgress(self) -> None:
        if self._task is None or self._stateToolTip is None:
            return
        progress, speed, receivedBytes = self._task.currentSnapshot()
        fileSize = self._task.fileSize
        if fileSize > 0:
            self._stateToolTip.setContent(
                self._window.tr("{0}% · {1}/{2} · {3}/s").format(
                    int(progress),
                    toReadableSize(receivedBytes),
                    toReadableSize(fileSize),
                    toReadableSize(speed),
                )
            )
        else:
            self._stateToolTip.setContent(
                self._window.tr("{0} · {1}/s").format(
                    toReadableSize(receivedBytes), toReadableSize(speed)
                )
            )

    def _onTransientCompleted(self, task) -> None:
        if task is not self._task:
            return
        self._disconnectService()
        self._progressTimer.stop()
        self._refreshProgress()
        if self._stateToolTip is not None:
            self._stateToolTip.setContent(self._window.tr("下载完成"))
            self._stateToolTip.setState(True)
            self._stateToolTip = None
        self._promptInstall()
        self.finished.emit()

    def _onTransientFailed(self, task, error: str) -> None:
        if task is not self._task:
            return
        self._disconnectService()
        self._progressTimer.stop()
        if self._stateToolTip is not None:
            self._stateToolTip.setContent(self._window.tr("下载失败: {0}").format(error))
            self._stateToolTip.setState(True)
            self._stateToolTip = None
        self.finished.emit()

    def _onDownloadFailed(self, error: str) -> None:
        """构造任务阶段（探测）失败。"""
        self._progressTimer.stop()
        if self._stateToolTip is not None:
            self._stateToolTip.setContent(self._window.tr("下载失败: {0}").format(error))
            self._stateToolTip.setState(True)
            self._stateToolTip = None
        self.finished.emit()

    def _disconnectService(self) -> None:
        from app.services.task_service import taskService
        try:
            taskService.transientCompleted.disconnect(self._onTransientCompleted)
            taskService.transientFailed.disconnect(self._onTransientFailed)
        except (RuntimeError, TypeError):
            pass


    def _promptInstall(self) -> None:
        installerPath = Path(self._task.outputPath)
        # 用显式 Horizontal 构造：InfoBar.success 便捷方法默认 Vertical，addWidget 按钮会溢出窗口
        infoBar = InfoBar(
            icon=FluentIcon.UPDATE,
            title=self._window.tr("新版本已下载"),
            content=self._window.tr("是否立即安装？安装程序将启动，本程序会随即退出。"),
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            duration=-1,
            position=InfoBarPosition.BOTTOM_RIGHT,
            parent=self._window,
        )
        installButton = PushButton(FluentIcon.UPDATE, self._window.tr("立即安装"))
        installButton.clicked.connect(lambda: self._installAndQuit(installerPath, infoBar))
        infoBar.addWidget(installButton)
        infoBar.show()

    def _installAndQuit(self, installerPath: Path, infoBar) -> None:
        if not installerPath.exists():
            InfoBar.error(
                self._window.tr("安装失败"), self._window.tr("找不到安装程序文件"),
                duration=3000, position=InfoBarPosition.BOTTOM_RIGHT, parent=self._window,
            )
            return
        started = QProcess.startDetached(str(installerPath))
        if not started:
            logger.error("启动安装程序失败 {}", installerPath)
            InfoBar.error(
                self._window.tr("安装失败"),
                self._window.tr("无法启动安装程序，请手动运行"),
                duration=5000, position=InfoBarPosition.BOTTOM_RIGHT, parent=self._window,
            )
            return
        infoBar.close()
        QApplication.quit()



