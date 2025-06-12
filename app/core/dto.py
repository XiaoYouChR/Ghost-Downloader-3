from dataclasses import dataclass
from uuid import UUID

from app.core.enums import TaskManagerStatus, HttpVersion


@dataclass
class WorkerInfo:
    __slots__ = ("startPos", "progress", "endPos")
    startPos: int
    progress: int
    endPos: int
    
@dataclass
class TaskProgressInfo:
    __slots__ = ("workerInfos",)
    workerInfos: list[WorkerInfo]

@dataclass
class TaskManagerInfo:
    taskID: UUID
    taskManagerStatus: TaskManagerStatus
    taskProgressInfo: TaskProgressInfo
    url: str
    fileSize: int
    fileName: str
    filePath: str
    headers: dict
    proxy: str
    verify: bool
    httpVersion: HttpVersion

@dataclass
class OverallTaskManagerInfo:
    taskManagerInfos: list[TaskManagerInfo]
