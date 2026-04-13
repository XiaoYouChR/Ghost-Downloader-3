# pyright: reportImplicitOverride=false, reportInvalidAbstractMethod=false, reportInconsistentConstructor=false, reportAny=false

"""Public ``Task`` contract for Feature Pack V1."""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass
from dataclasses import replace
from inspect import isawaitable
from pathlib import Path
from typing import ClassVar
from typing import Self

from PySide6.QtCore import QObject
from PySide6.QtCore import Signal

from .config import TaskConfig
from .snapshot import TaskSnapshot
from .stage import TaskStage


def _collectAbstractMethods(cls: type[object]) -> frozenset[str]:
    abstractMethods: set[str] = set()

    for base in cls.__mro__[1:]:
        inheritedAbstracts = getattr(base, "__abstractmethods__", ())
        abstractMethods.update(inheritedAbstracts)

        for attrName, attrValue in cls.__dict__.items():
            if getattr(attrValue, "__isabstractmethod__", False):
                abstractMethods.add(attrName)
            else:
                abstractMethods.discard(attrName)

    return frozenset(abstractMethods)


@dataclass(slots=True, kw_only=True)
class TaskFile:
    """Unified file entry for multi-file tasks and selection dialogs."""

    id: str
    path: str
    size: int
    selected: bool = True
    note: str = ""
    doneBytes: int = 0
    finished: bool = False


class Task(QObject):
    """
    Runtime workflow base class for Feature Pack tasks.

    ``Task`` owns task-level configuration and stage orchestration. Stages keep
    their local execution behavior, while the task supervises ordering,
    projection, and command forwarding.
    """

    stateChanged: ClassVar[Signal] = Signal(str)
    progressChanged: ClassVar[Signal] = Signal(float)
    snapshotChanged: ClassVar[Signal] = Signal(object)
    __abstractmethods__: ClassVar[frozenset[str]] = frozenset()
    id: str
    packId: str
    kind: str
    version: int
    config: TaskConfig
    stages: list[TaskStage]
    currentStageIndex: int

    def __new__(cls: type[Self], *args: object, **kwargs: object) -> Self:
        abstractMethods = cls.__abstractmethods__
        if abstractMethods:
            missingMethods = ", ".join(sorted(abstractMethods))
            raise TypeError(
                (
                    f"Can't instantiate abstract class {cls.__name__}"
                    f" with abstract methods {missingMethods}"
                )
            )

        _ = args
        _ = kwargs
        return super().__new__(cls)

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        cls.__abstractmethods__ = _collectAbstractMethods(cls)

    def __init__(
        self,
        *,
        id: str,
        packId: str,
        kind: str,
        version: int,
        config: TaskConfig,
        stages: list[TaskStage],
    ) -> None:
        super().__init__()
        self.id = id
        self.packId = packId
        self.kind = kind
        self.version = version
        self.config = config
        self.stages = []
        self.currentStageIndex = 0

        for stage in stages:
            self.addStage(stage)

    def addStage(self, stage: TaskStage) -> None:
        """Attach a stage and append it to the workflow."""
        stage.attach(self)
        self.stages.append(stage)

    def configure(self, config: TaskConfig) -> None:
        """
        Replace the current task configuration and forward it to all stages.

        Output synchronization happens before stage-level ``configure()`` so
        stages always observe the latest resolved target.
        """
        self.config = config
        self.syncOutput()
        for stage in self.stages:
            stage.configure(config)

    def editForm(self, _mode: str) -> object | None:
        """Return a declarative edit form or ``None`` when defaults are enough."""
        return None

    @abstractmethod
    def syncOutput(self) -> None:
        """Synchronize the current output target to the workflow stages."""
        raise NotImplementedError

    def iterStages(self) -> Iterable[TaskStage]:
        """Iterate stages in workflow order."""
        return self.stages

    def canPause(self) -> bool:
        """Return whether every stage can pause safely."""
        return all(stage.canPause() for stage in self.stages)

    async def run(self) -> None:
        """Run all stages in order and track the current stage index."""
        for stageIndex, stage in enumerate(self.iterStages()):
            self.currentStageIndex = stageIndex
            await stage.run()

        if self.stages:
            self.currentStageIndex = len(self.stages) - 1

    async def pause(self) -> None:
        """
        Pause the active workflow stage when it exposes a pause coroutine.

        ``Task`` owns pause command routing. Stages that do not expose ``pause()``
        are ignored, which keeps the public base contract minimal while still
        giving the supervisor an explicit command boundary.
        """
        if not self.stages:
            return None

        stageIndex = min(self.currentStageIndex, len(self.stages) - 1)
        activeStage = self.stages[stageIndex]
        pause = getattr(activeStage, "pause", None)

        if callable(pause):
            pauseResult = pause()
            if isawaitable(pauseResult):
                await pauseResult

        return None

    @abstractmethod
    def reset(self) -> None:
        """Reset task-level runtime state so the workflow can be run again."""
        raise NotImplementedError

    @abstractmethod
    def snapshot(self) -> TaskSnapshot:
        """Project runtime state into a Qt-free snapshot."""
        raise NotImplementedError


class SingleFileTask(Task):
    """
    Workflow base class for tasks that produce one final output file.

    ``SingleFileTask`` keeps common single-target behavior in one place and
    treats ``syncOutput()`` as the hook that propagates the resolved output path
    into attached stages.
    """

    @property
    def folder(self) -> Path:
        """Return the configured output folder."""
        return self.config.folder

    @property
    def filename(self) -> str:
        """Return the configured output filename."""
        return self.config.name

    @property
    def path(self) -> Path:
        """Return the resolved single-file output path."""
        return self.folder / self.filename

    def rename(self, name: str) -> None:
        """Rename the single output file through the task config boundary."""
        self.configure(replace(self.config, name=name))

    def move(self, folder: Path) -> None:
        """Move the single output file through the task config boundary."""
        self.configure(replace(self.config, folder=folder))

    @abstractmethod
    def syncOutput(self) -> None:
        """Synchronize ``path`` to workflow stages for this single output."""
        raise NotImplementedError


__all__ = ["SingleFileTask", "Task", "TaskFile"]


Task.__abstractmethods__ = _collectAbstractMethods(Task)
SingleFileTask.__abstractmethods__ = _collectAbstractMethods(SingleFileTask)
