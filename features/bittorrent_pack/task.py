from __future__ import annotations

from base64 import b64decode
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from app.models.task import Task, TaskError, TaskStep, TaskFile, TaskStatus
from app.platform.filesystem import deletePath, toPosixPath
from .config import bittorrentConfig


@dataclass(kw_only=True)
class BTFile(TaskFile):
    priority: int = 4

    def __post_init__(self):
        self.relativePath = toPosixPath(self.relativePath)


@dataclass(kw_only=True, eq=False)
class BTTask(Task):
    packId: str = "bt"
    canEdit = True
    fileType = BTFile
    sourceType: str = "torrent"
    torrentData: str = ""
    resumeData: str = ""
    trackers: list[str] = field(default_factory=list)
    shouldSeed: bool = True
    shareRatioPercent: float = 0
    seedingTimeSeconds: int = 0
    isSeeding: bool = False
    stateText: str = ""
    peerCount: int = 0
    seedCount: int = 0
    downloadRate: int = 0
    uploadRate: int = 0

    def __post_init__(self):
        if self.files:
            self.files = [
                item if isinstance(item, BTFile) else BTFile(**item)
                for item in self.files
            ]
        self._fileSelectionVersion = 0
        super().__post_init__()
        self.fileSize = sum(f.size for f in self.files if f.selected)

    @property
    def step(self) -> BTTaskStep:
        return self.steps[0]

    @property
    def magnetTorrentPath(self) -> Path | None:
        if self.sourceType != "magnet":
            return None
        return self.outputFolder / f"{self.name}.torrent"

    @property
    def countSelected(self) -> int:
        return sum(1 for f in self.files if f.selected)

    @property
    def isSingleFile(self) -> bool:
        return len(self.files) == 1

    def toRelativePath(self, file: BTFile) -> str:
        if self.isSingleFile:
            return self.name
        return toPosixPath(Path(self.name, *PurePosixPath(file.relativePath).parts[1:]))

    def priorities(self) -> list[int]:
        return [f.priority if f.selected else 0 for f in self.files]

    def setSelection(self, selectedIndexes: set[int]):
        if not selectedIndexes:
            raise ValueError("至少需要选择一个文件")
        changed = False
        for f in self.files:
            selected = f.index in selectedIndexes
            priority = 4 if selected else 0
            if f.selected != selected or f.priority != priority:
                changed = True
            f.selected = selected
            f.priority = priority
            if not selected:
                f.downloadedBytes = 0
                f.completed = False
        if not changed:
            return
        self._fileSelectionVersion += 1
        self.fileSize = sum(f.size for f in self.files if f.selected)

    def deleteFiles(self) -> bool:
        ok = super().deleteFiles()
        if self.magnetTorrentPath is not None:
            ok = deletePath(self.magnetTorrentPath) and ok
        return ok

    def _move(self, newFolder: Path) -> None:
        from shutil import move
        if self.magnetTorrentPath is not None and self.magnetTorrentPath.exists():
            move(str(self.magnetTorrentPath), str(newFolder / f"{self.name}.torrent"))
        super()._move(newFolder)

    def reset(self) -> TaskStatus:
        result = super().reset()
        self.resumeData = ""
        self.shouldSeed = True
        self.shareRatioPercent = 0
        self.seedingTimeSeconds = 0
        self.isSeeding = False
        self.stateText = ""
        self.peerCount = 0
        self.seedCount = 0
        self.downloadRate = 0
        self.uploadRate = 0
        for f in self.files:
            f.downloadedBytes = 0
            f.completed = False
        return result

@dataclass(kw_only=True)
class BTTaskStep(TaskStep):
    @property
    def outputPath(self) -> str:
        return self.task.outputPath

    async def run(self) -> None:
        from .session import btSession

        task: BTTask = self.task

        if task.countSelected <= 0:
            raise TaskError("至少需要选择一个文件")

        target = Path(task.outputPath)
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.touch() if task.isSingleFile else target.mkdir()

        if task.sourceType == "magnet" and bittorrentConfig.saveMagnetFile.value:
            try:
                task.magnetTorrentPath.write_bytes(b64decode(task.torrentData))
            except Exception as e:
                from loguru import logger
                logger.opt(exception=e).warning("保存 magnet 种子文件失败 {}", task.name)

        await btSession.run(task, self)
        self.setStatus(TaskStatus.COMPLETED)
