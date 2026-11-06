from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .task import FtpStep, FtpTask


def editFields(task: FtpTask) -> dict[str, Any]:
    step: FtpStep = task.steps[0]  # type: ignore[assignment]
    return {"subworkerCount": step.subworkerCount}
