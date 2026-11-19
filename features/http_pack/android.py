"""Android projection of existing HTTP edit options."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.task import Task


def editFields(task: Task) -> dict:
    step = task.steps[0]
    return {
        "url": task.url,
        "headers": dict(step.headers),
        "clientProfile": step.clientProfile,
        "userAgent": step.userAgent,
        "subworkerCount": step.subworkerCount,
    }
