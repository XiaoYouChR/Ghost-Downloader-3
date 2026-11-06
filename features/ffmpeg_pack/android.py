"""Android View adapter for FFmpegPack."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from http_pack.android import editFields

if TYPE_CHECKING:
    from .task import FFmpegTask

__all__ = ["UI_CLASS", "draftFields", "editFields", "setTrim"]

UI_CLASS = "com.xychr.ghostdownloader.features.ffmpeg_pack.FFmpegUi"


def draftFields(task: FFmpegTask) -> dict[str, Any]:
    return {
        "duration": task.duration,
        "startTime": task.startTime,
        "endTime": task.endTime,
        "hasPreview": False,
    }


def setTrim(task: FFmpegTask, startTime: int, endTime: int) -> None:
    duration = task.duration
    if not (0 <= startTime < (endTime or duration) <= duration):
        raise ValueError("Invalid trim range")
    task.setTimeRange(startTime, endTime)
