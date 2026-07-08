from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QTimer, Signal
from loguru import logger

from app.config.paths import UPDATE_DIR

if TYPE_CHECKING:
    from app.models.task import Task


class AppUpdateService(QObject):
    """应用自身更新服务

    使用独立下载模式，不进入任务队列，通过 StateToolTip 显示实时进度。
    """

    # 信号：下载开始（解析前立即发出）
    downloadStarted = Signal()
    # 信号：(progress, speed)
    progressChanged = Signal(float, int)
    # 信号：(installerPath)
    downloadSucceeded = Signal(str)
    # 信号：无参数
    downloadFailed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._isDownloading = False
        self._task: Task | None = None
        self._installerPath = ""
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._onTick)

    @property
    def isDownloading(self) -> bool:
        return self._isDownloading

    @property
    def installerPath(self) -> str:
        return self._installerPath

    def downloadAppUpdate(self, url: str, name: str) -> None:
        """下载应用更新包"""
        if self._isDownloading:
            logger.warning("App update is already downloading")
            return

        from app.models.task import TaskOptions
        from app.services.coroutine_runner import coroutineRunner
        from app.services.feature_service import featureService

        self._isDownloading = True
        self._installerPath = ""

        logger.info(f"Starting app update download: {name}")
        self.downloadStarted.emit()

        coroutineRunner.submit(
            featureService.parse(TaskOptions(url=url, outputFolder=UPDATE_DIR)),
            done=self._onParsed,
            failed=self._onFailed,
            name=name,
        )

    def _onParsed(self, task: Task, name: str) -> None:
        """任务创建成功，开始运行"""
        from app.models.task import TaskStatus
        from app.services.coroutine_runner import coroutineRunner

        task.outputFolder = Path(UPDATE_DIR)
        task.name = name
        self._task = task

        task.setStatus(TaskStatus.RUNNING)
        coroutineRunner.submit(
            task.run(),
            done=self._onDone,
            failed=self._onFailed
        )

        self._timer.start()
        logger.info(f"App update task started: {name}")

    def _onTick(self) -> None:
        """定时查询下载进度"""
        if self._task is None:
            return

        try:
            progress, speed, _ = self._task.currentSnapshot()
            self.progressChanged.emit(progress, speed)
        except Exception as e:
            logger.opt(exception=e).warning("Failed to get app update progress")

    def _onDone(self, _=None) -> None:
        """下载完成"""
        self._timer.stop()
        self._isDownloading = False

        if self._task is not None:
            self._installerPath = str(self._task.outputPath)

        self.progressChanged.emit(100.0, 0)
        self.downloadSucceeded.emit(self._installerPath)

        logger.success(f"App update download completed: {self._installerPath}")

    def _onFailed(self, error=None) -> None:
        """下载失败"""
        self._timer.stop()
        self._isDownloading = False

        errorMsg = str(error) if error else "Unknown error"
        logger.error(f"App update download failed: {errorMsg}")

        self.downloadFailed.emit()


# 全局单例
appUpdateService = AppUpdateService()
