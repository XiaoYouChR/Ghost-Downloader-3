"""Android View adapter for M3U8Pack."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.i18n import N
from app.models.task import TaskStatus

if TYPE_CHECKING:
    from .task import M3U8Task, M3U8TaskStep

UI_CLASS = "com.xychr.ghostdownloader.features.m3u8_pack.M3u8Ui"


def editFields(task: M3U8Task) -> dict[str, Any]:
    step: M3U8TaskStep = task.steps[0]
    return {
        "headers": dict(step.headers),
        **({"recordLimit": step.recordLimit} if task.isLive else {}),
        "decryptionKeys": list(step.decryptionKeys),
        "decryptionKeyFile": step.decryptionKeyFile,
        "muxImports": list(step.muxImports),
    }


def optionFields(task: M3U8Task) -> dict[str, Any]:
    if len(task.streams) <= 1:
        return {}
    step: M3U8TaskStep = task.steps[0]
    return {"streams": toStreamOptions(task.streams), "selectVideo": step.selectVideo}


def toStreamOptions(streams: list[dict[str, Any]]) -> list[dict[str, str]]:
    options = [{"key": "", "label": "默认（最佳）"}]
    for stream in streams:
        width, height = stream.get("width", 0), stream.get("height", 0)
        details = [v for v in (stream.get("codecs") or "",
                               f"{stream['frameRate']}fps" if stream.get("frameRate") else "") if v]
        label = f"{width}×{height}" + (f" ({', '.join(details)})" if details else "")
        selectExpr = f'res="{width}x{height}"'
        if stream.get("frameRate"):
            selectExpr += f':frame="{int(stream["frameRate"])}*"'
        options.append({"key": selectExpr, "label": label})
    return options


def taskFields(task: M3U8Task) -> dict[str, Any]:
    if not task.isLive:
        return {}
    step: M3U8TaskStep | None = task.steps[0] if task.steps else None
    isRunning = task.status == TaskStatus.RUNNING
    waiting = step is not None and step.liveStatus == "Waiting"
    return {
        "progressMode": "indeterminate" if isRunning else "determinate",
        "statusText": (N("TaskState", "等待中") if waiting else N("TaskState", "录制中"))
                      if isRunning else "",
        "canStop": isRunning and step is not None,
        "packFields": {
            "liveElapsed": step.liveElapsed if step else "",
            "recordLimit": step.recordLimit if step else "",
        },
    }


def stop(task: M3U8Task) -> None:
    if task.isLive and task.status == TaskStatus.RUNNING and task.steps:
        step: M3U8TaskStep = task.steps[0]
        step.terminate()
