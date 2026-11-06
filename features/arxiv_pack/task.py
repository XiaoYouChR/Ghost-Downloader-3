from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.models.task import Task, TaskStatus, TaskStep
from app.platform.filesystem import deletePath
from http_pack.task import HttpTaskStep


@dataclass(kw_only=True)
class ArxivSourceStep(HttpTaskStep):
    suffix: str = "tar.gz"
    _task: ArxivTask = field(repr=False, init=False)

    @property
    def task(self) -> ArxivTask:
        return self._task

    @property
    def outputPath(self) -> str:
        return str(self.task.toSidePath(None, self.suffix)) if self.task.isSourceEnabled else ""


@dataclass(kw_only=True)
class ArxivBibtexStep(HttpTaskStep):
    _task: ArxivTask = field(repr=False, init=False)

    @property
    def task(self) -> ArxivTask:
        return self._task

    @property
    def outputPath(self) -> str:
        return str(self.task.toSidePath(None, "bib")) if self.task.isBibtexEnabled else ""


@dataclass(kw_only=True, eq=False)
class ArxivTask(Task):
    packId: str = "arxiv"
    canEdit = True
    isSourceEnabled: bool = False
    isBibtexEnabled: bool = False

    @property
    def hasSource(self) -> bool:
        return any(isinstance(step, ArxivSourceStep) for step in self.steps)

    def isStepSelected(self, step: TaskStep, selectedIndexes: set[int]) -> bool:
        if isinstance(step, ArxivSourceStep):
            return self.isSourceEnabled
        if isinstance(step, ArxivBibtexStep):
            return self.isBibtexEnabled
        return True

    def currentSnapshot(self) -> tuple[float, int, int]:
        steps = [step for step in self.steps if self.isStepSelected(step, self.selectedIndexes)]
        progress = sum(step.progress for step in steps) / len(steps)
        return progress, sum(step.speed for step in steps), sum(step.receivedBytes for step in steps)

    def setOptions(self, options: dict[str, Any]) -> None:
        super().setOptions(options)
        previousPaths = [(step, step.outputPath) for step in self.steps]
        self.isSourceEnabled = options.get("isSourceEnabled", self.isSourceEnabled)
        self.isBibtexEnabled = options.get("isBibtexEnabled", self.isBibtexEnabled)
        for step, previousPath in previousPaths:
            if step.status == TaskStatus.COMPLETED or bool(previousPath) == bool(step.outputPath):
                continue
            if previousPath:
                # 关掉未下完的 Side File 时不留半截文件
                step.reset()
                deletePath(Path(previousPath))
                deletePath(Path(f"{previousPath}.ghd"))
            else:
                self.completedAt = 0
        self.fileSize = sum(
            step.fileSize for step in self.steps
            if isinstance(step, HttpTaskStep) and self.isStepSelected(step, self.selectedIndexes) and step.fileSize > 0
        )
        self.updateStatus()
