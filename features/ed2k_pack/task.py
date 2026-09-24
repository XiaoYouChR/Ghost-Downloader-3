from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from app.models.task import Task, TaskError, TaskStep, TaskStatus
from .python_ed2k import Transfer


@dataclass(kw_only=True, eq=False)
class ED2kTask(Task):
    packId: str = "ed2k"
    canSeed = True
    fileHash: str = ""
    activePeerCount: int | None = None
    totalPeerCount: int = 0
    uploadRate: int = 0
    seedingTimeSeconds: int = 0

    def reset(self) -> TaskStatus:
        self.fileHash = ""
        self.activePeerCount = None
        self.totalPeerCount = 0
        self.uploadRate = 0
        self.seedingTimeSeconds = 0
        return super().reset()

    async def runSeeding(self, isManual: bool) -> None:
        from .session import ed2kSession

        def onProgress(t: Transfer, elapsed: int):
            self.uploadRate = t.uploadRate
            self.activePeerCount = t.activePeers
            self.totalPeerCount = t.peers
            self.seedingTimeSeconds = elapsed

        try:
            await ed2kSession.runSeeding(
                self.url, self.fileHash, self.seedingTimeSeconds, isManual, onProgress)
        finally:
            self.uploadRate = 0

    def deleteFiles(self):
        if self.fileHash:
            from .session import ed2kSession
            ed2kSession.remove(self.fileHash)
        super().deleteFiles()


@dataclass(kw_only=True)
class ED2kTaskStep(TaskStep):
    async def run(self, reportSpeed, waitForSpeedLimit) -> None:
        from .session import RunResult, ed2kSession

        task: ED2kTask = self.task

        def onStarted(result: RunResult):
            task.fileHash = result.fileHash
            task.name = result.name
            if result.fileSize:
                task.fileSize = result.fileSize

        def onProgress(t: Transfer):
            task.uploadRate = t.uploadRate
            task.activePeerCount = t.activePeers
            task.totalPeerCount = t.peers
            self.receivedBytes = t.received
            self.speed = t.downloadRate
            reportSpeed(t.downloadRate)
            if t.size > 0:
                task.fileSize = t.size
                self.progress = min(99.9, t.received / t.size * 100)

        await ed2kSession.run(
            task.url, task.fileHash, task.name, task.outputFolder,
            onStarted=onStarted,
            onProgress=onProgress,
        )
        self.setStatus(TaskStatus.COMPLETED)


@dataclass(kw_only=True)
class ED2kInstallStep(TaskStep):
    canPause = False
    binaryPath: str = ""

    async def run(self, reportSpeed, waitForSpeedLimit) -> None:
        path = Path(self.binaryPath)
        if not path.is_file():
            raise TaskError("{name} 未安装，请在设置中安装", name="goed2kd")
        if sys.platform != "win32":
            path.chmod(path.stat().st_mode | 0o755)
        self.setStatus(TaskStatus.COMPLETED)
