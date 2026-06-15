import asyncio
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from loguru import logger

from app.bases.models import Task, TaskStage, TaskStatus
from app.supports.utils import removePath, toSafeFilename


@dataclass
class BTFile:
    index: int
    path: str
    size: int
    selected: bool = True
    priority: int = 4
    downloadedBytes: int = 0
    completed: bool = False

    def __post_init__(self):
        self.path = str(PurePosixPath(str(self.path).replace("\\", "/")))


@dataclass(kw_only=True, eq=False)
class BTTask(Task):
    packId: str = "bt"
    sourceType: str
    torrentData: str
    resumeData: str = ""
    trackers: list[str] = field(default_factory=list)
    files: list[BTFile] = field(default_factory=list)
    shareRatioPercent: float = 0
    seedingTimeSeconds: int = 0
    isSeeding: bool = False
    stateText: str = ""
    peerCount: int = 0
    seedCount: int = 0
    downloadRate: int = 0
    uploadRate: int = 0

    def __post_init__(self):
        self.files = [
            item if isinstance(item, BTFile) else BTFile(**item)
            for item in self.files
        ]
        self.fileSelectionVersion = 0
        self.title = toSafeFilename(self.title, fallback="torrent")
        super().__post_init__()
        self.fileSize = sum(file.size for file in self.files if file.selected)
        self._updateSlot()

    @property
    def stage(self) -> TaskStage:
        return self.stages[0]

    @property
    def magnetTorrentPath(self) -> Path | None:
        if self.sourceType != "magnet":
            return None
        return self.path / f"{self.title}.torrent"

    @property
    def countSelected(self) -> int:
        return sum(1 for file in self.files if file.selected)

    @property
    def countAll(self) -> int:
        return len(self.files)

    @property
    def isSingleFile(self) -> bool:
        return len(self.files) == 1

    @property
    def hasUnselected(self) -> bool:
        return not all(file.selected for file in self.files)

    def mapPath(self, file: BTFile) -> str:
        if self.isSingleFile:
            return self.title
        return str(PurePosixPath(self.title, *PurePosixPath(file.path).parts[1:]))

    def priorities(self) -> list[int]:
        return [file.priority if file.selected else 0 for file in self.files]

    def setSelection(self, selectedIndexes: set[int]):
        if not selectedIndexes:
            raise ValueError("至少需要选择一个文件")

        changed = False
        for file in self.files:
            selected = file.index in selectedIndexes
            priority = 4 if selected else 0
            if file.selected != selected or file.priority != priority:
                changed = True
            file.selected = selected
            file.priority = priority
            if not selected:
                file.downloadedBytes = 0
                file.completed = False

        if not changed:
            return

        self.fileSelectionVersion += 1
        self.fileSize = sum(file.size for file in self.files if file.selected)

    def cleanup(self):
        super().cleanup()
        if self.magnetTorrentPath is not None:
            removePath(self.magnetTorrentPath)

    def reopen(self) -> bool:
        if self.stage.status != TaskStatus.COMPLETED:
            return False

        if not any(file.selected and not file.completed for file in self.files):
            return False

        self.isSeeding = False
        self._updateSlot()
        self.stateText = "已添加新的下载文件"
        self.stage.setStatus(TaskStatus.PAUSED)
        self.stage.receivedBytes = sum(file.downloadedBytes for file in self.files if file.selected)
        if self.fileSize > 0:
            self.stage.progress = self.stage.receivedBytes / self.fileSize * 100
        else:
            self.stage.progress = 0
        return True

    def updateProgress(self, fileBytes: list[int]):
        for file in self.files:
            if not file.selected:
                file.downloadedBytes = 0
                file.completed = False
                continue
            downloaded = fileBytes[file.index] if file.index < len(fileBytes) else 0
            file.downloadedBytes = downloaded
            file.completed = file.size > 0 and downloaded >= file.size

    def reset(self) -> TaskStatus:
        result = super().reset()
        self.resumeData = ""
        self.shareRatioPercent = 0
        self.seedingTimeSeconds = 0
        self.isSeeding = False
        self._updateSlot()
        self.stateText = ""
        self.peerCount = 0
        self.seedCount = 0
        self.downloadRate = 0
        self.uploadRate = 0
        for file in self.files:
            file.downloadedBytes = 0
            file.completed = False
        return result

    def _updateSlot(self):
        self.usesSlot = not self.isSeeding

    async def run(self):
        from .session import btSessionService

        try:
            await btSessionService.lease(self)
        except asyncio.CancelledError:
            self.stateText = "已暂停做种" if self.isSeeding else "已暂停下载"
            self.isSeeding = False
            self._updateSlot()
            self.stage.setStatus(TaskStatus.PAUSED)
            logger.info("{} 停止下载", self.title)
            raise
        except Exception as e:
            if not self.stage.error:
                self.stage.setError(e)
            logger.opt(exception=e).error("{} 下载失败", self.title)
            raise
        else:
            self.isSeeding = False
            self._updateSlot()
            self.stateText = "已自动暂停做种"
            self.stage.setStatus(TaskStatus.COMPLETED)
            self.stage.progress = 100
            self.stage.speed = 0

    def __hash__(self):
        return hash(self.taskId)
