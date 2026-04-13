# pyright: reportImplicitOverride=false, reportInvalidAbstractMethod=false, reportInconsistentConstructor=false, reportAny=false, reportUnknownVariableType=false, reportUnknownMemberType=false

"""Public ``Task`` contract for Feature Pack V1."""

from __future__ import annotations

import asyncio
from abc import abstractmethod
from collections.abc import Coroutine
from collections.abc import Iterable
from collections.abc import Mapping
from dataclasses import dataclass
from dataclasses import replace
from inspect import isawaitable
from pathlib import Path
from typing import ClassVar
from typing import cast
from typing import Self

from PySide6.QtCore import QObject
from PySide6.QtCore import Signal

from .config import TaskConfig
from .form import EditMode
from .form import TaskForm
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
    commandRequested: ClassVar[Signal] = Signal(str, object)
    stageCommandForwarded: ClassVar[Signal] = Signal(object, str, object)
    __abstractmethods__: ClassVar[frozenset[str]] = frozenset()
    __recordRegistry__: ClassVar[dict[tuple[str, str, int], type["Task"]]] = {}
    recordPackId: ClassVar[str | None] = None
    recordKind: ClassVar[str | None] = None
    recordVersion: ClassVar[int | None] = None
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
        cls._registerPersistentClass()

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
        _ = self.commandRequested.connect(self._onCommandRequested)

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
        _ = self.dispatchToStages("configure", config)

    def editForm(self, _mode: EditMode) -> TaskForm | None:
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

        pauseResult = self.dispatchToCurrentStage("pause")
        if isawaitable(pauseResult):
            await pauseResult

        return None

    def requestCommand(self, command: str, payload: object | None = None) -> None:
        """Queue one explicit card-to-task command."""
        normalizedCommand = self._normalizeCommand(command)
        self._validateCommandPayload(normalizedCommand, payload)
        self.commandRequested.emit(normalizedCommand, payload)

    def dispatchCommand(self, command: str, payload: object | None = None) -> object | None:
        """Handle one explicit command at the task boundary."""
        normalizedCommand = self._normalizeCommand(command)
        self._validateCommandPayload(normalizedCommand, payload)

        if normalizedCommand == "configure":
            self.configure(cast(TaskConfig, payload))
            return None
        if normalizedCommand == "pause":
            return self.dispatchToCurrentStage("pause")
        if normalizedCommand == "reset":
            self.reset()
            return None

        return self.dispatchCustomCommand(normalizedCommand, payload)

    def dispatchCustomCommand(
        self,
        command: str,
        payload: object | None = None,
    ) -> object | None:
        """Override to accept task-specific commands beyond the base contract."""
        _ = payload
        raise ValueError(f"Unsupported task command: {command}")

    def dispatchToCurrentStage(
        self,
        command: str,
        payload: object | None = None,
    ) -> object | None:
        """Forward one command to the currently active stage."""
        if not self.stages:
            return None

        stageIndex = min(self.currentStageIndex, len(self.stages) - 1)
        return self.dispatchToStage(self.stages[stageIndex], command, payload)

    def dispatchToStages(
        self,
        command: str,
        payload: object | None = None,
    ) -> tuple[object | None, ...]:
        """Forward one command to all stages in workflow order."""
        return tuple(
            self.dispatchToStage(stage, command, payload)
            for stage in self.stages
        )

    def dispatchToStage(
        self,
        stage: TaskStage,
        command: str,
        payload: object | None = None,
    ) -> object | None:
        """Forward one command to one attached stage through the task boundary."""
        if stage not in self.stages:
            raise ValueError(f"Stage {stage.id!r} is not attached to task {self.id!r}")

        normalizedCommand = self._normalizeCommand(command)
        self.stageCommandForwarded.emit(stage, normalizedCommand, payload)
        return stage.dispatchCommand(normalizedCommand, payload)

    def _onCommandRequested(self, command: str, payload: object) -> None:
        commandResult = self.dispatchCommand(command, payload)
        self._consumeCommandResult(commandResult)

    def _consumeCommandResult(self, commandResult: object | None) -> None:
        if not isawaitable(commandResult):
            return
        coroutine = cast(Coroutine[object, object, object], commandResult)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            _ = asyncio.run(coroutine)
            return

        _ = loop.create_task(coroutine)

    @staticmethod
    def _normalizeCommand(command: str) -> str:
        normalizedCommand = command.strip().lower()
        if not normalizedCommand:
            raise ValueError("Task command 不能为空")
        return normalizedCommand

    @staticmethod
    def _validateCommandPayload(
        command: str,
        payload: object | None,
    ) -> None:
        if command == "configure" and not isinstance(payload, TaskConfig):
            raise TypeError("configure command requires TaskConfig payload")

    def persistenceState(self) -> dict[str, object]:
        """Return JSON-safe task-local state used by task persistence."""
        return {"currentStageIndex": self.currentStageIndex}

    def restorePersistentState(self, state: Mapping[str, object]) -> None:
        """Restore task-local runtime state after stages have been rebuilt."""
        rawStageIndex = state.get("currentStageIndex")
        if isinstance(rawStageIndex, int) and not isinstance(rawStageIndex, bool):
            self.currentStageIndex = rawStageIndex
        return None

    @classmethod
    def createPersistentTask(
        cls,
        *,
        id: str,
        packId: str,
        kind: str,
        version: int,
        config: TaskConfig,
        stages: list[TaskStage],
        state: Mapping[str, object],
    ) -> "Task":
        """Create one task instance from a persisted record."""
        _ = id
        _ = packId
        _ = kind
        _ = version
        _ = config
        _ = stages
        _ = state
        raise NotImplementedError(
            f"{cls.__name__} does not support persisted task restore"
        )

    @classmethod
    def persistentClass(
        cls,
        *,
        packId: str,
        kind: str,
        version: int,
    ) -> type["Task"] | None:
        """Look up a persisted task implementation by stable identity fields."""
        return Task.__recordRegistry__.get((packId, kind, version))

    @classmethod
    def _registerPersistentClass(cls) -> None:
        if cls is Task or cls.__abstractmethods__:
            return

        packId = getattr(cls, "recordPackId", None)
        kind = getattr(cls, "recordKind", None)
        version = getattr(cls, "recordVersion", None)

        if not isinstance(packId, str) or not packId:
            return
        if not isinstance(kind, str) or not kind:
            return
        if isinstance(version, bool) or not isinstance(version, int):
            return

        recordKey = (packId, kind, version)
        existing = Task.__recordRegistry__.get(recordKey)
        if existing is not None and existing is not cls:
            raise ValueError(
                f"Duplicate Task persistence identity: {recordKey!r}"
            )

        Task.__recordRegistry__[recordKey] = cls

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


class MultiFileTask(Task):
    """
    Workflow base class for tasks that produce multiple logical outputs.

    ``MultiFileTask`` keeps the shared file container, resolved root path, and
    selection summary in one place so packs only need to implement stage output
    propagation and any extra task-specific behavior.
    """

    files: list[TaskFile]

    def __init__(
        self,
        *,
        id: str,
        packId: str,
        kind: str,
        version: int,
        config: TaskConfig,
        stages: list[TaskStage],
        files: list[TaskFile],
    ) -> None:
        self.files = files
        super().__init__(
            id=id,
            packId=packId,
            kind=kind,
            version=version,
            config=config,
            stages=stages,
        )

    @property
    def root(self) -> Path:
        """Return the resolved root directory for multi-file outputs."""
        return self.config.folder / self.config.name

    @property
    def fileCount(self) -> int:
        """Return how many logical files the task currently exposes."""
        return len(self.files)

    @property
    def selectedCount(self) -> int:
        """Return how many files are currently selected."""
        return sum(1 for file in self.files if file.selected)

    @property
    def selectedIds(self) -> set[str]:
        """Return the ids of the currently selected files."""
        return {file.id for file in self.files if file.selected}

    def select(self, ids: set[str]) -> None:
        """
        Replace the current file selection using stable ``TaskFile.id`` values.

        Unknown ids are rejected explicitly so callers do not silently drift out
        of sync with the task's current file list.
        """
        knownIds = {file.id for file in self.files}
        unknownIds = ids - knownIds
        if unknownIds:
            unknownList = ", ".join(sorted(unknownIds))
            raise ValueError(f"Unknown task file ids: {unknownList}")

        for file in self.files:
            file.selected = file.id in ids

    def dispatchCustomCommand(
        self,
        command: str,
        payload: object | None = None,
    ) -> object | None:
        if command != "select":
            return super().dispatchCustomCommand(command, payload)

        if not isinstance(payload, set) or not all(
            isinstance(fileId, str) for fileId in payload
        ):
            raise TypeError("select command requires set[str] payload")

        self.select(cast(set[str], payload))
        return None

    def persistenceState(self) -> dict[str, object]:
        """Persist generic multi-file selection state alongside task state."""
        state = super().persistenceState()
        state["files"] = [
            {
                "id": file.id,
                "path": file.path,
                "size": file.size,
                "selected": file.selected,
                "note": file.note,
                "doneBytes": file.doneBytes,
                "finished": file.finished,
            }
            for file in self.files
        ]
        return state

    def restorePersistentState(self, state: Mapping[str, object]) -> None:
        """Restore generic multi-file entries and selected ids."""
        super().restorePersistentState(state)
        rawFiles = state.get("files")
        if not isinstance(rawFiles, list):
            return

        restoredFiles: list[TaskFile] = []
        for rawFile in rawFiles:
            if not isinstance(rawFile, Mapping):
                continue

            fileId = rawFile.get("id")
            filePath = rawFile.get("path")
            fileSize = rawFile.get("size")
            if (
                not isinstance(fileId, str)
                or not isinstance(filePath, str)
                or isinstance(fileSize, bool)
                or not isinstance(fileSize, int)
            ):
                continue

            rawDoneBytes = rawFile.get("doneBytes", 0)
            doneBytes = (
                rawDoneBytes
                if isinstance(rawDoneBytes, int) and not isinstance(rawDoneBytes, bool)
                else 0
            )
            note = rawFile.get("note")
            restoredFiles.append(
                TaskFile(
                    id=fileId,
                    path=filePath,
                    size=fileSize,
                    selected=bool(rawFile.get("selected", True)),
                    note=note if isinstance(note, str) else "",
                    doneBytes=doneBytes,
                    finished=bool(rawFile.get("finished", False)),
                )
            )

        self.files = restoredFiles


__all__ = ["MultiFileTask", "SingleFileTask", "Task", "TaskFile"]


Task.__abstractmethods__ = _collectAbstractMethods(Task)
SingleFileTask.__abstractmethods__ = _collectAbstractMethods(SingleFileTask)
MultiFileTask.__abstractmethods__ = _collectAbstractMethods(MultiFileTask)
