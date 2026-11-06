from __future__ import annotations

import asyncio
import os
import shutil
import zipfile
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.models.task import Task, TaskError, TaskFile, TaskStatus, TaskStep, deletePlaceholder
from app.platform.filesystem import deletePath, splitStemExt
from http_pack.task import HttpTaskStep
from .sparse import SparseView


@dataclass(kw_only=True)
class ZipEntry(TaskFile):
    innerPath: str = ""
    localHeaderOffset: int = 0
    windowEnd: int = 0


@dataclass(kw_only=True, eq=False)
class ZipTask(Task):
    packId: str = "zip"
    canEdit = True
    fileType = ZipEntry
    tailOffset: int = 0
    metadataEncoding: str = ""

    @property
    def archiveStep(self) -> HttpTaskStep:
        return self.steps[0]

    @property
    def extractStep(self) -> ZipExtractStep:
        return self.steps[1]

    @property
    def isWhole(self) -> bool:
        return len(self.selectedIndexes) == len(self.files)

    @property
    def archivePath(self) -> Path:
        return self.outputFolder / self.name

    @property
    def folderPath(self) -> Path:
        return self.outputFolder / splitStemExt(self.name)[0]

    @property
    def hasArchive(self) -> bool:
        return self.archiveStep.status == TaskStatus.COMPLETED or self.archiveStep.receivedBytes > 0

    @property
    def isOutputFolder(self) -> bool:
        return not self.isWhole

    @property
    def outputPath(self) -> str:
        return str(self.archivePath if self.isWhole else self.folderPath)

    def isStepSelected(self, step: TaskStep, selectedIndexes: set[int]) -> bool:
        isWhole = len(selectedIndexes) == len(self.files)
        return not isWhole if isinstance(step, ZipExtractStep) else isWhole

    def setSelection(self, selectedIndexes):
        super().setSelection(selectedIndexes)
        if self.isWhole:
            self.fileSize = self.archiveStep.fileSize
        elif self.extractStep.status == TaskStatus.COMPLETED and any(
                file.selected and not file.completed for file in self.files):
            self.extractStep.reset()

    def reset(self) -> TaskStatus:
        for file in self.files:
            file.downloadedBytes, file.completed = 0, False
        return super().reset()

    def relink(self, newTask: Task) -> None:
        if not isinstance(newTask, ZipTask):
            raise TaskError("该链接不能用于更换")
        old, new = self.archiveStep, newTask.archiveStep
        if (new.fileSize != old.fileSize
                or [(f.relativePath, f.size) for f in newTask.files]
                != [(f.relativePath, f.size) for f in self.files]):
            raise TaskError("新链接的内容与原任务不同，请重新添加任务")
        new.status = TaskStatus.PAUSED if old.status in {TaskStatus.RUNNING, TaskStatus.FAILED} else old.status
        new.progress, new.receivedBytes = old.progress, old.receivedBytes
        new._bindTask(self)
        if self.extractStep.status in {TaskStatus.RUNNING, TaskStatus.FAILED}:
            self.extractStep.status = TaskStatus.PAUSED
            self.extractStep.error = None
        self.url = newTask.url
        self.steps[0] = new
        self.updateStatus()

    def deleteFiles(self) -> None:
        super().deleteFiles()
        if not self.isWhole and self.hasArchive:
            deletePath(self.archivePath)
        if self.isWhole and any(file.completed for file in self.files):
            deletePath(self.folderPath)

    def deletePlaceholders(self) -> None:
        if self.archiveStep.status != TaskStatus.COMPLETED and (self.isWhole or self.hasArchive):
            deletePath(self.archivePath)
        deletePath(Path(f"{self.archivePath}.ghd"))
        deletePath(Path(f"{self.folderPath}.ghd"))
        for path in self.placeholderPaths:
            deletePlaceholder(path)


def toSpans(files: list[ZipEntry]) -> list[list[ZipEntry]]:
    spans: list[list[ZipEntry]] = []
    for file in files:
        if spans and spans[-1][-1].windowEnd == file.localHeaderOffset:
            spans[-1].append(file)
        else:
            spans.append([file])
    return spans


def extractFile(archive: zipfile.ZipFile, innerPath: str, path: Path) -> None:
    info = archive.getinfo(innerPath)
    with archive.open(info) as source, open(path, "wb") as target:
        shutil.copyfileobj(source, target, 1 << 20)
    with suppress(ValueError):
        modifiedAt = datetime(*info.date_time).timestamp()
        os.utime(path, (modifiedAt, modifiedAt))


@dataclass(kw_only=True)
class ZipExtractStep(TaskStep):
    async def run(self, reportSpeed, waitForSpeedLimit) -> None:
        task: ZipTask = self.task
        self._reportSpeed, self._waitForSpeedLimit = reportSpeed, waitForSpeedLimit
        self._spans: list[tuple[HttpTaskStep, list[ZipEntry]]] = []
        task.partPath.mkdir(parents=True, exist_ok=True)
        tailPath = task.partPath / "tail"
        await task.archiveStep.rangeStep(task.tailOffset, task.archiveStep.fileSize, tailPath).run(
            reportSpeed, waitForSpeedLimit)
        view = SparseView(task.archiveStep.fileSize)
        view.addSegment(task.tailOffset, tailPath)
        archive = await asyncio.to_thread(zipfile.ZipFile, view, metadata_encoding=task.metadataEncoding or None)
        slots = asyncio.Semaphore(max(1, task.archiveStep.subworkerCount))
        extracting = asyncio.Lock()
        supervisor = asyncio.create_task(self._supervise())
        try:
            while spans := toSpans([file for file in task.files if file.selected and not file.completed]):
                async with asyncio.TaskGroup() as group:
                    for span in spans:
                        group.create_task(self._runSpan(span, archive, view, slots, extracting))
        except ExceptionGroup as eg:
            raise eg.exceptions[0] from eg
        finally:
            supervisor.cancel()
            with suppress(asyncio.CancelledError):
                await supervisor
            archive.close()
            view.close()
        deletePath(task.partPath)
        self.receivedBytes = sum(file.windowEnd - file.localHeaderOffset for file in task.files if file.selected)

    async def _runSpan(self, span: list[ZipEntry], archive: zipfile.ZipFile, view: SparseView,
                       slots: asyncio.Semaphore, extracting: asyncio.Lock) -> None:
        task: ZipTask = self.task
        start, end = span[0].localHeaderOffset, span[-1].windowEnd
        path = task.partPath / f"{start}-{end}"
        step = task.archiveStep.rangeStep(start, end, path)
        self._spans.append((step, span))
        try:
            async with slots:
                await step.run(self._reportSpeed, self._waitForSpeedLimit)
            async with extracting:
                view.addSegment(start, path)
                try:
                    for file in span:
                        if not file.selected:
                            continue
                        target = task.toFilePath(file.index)
                        temporary = Path(f"{path}.out")
                        await asyncio.to_thread(extractFile, archive, file.innerPath, temporary)
                        target.parent.mkdir(parents=True, exist_ok=True)
                        os.replace(temporary, target)
                        file.downloadedBytes, file.completed = file.size, True
                finally:
                    view.removeSegment(start)
        finally:
            self._spans.remove((step, span))
        deletePath(path)

    async def _supervise(self) -> None:
        while True:
            selected = [file for file in self.task.files if file.selected]
            total = sum(file.windowEnd - file.localHeaderOffset for file in selected)
            done = sum(file.windowEnd - file.localHeaderOffset for file in selected if file.completed)
            extracted = sum(file.windowEnd - file.localHeaderOffset
                            for _, span in self._spans for file in span if file.completed)
            self.receivedBytes = done + sum(step.receivedBytes for step, _ in self._spans) - extracted
            self.speed = sum(step.speed for step, _ in self._spans)
            self.progress = self.receivedBytes / total * 100 if total else 0
            await asyncio.sleep(1)
