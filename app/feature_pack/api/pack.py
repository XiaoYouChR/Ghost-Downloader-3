"""Public ``FeaturePack`` contract for Feature Pack V1."""

from __future__ import annotations

from abc import ABC
from abc import abstractmethod
from typing import TYPE_CHECKING

from .input import TaskInput
from .manifest import Manifest
from .settings import SettingSection

if TYPE_CHECKING:
    from .task import Task


class FeaturePack(ABC):
    """
    Core pack contract for source routing and task creation.

    Only ``accepts()``, ``createTask()`` and ``owns()`` are part of the main path.
    Settings and card factories are optional UI-side hooks.
    """

    manifest: Manifest

    @abstractmethod
    def accepts(self, source: str) -> bool:
        """Return whether this pack can create a task for the source."""

    @abstractmethod
    async def createTask(self, data: TaskInput) -> Task | None:
        """Create a task from normalized host input."""

    @abstractmethod
    def owns(self, task: Task) -> bool:
        """Return whether an existing task belongs to this pack."""

    def settingSection(self) -> SettingSection | object | None:
        """Optional settings-page contribution for this pack."""
        return None

    def createTaskCard(
        self,
        _task: Task,
        _parent: object | None = None,
    ) -> object | None:
        """Optional task card factory. Not part of the core routing contract."""
        return None

    def createResultCard(
        self,
        _task: Task,
        _parent: object | None = None,
    ) -> object | None:
        """Optional result card factory. Not part of the core routing contract."""
        return None

    def install(self, _window: object) -> None:
        """Optional host install hook for pack-specific UI wiring."""
        return None


__all__ = ["FeaturePack"]
