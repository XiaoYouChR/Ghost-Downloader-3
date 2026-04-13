# pyright: reportImplicitOverride=false, reportInvalidAbstractMethod=false, reportInconsistentConstructor=false, reportAny=false

"""Public ``TaskStage`` contract for Feature Pack V1."""

from __future__ import annotations

import asyncio
from abc import abstractmethod
from collections.abc import Coroutine
from collections.abc import Mapping
from inspect import isawaitable
from typing import ClassVar
from typing import Self
from typing import cast

from PySide6.QtCore import QObject
from PySide6.QtCore import Signal

from .config import TaskConfig
from .snapshot import StageSnapshot

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


class TaskStage(QObject):
    """
    Runtime stage base class for Feature Pack workflows.

    ``TaskStage`` is a ``QObject``-based active object that owns stage-local
    behavior and projects state through Qt signals and Qt-free snapshots.
    """

    stateChanged: ClassVar[Signal] = Signal(str)
    progressChanged: ClassVar[Signal] = Signal(float)
    snapshotChanged: ClassVar[Signal] = Signal(object)
    failed: ClassVar[Signal] = Signal(str)
    commandRequested: ClassVar[Signal] = Signal(str, object)
    __abstractmethods__: ClassVar[frozenset[str]] = frozenset()
    __recordRegistry__: ClassVar[
        dict[tuple[str, str, int, str, int], type["TaskStage"]]
    ] = {}
    recordTaskPackId: ClassVar[str | None] = None
    recordTaskKind: ClassVar[str | None] = None
    recordTaskVersion: ClassVar[int | None] = None
    recordKind: ClassVar[str | None] = None
    recordVersion: ClassVar[int | None] = None
    id: str
    kind: str
    version: int
    name: str

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

    def __init__(self, *, id: str, kind: str, version: int, name: str) -> None:
        super().__init__()
        self.id = id
        self.kind = kind
        self.version = version
        self.name = name
        self._task: object | None = None
        _ = self.commandRequested.connect(self._onCommandRequested)

    def attach(self, task: object) -> None:
        """Bind this stage to its owning task workflow."""
        self._task = task

    @abstractmethod
    async def run(self) -> None:
        """Execute this stage."""
        raise NotImplementedError

    def canPause(self) -> bool:
        """Return whether this stage can pause safely."""
        return True

    @abstractmethod
    def reset(self) -> None:
        """Reset runtime state so the stage can be run again."""
        raise NotImplementedError

    def configure(self, _config: TaskConfig) -> None:
        """
        Receive the full task configuration from the owning task.

        Subclasses may apply it immediately, defer it, or request a controlled
        stage restart.
        """
        return None

    def requestCommand(self, command: str, payload: object | None = None) -> None:
        """Queue one explicit command for this stage."""
        normalizedCommand = self._normalizeCommand(command)
        self._validateCommandPayload(normalizedCommand, payload)
        self.commandRequested.emit(normalizedCommand, payload)

    def dispatchCommand(self, command: str, payload: object | None = None) -> object | None:
        """Run one explicit command against this stage."""
        normalizedCommand = self._normalizeCommand(command)
        self._validateCommandPayload(normalizedCommand, payload)

        if normalizedCommand == "configure":
            self.configure(cast(TaskConfig, payload))
            return None
        if normalizedCommand == "reset":
            self.reset()
            return None
        if normalizedCommand == "pause":
            pause = getattr(self, "pause", None)
            if callable(pause):
                return pause()
            return None

        return self.dispatchCustomCommand(normalizedCommand, payload)

    def dispatchCustomCommand(
        self,
        command: str,
        payload: object | None = None,
    ) -> object | None:
        """Override to accept stage-specific commands beyond the base contract."""
        _ = payload
        raise ValueError(f"Unsupported task stage command: {command}")

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
            raise ValueError("TaskStage command 不能为空")
        return normalizedCommand

    @staticmethod
    def _validateCommandPayload(
        command: str,
        payload: object | None,
    ) -> None:
        if command == "configure" and not isinstance(payload, TaskConfig):
            raise TypeError("configure command requires TaskConfig payload")

    def persistenceState(self) -> dict[str, object]:
        """Return JSON-safe state used by task persistence."""
        return {}

    def restorePersistentState(self, state: Mapping[str, object]) -> None:
        """Restore runtime state after the owning task has been rebuilt."""
        _ = state
        return None

    @classmethod
    def createPersistentStage(
        cls,
        *,
        id: str,
        kind: str,
        version: int,
        name: str,
        state: Mapping[str, object],
    ) -> "TaskStage":
        """Create one stage instance from a persisted record."""
        _ = id
        _ = kind
        _ = version
        _ = name
        _ = state
        raise NotImplementedError(
            f"{cls.__name__} does not support persisted stage restore"
        )

    @classmethod
    def persistentClass(
        cls,
        *,
        taskPackId: str,
        taskKind: str,
        taskVersion: int,
        kind: str,
        version: int,
    ) -> type["TaskStage"] | None:
        """Look up a persisted stage implementation by stable identity fields."""
        return TaskStage.__recordRegistry__.get(
            (taskPackId, taskKind, taskVersion, kind, version)
        )

    @classmethod
    def _registerPersistentClass(cls) -> None:
        if cls is TaskStage or cls.__abstractmethods__:
            return

        taskPackId = getattr(cls, "recordTaskPackId", None)
        taskKind = getattr(cls, "recordTaskKind", None)
        taskVersion = getattr(cls, "recordTaskVersion", None)
        kind = getattr(cls, "recordKind", None)
        version = getattr(cls, "recordVersion", None)

        if not isinstance(taskPackId, str) or not taskPackId:
            return
        if not isinstance(taskKind, str) or not taskKind:
            return
        if isinstance(taskVersion, bool) or not isinstance(taskVersion, int):
            return
        if not isinstance(kind, str) or not kind:
            return
        if isinstance(version, bool) or not isinstance(version, int):
            return

        recordKey = (taskPackId, taskKind, taskVersion, kind, version)
        existing = TaskStage.__recordRegistry__.get(recordKey)
        if existing is not None and existing is not cls:
            raise ValueError(
                f"Duplicate TaskStage persistence identity: {recordKey!r}"
            )

        TaskStage.__recordRegistry__[recordKey] = cls

    @abstractmethod
    def snapshot(self) -> StageSnapshot:
        """Project runtime state into a Qt-free snapshot."""
        raise NotImplementedError


__all__ = ["TaskStage"]


TaskStage.__abstractmethods__ = _collectAbstractMethods(TaskStage)
