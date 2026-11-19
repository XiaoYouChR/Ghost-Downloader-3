from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .task import FtpTask


def editFields(task: FtpTask) -> dict:
    return {"subworkerCount": task.steps[0].subworkerCount}
