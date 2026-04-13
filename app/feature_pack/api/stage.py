# pyright: reportImplicitOverride=false, reportInvalidAbstractMethod=false, reportInconsistentConstructor=false, reportAny=false

"""Public ``TaskStage`` contract for Feature Pack V1."""

from __future__ import annotations

from abc import abstractmethod
from typing import ClassVar
from typing import Self

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
    __abstractmethods__: ClassVar[frozenset[str]] = frozenset()
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

    def __init__(self, *, id: str, kind: str, version: int, name: str) -> None:
        super().__init__()
        self.id = id
        self.kind = kind
        self.version = version
        self.name = name
        self._task: object | None = None

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

    @abstractmethod
    def snapshot(self) -> StageSnapshot:
        """Project runtime state into a Qt-free snapshot."""
        raise NotImplementedError


__all__ = ["TaskStage"]


TaskStage.__abstractmethods__ = _collectAbstractMethods(TaskStage)
