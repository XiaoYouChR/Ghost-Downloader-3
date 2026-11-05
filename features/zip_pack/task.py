from __future__ import annotations

import asyncio
import os
import shutil
import zipfile
from contextlib import suppress
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from loguru import logger

from app.models.task import Task, TaskFile, TaskOptions, TaskStatus, TaskStep
from app.platform.filesystem import deletePath
from http_pack.pack import fetchRange
from http_pack.task import HttpTaskStep
from .sparse import SparseView


@dataclass(kw_only=True)
class ZipEntry(TaskFile):
    name: str = ""
    localHeaderOffset: int = 0
    windowEnd: int = 0


@dataclass(kw_only=True, eq=False)
class ZipTask(Task):
    packId: str = "zip"
    canEdit = True
    fileType = ZipEntry
    archiveSize: int = 0
    tailOffset: int = 0
    metadataEncoding: str = ""

    @property
    def isWhole(self) -> bool:
        return all(file.selected for file in self.files)

    @property
    def isOutputFolder(self) -> bool:
        return not self.isWhole

    @property
    def outputPath(self) -> str:
        return str(self.outputFolder / (f"{self.name}.zip" if self.isWhole else self.name))

    @property
    def wholeStep(self) -> HttpTaskStep:
        return next(step for step in self.steps if step.fileIndex is None)

    @property
    def tailPath(self) -> Path:
        return Path(self.partPath, "tail")

    def toWindowPath(self, fileIndex: int) -> Path:
        return Path(f"{self.toFilePath(fileIndex)}.ghd", "window")

    def _isStepSelected(self, step: TaskStep) -> bool:
        if step.fileIndex is None:
            return self.isWhole
        return not self.isWhole and super()._isStepSelected(step)

    def setSelection(self, selectedIndexes):
        super().setSelection(selectedIndexes)
        if self.isWhole:
            self.fileSize = self.archiveSize

    def currentSnapshot(self) -> tuple[float, int, int]:
        steps = [step for step in self.steps if isinstance(step, HttpTaskStep) and self._isStepSelected(step)]
        total = sum(step.fileSize for step in steps)
        receivedBytes = sum(step.receivedBytes for step in steps)
        progress = receivedBytes / total * 100 if total else 0.0
        return progress, sum(step.speed for step in steps), receivedBytes

    def canReuseProgress(self, probed: TaskOptions) -> bool:
        return probed.file.fileSize == self.archiveSize

    def replaceWith(self, probed: TaskOptions) -> None:
        isSameArchive = self.canReuseProgress(probed)
        self.url = probed.url
        for position, old in enumerate(self.steps):
            if not isinstance(old, HttpTaskStep):
                continue
            new = deepcopy(probed.template)
            for name in ("stepId", "stepIndex", "fileIndex", "httpByteOffset", "fileSize", "subworkerCount"):
                setattr(new, name, getattr(old, name))
            if isSameArchive:
                new.status, new.progress, new.receivedBytes = old.status, old.progress, old.receivedBytes
            new._bindTask(self)
            self.steps[position] = new
        if not isSameArchive:
            self.archiveSize = self.wholeStep.fileSize = probed.file.fileSize
            self.setSelection([file.index for file in self.files])
        self.updateStatus()

    def deletePlaceholders(self) -> None:
        for file in self.files:
            if not file.completed:
                deletePath(Path(f"{self.toFilePath(file.index)}.ghd"))
        super().deletePlaceholders()

    async def run(self, reportSpeed, waitForSpeedLimit):
        if self.isWhole:
            return await super().run(reportSpeed, waitForSpeedLimit)
        try:
            if not self.tailPath.exists():
                tail = await fetchRange(self.wholeStep, self.tailOffset, self.archiveSize - self.tailOffset)
                self.tailPath.parent.mkdir(parents=True, exist_ok=True)
                self.tailPath.write_bytes(tail)

            stepsByFile: dict[int, list[TaskStep]] = {}
            for step in self.pendingSteps():
                stepsByFile.setdefault(step.fileIndex, []).append(step)
            slots = asyncio.Semaphore(max(1, self.wholeStep.subworkerCount))

            async def runFile(steps: list[TaskStep]) -> None:
                async with slots:
                    for step in steps:
                        if isinstance(step, HttpTaskStep):
                            step.filePath = str(self.toWindowPath(step.fileIndex))
                        await self.runStep(step, reportSpeed, waitForSpeedLimit)

            try:
                async with asyncio.TaskGroup() as group:
                    for steps in stepsByFile.values():
                        group.create_task(runFile(steps))
            except ExceptionGroup as eg:
                raise eg.exceptions[0] from eg
            if self.status == TaskStatus.COMPLETED:
                deletePath(self.partPath)
        except asyncio.CancelledError:
            logger.info("{} stopped", self.name)
            raise
        except Exception as e:
            logger.opt(exception=e).error("{} failed", self.name)
            raise


@dataclass(kw_only=True)
class ZipExtractStep(TaskStep):
    canPause = False

    @property
    def outputPath(self) -> str:
        return str(self.task.toFilePath(self.fileIndex))

    async def run(self, reportSpeed, waitForSpeedLimit) -> None:
        task: ZipTask = self.task
        entry = next(file for file in task.files if file.index == self.fileIndex)
        window = task.toWindowPath(self.fileIndex)
        view = SparseView(task.archiveSize, [(task.tailOffset, task.tailPath),
                                             (entry.localHeaderOffset, window)])
        with view, zipfile.ZipFile(view, metadata_encoding=task.metadataEncoding or None) as archive:
            info = archive.getinfo(entry.name)
            with archive.open(info) as source, open(self.outputPath, "wb") as target:
                await asyncio.to_thread(shutil.copyfileobj, source, target, 1 << 20)
        with suppress(ValueError):
            modifiedAt = datetime(*info.date_time).timestamp()
            os.utime(self.outputPath, (modifiedAt, modifiedAt))
        deletePath(window.parent)
        self.progress = 100
