"""Android View adapter for M3U8Pack."""

from app.models.task import TaskStatus

UI_CLASS = "com.xychr.ghostdownloader.packs.M3u8Ui"


def editFields(task) -> dict:
    step = task.steps[0]
    return {
        "headers": dict(step.headers),
        **({"recordLimit": step.recordLimit} if task.isLive else {}),
        "decryptionKeys": list(step.decryptionKeys),
        "decryptionKeyFile": step.decryptionKeyFile,
        "muxImports": list(step.muxImports),
    }


def taskFields(task) -> dict:
    if not task.isLive:
        return {}
    step = task.steps[0] if task.steps else None
    isRunning = task.status == TaskStatus.RUNNING
    return {
        "progressMode": "indeterminate" if isRunning else "determinate",
        "statusText": ("recording" if not step or step.liveStatus != "Waiting" else "waiting")
                      if isRunning else "",
        "canStop": isRunning and step is not None,
        "canPause": False,
        "packFields": {
            "liveElapsed": step.liveElapsed if step else "",
            "recordLimit": step.recordLimit if step else "",
        },
    }


def stop(task) -> None:
    if task.isLive and task.status == TaskStatus.RUNNING and task.steps:
        task.steps[0].terminate()
