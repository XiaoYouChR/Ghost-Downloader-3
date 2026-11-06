"""Android projection of existing HTTP edit options."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.models.task import Task
    from .task import HttpTaskStep


def editFields(task: Task) -> dict[str, Any]:
    step: HttpTaskStep = task.steps[0]  # type: ignore[assignment]
    return {
        "url": task.url,
        "headers": dict(step.headers),
        "clientProfile": step.clientProfile,
        "userAgent": step.userAgent,
        "subworkerCount": step.subworkerCount,
    }
