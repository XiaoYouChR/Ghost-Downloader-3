from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QTimer, Signal
from loguru import logger

if TYPE_CHECKING:
    from app.models.pack import BinaryRuntime
    from app.models.task import Task


class RuntimeUpdateStatus(Enum):
    IDLE = auto()
    CHECKING = auto()
    AVAILABLE = auto()
    DOWNLOADING = auto()
    SUCCEEDED = auto()
    FAILED = auto()


@dataclass(frozen=True)
class RuntimeUpdateInfo:
    """运行时更新信息"""
    runtimeId: str
    name: str
    currentVersion: str
    latestVersion: str
    downloadUrl: str
    releaseNotes: str = ""


class RuntimeUpdateService(QObject):
    """统一管理所有 BinaryRuntime 的更新和下载

    采用多实例并发模式，每个 Runtime 可以独立并发更新。
    使用独立下载逻辑（类似应用更新），不进入任务队列。
    """

    # 信号：(runtimeId, progress, speed)
    progressChanged = Signal(str, float, int)
    # 信号：(runtimeId, installedPath)
    downloadSucceeded = Signal(str, str)
    # 信号：(runtimeId, errorMessage)
    downloadFailed = Signal(str, str)
    # 信号：(runtimeId, updateInfo)
    updateAvailable = Signal(str, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        # 每个 Runtime 的下载状态
        self._statuses: dict[str, RuntimeUpdateStatus] = {}
        # 每个 Runtime 的下载任务
        self._tasks: dict[str, Task] = {}
        # 每个 Runtime 的进度查询定时器
        self._timers: dict[str, QTimer] = {}
        # 每个 Runtime 的安装路径
        self._installedPaths: dict[str, str] = {}

    def status(self, runtimeId: str) -> RuntimeUpdateStatus:
        """获取指定 Runtime 的更新状态"""
        return self._statuses.get(runtimeId, RuntimeUpdateStatus.IDLE)

    def installedPath(self, runtimeId: str) -> str:
        """获取指定 Runtime 的安装路径"""
        return self._installedPaths.get(runtimeId, "")

    def isDownloading(self, runtimeId: str) -> bool:
        """检查指定 Runtime 是否正在下载"""
        return self._statuses.get(runtimeId) == RuntimeUpdateStatus.DOWNLOADING

    def checkUpdate(self, runtime: BinaryRuntime) -> None:
        """检查指定 Runtime 是否有可用更新

        注意：当前实现直接触发下载，未来可以扩展版本比对逻辑
        """
        runtimeId = runtime.runtimeId
        if self._statuses.get(runtimeId) == RuntimeUpdateStatus.CHECKING:
            return

        # TODO: 实现版本检查逻辑，目前直接标记为可用
        self._statuses[runtimeId] = RuntimeUpdateStatus.AVAILABLE
        logger.info(f"Runtime update check initiated for {runtime.name}")

    def downloadRuntime(self, runtime: BinaryRuntime) -> None:
        """下载并安装/更新指定的 BinaryRuntime

        使用独立下载模式，复用 runtime.installTask() 创建任务，
        但不加入任务队列，而是独立运行并通过 StateToolTip 显示进度。
        """
        runtimeId = runtime.runtimeId

        if self.isDownloading(runtimeId):
            logger.warning(f"Runtime {runtime.name} is already downloading")
            return

        from app.services.coroutine_runner import coroutineRunner

        self._statuses[runtimeId] = RuntimeUpdateStatus.DOWNLOADING
        self._installedPaths[runtimeId] = ""

        logger.info(f"Starting download for runtime: {runtime.name} ({runtimeId})")

        coroutineRunner.submit(
            runtime.installTask(),
            done=self._onTaskCreated,
            failed=self._onCreateFailed,
            runtimeId=runtimeId,
            name=runtime.name,
        )

    def _onTaskCreated(self, task: Task, runtimeId: str, name: str) -> None:
        """任务创建成功，开始运行"""
        from app.models.task import TaskStatus
        from app.services.coroutine_runner import coroutineRunner

        # installTask() 已经正确设置了输出路径，不能覆盖
        self._tasks[runtimeId] = task

        task.setStatus(TaskStatus.RUNNING)
        coroutineRunner.submit(
            task.run(),
            done=self._onDownloadDone,
            failed=self._onDownloadFailed,
            runtimeId=runtimeId,
        )

        # 启动进度监控定时器
        timer = QTimer(self)
        timer.setInterval(1000)
        timer.timeout.connect(lambda: self._onTick(runtimeId))
        timer.start()
        self._timers[runtimeId] = timer

        logger.info(f"Task started for runtime: {name} ({runtimeId})")

    def _onCreateFailed(self, error, runtimeId: str, name: str) -> None:
        """任务创建失败"""
        self._statuses[runtimeId] = RuntimeUpdateStatus.FAILED
        errorMsg = str(error) if error else "未知错误"
        logger.error(f"Failed to create install task for {name}: {errorMsg}")
        self.downloadFailed.emit(runtimeId, errorMsg)

    def _onTick(self, runtimeId: str) -> None:
        """定时查询下载进度"""
        task = self._tasks.get(runtimeId)
        if task is None:
            return

        try:
            progress, speed, _ = task.currentSnapshot()
            logger.debug(f"RuntimeUpdateService: Emitting progress for {runtimeId}: {progress:.1f}%, {speed} B/s")
            self.progressChanged.emit(runtimeId, progress, speed)
        except Exception as e:
            logger.opt(exception=e).warning(f"Failed to get progress for {runtimeId}")

    def _onDownloadDone(self, _=None, runtimeId: str = "") -> None:
        """下载完成"""
        # 停止定时器
        timer = self._timers.pop(runtimeId, None)
        if timer is not None:
            timer.stop()

        task = self._tasks.get(runtimeId)
        if task is None:
            return

        self._statuses[runtimeId] = RuntimeUpdateStatus.SUCCEEDED
        installedPath = str(task.outputPath) if task.outputPath else ""
        self._installedPaths[runtimeId] = installedPath

        # 发送最终进度
        self.progressChanged.emit(runtimeId, 100.0, 0)
        self.downloadSucceeded.emit(runtimeId, installedPath)

        logger.success(f"Runtime download completed: {runtimeId} -> {installedPath}")

    def _onDownloadFailed(self, error=None, runtimeId: str = "") -> None:
        """下载失败"""
        # 停止定时器
        timer = self._timers.pop(runtimeId, None)
        if timer is not None:
            timer.stop()

        self._statuses[runtimeId] = RuntimeUpdateStatus.FAILED
        errorMsg = str(error) if error else "下载失败"
        logger.error(f"Runtime download failed: {runtimeId} - {errorMsg}")
        self.downloadFailed.emit(runtimeId, errorMsg)

    def cancelDownload(self, runtimeId: str) -> None:
        """取消指定 Runtime 的下载"""
        task = self._tasks.get(runtimeId)
        if task is not None:
            try:
                task.cancel()
            except Exception as e:
                logger.opt(exception=e).warning(f"Failed to cancel task for {runtimeId}")

        timer = self._timers.pop(runtimeId, None)
        if timer is not None:
            timer.stop()

        self._statuses[runtimeId] = RuntimeUpdateStatus.IDLE
        self._tasks.pop(runtimeId, None)
        logger.info(f"Download cancelled for runtime: {runtimeId}")


# 全局单例
runtimeUpdateService = RuntimeUpdateService()
