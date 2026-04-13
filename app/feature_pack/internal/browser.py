# pyright: reportUnknownVariableType=false

"""Browser-facing snapshot and action helpers for Feature Pack V1."""

from __future__ import annotations

from collections.abc import Callable
from collections.abc import Iterable
from dataclasses import asdict
from dataclasses import dataclass
from enum import StrEnum
from inspect import isawaitable
from pathlib import Path
from typing import final

import orjson

from app.feature_pack.api import Task
from app.feature_pack.api import TaskSnapshot
from app.supports.utils import openFile
from app.supports.utils import openFolder


class BrowserMessageType(StrEnum):
    TASK_SNAPSHOT = "task_snapshot"


class BrowserTaskAction(StrEnum):
    TOGGLE_PAUSE = "toggle_pause"
    CANCEL = "cancel"
    REDOWNLOAD = "redownload"
    OPEN_FILE = "open_file"
    OPEN_FOLDER = "open_folder"


@dataclass(frozen=True, slots=True, kw_only=True)
class BrowserTaskSummary:
    """Stable browser task summary derived from ``TaskSnapshot``."""

    id: str
    packId: str
    kind: str
    name: str
    state: str
    progress: float
    doneBytes: int
    totalBytes: int
    speed: int
    target: str
    folder: str
    canPause: bool
    canOpenFile: bool
    canOpenFolder: bool
    fileExt: str


@dataclass(frozen=True, slots=True, kw_only=True)
class BrowserTaskActionResult:
    """Browser action outcome that can be sent back to the extension."""

    ok: bool
    message: str = ""


def clampProgress(progress: float) -> float:
    return round(max(0.0, min(progress, 100.0)), 2)


def resolveTargetPath(snapshot: TaskSnapshot) -> Path | None:
    target = snapshot.target.strip()
    if not target:
        return None
    return Path(target)


def resolveFolderPath(targetPath: Path | None) -> Path | None:
    if targetPath is None:
        return None
    if targetPath.is_dir():
        return targetPath
    return targetPath.parent


def buildBrowserTaskSummary(task: Task) -> BrowserTaskSummary:
    snapshot = task.snapshot()
    targetPath = resolveTargetPath(snapshot)
    folderPath = resolveFolderPath(targetPath)
    speed = sum(stage.speed for stage in snapshot.stages)

    return BrowserTaskSummary(
        id=snapshot.id,
        packId=snapshot.packId,
        kind=snapshot.kind,
        name=snapshot.name,
        state=snapshot.state,
        progress=clampProgress(snapshot.progress),
        doneBytes=snapshot.doneBytes,
        totalBytes=snapshot.totalBytes,
        speed=speed,
        target=snapshot.target.strip(),
        folder="" if folderPath is None else str(folderPath),
        canPause=snapshot.canPause,
        canOpenFile=bool(targetPath is not None and targetPath.is_file()),
        canOpenFolder=bool(folderPath is not None and folderPath.exists()),
        fileExt="" if targetPath is None else targetPath.suffix.lstrip(".").lower(),
    )


def buildBrowserTaskSnapshot(tasks: Iterable[Task]) -> bytes:
    return orjson.dumps(
        {
            "type": BrowserMessageType.TASK_SNAPSHOT,
            "tasks": [asdict(buildBrowserTaskSummary(task)) for task in tasks],
        }
    )


def _openBrowserFileTarget(path: Path) -> None:
    openFile(path)


def _openBrowserFolderTarget(path: Path) -> None:
    if path.is_dir():
        openFile(path)
        return
    openFolder(path)


@final
class BrowserTaskActionMapper:
    """Map browser task actions onto the Feature Pack V1 task surface."""

    def __init__(
        self,
        *,
        startTask: Callable[[Task], object],
        cancelTask: Callable[[Task], object],
        openFilePath: Callable[[Path], None] = _openBrowserFileTarget,
        openFolderPath: Callable[[Path], None] = _openBrowserFolderTarget,
    ) -> None:
        self._startTask = startTask
        self._cancelTask = cancelTask
        self._openFilePath = openFilePath
        self._openFolderPath = openFolderPath

    async def execute(
        self,
        *,
        task: Task,
        action: BrowserTaskAction | str,
    ) -> BrowserTaskActionResult:
        try:
            normalizedAction = (
                action
                if isinstance(action, BrowserTaskAction)
                else BrowserTaskAction(action)
            )
        except ValueError:
            return BrowserTaskActionResult(ok=False, message="不支持的任务操作")

        try:
            if normalizedAction == BrowserTaskAction.TOGGLE_PAUSE:
                return await self._togglePause(task)
            if normalizedAction == BrowserTaskAction.CANCEL:
                return await self._cancel(task)
            if normalizedAction == BrowserTaskAction.REDOWNLOAD:
                return await self._redownload(task)
            if normalizedAction == BrowserTaskAction.OPEN_FILE:
                return self._openFile(task)
            return self._openFolder(task)
        except Exception as error:
            return BrowserTaskActionResult(ok=False, message=repr(error))

    async def _togglePause(self, task: Task) -> BrowserTaskActionResult:
        snapshot = task.snapshot()
        state = snapshot.state.strip().lower()

        if state == "running":
            if not snapshot.canPause:
                return BrowserTaskActionResult(ok=False, message="当前任务不支持暂停")

            await task.pause()
            return BrowserTaskActionResult(ok=True)

        if state == "completed":
            return BrowserTaskActionResult(ok=False, message="任务已完成")

        await self._invoke(self._startTask, task)
        return BrowserTaskActionResult(ok=True)

    async def _cancel(self, task: Task) -> BrowserTaskActionResult:
        await self._invoke(self._cancelTask, task)
        return BrowserTaskActionResult(ok=True)

    async def _redownload(self, task: Task) -> BrowserTaskActionResult:
        await self._invoke(self._cancelTask, task)
        task.reset()
        await self._invoke(self._startTask, task)
        return BrowserTaskActionResult(ok=True)

    def _openFile(self, task: Task) -> BrowserTaskActionResult:
        targetPath = resolveTargetPath(task.snapshot())
        if targetPath is None or not targetPath.is_file():
            return BrowserTaskActionResult(ok=False, message="文件尚未生成")

        self._openFilePath(targetPath)
        return BrowserTaskActionResult(ok=True)

    def _openFolder(self, task: Task) -> BrowserTaskActionResult:
        targetPath = resolveTargetPath(task.snapshot())
        folderPath = resolveFolderPath(targetPath)
        if folderPath is None or not folderPath.exists():
            return BrowserTaskActionResult(ok=False, message="目录不存在")

        self._openFolderPath(folderPath)
        return BrowserTaskActionResult(ok=True)

    async def _invoke(
        self,
        callback: Callable[[Task], object],
        task: Task,
    ) -> None:
        result = callback(task)
        if isawaitable(result):
            await result


__all__ = [
    "BrowserMessageType",
    "BrowserTaskAction",
    "BrowserTaskActionMapper",
    "BrowserTaskActionResult",
    "BrowserTaskSummary",
    "buildBrowserTaskSnapshot",
    "buildBrowserTaskSummary",
    "clampProgress",
    "resolveFolderPath",
    "resolveTargetPath",
]
