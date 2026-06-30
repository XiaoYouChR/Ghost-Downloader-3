from __future__ import annotations

from dataclasses import fields as dataclass_fields, is_dataclass
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.task import Task, TaskStep


def toDict(obj: Any) -> Any:
    from app.models.task import Task, TaskStep, TaskStatus

    if isinstance(obj, TaskStatus):
        return obj.name
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, (TaskStep, Task)):
        result = {
            f.name: toDict(getattr(obj, f.name))
            for f in dataclass_fields(obj) if f.repr
        }
        baseName = "TaskStep" if isinstance(obj, TaskStep) else "Task"
        if type(obj).__name__ != baseName:
            result["type"] = type(obj).__name__
        return result
    if is_dataclass(obj):
        return {
            f.name: toDict(getattr(obj, f.name))
            for f in dataclass_fields(obj) if f.repr
        }
    if isinstance(obj, list):
        return [toDict(item) for item in obj]
    if isinstance(obj, dict):
        return {k: toDict(v) for k, v in obj.items()}
    return obj


def fromDict(data: Any, cls: type) -> Any:
    from app.models.task import Task, TaskStep, TaskStatus, TaskFile

    if isinstance(data, (bytes, bytearray, str)):
        import json
        obj = json.loads(data)
    else:
        obj = dict(data)

    typeName = obj.pop("type", None)
    if isinstance(typeName, str):
        if issubclass(cls, TaskStep):
            targetCls = TaskStep._registry.get(typeName, cls)
        elif issubclass(cls, Task):
            targetCls = Task._registry.get(typeName, cls)
        else:
            targetCls = cls
    else:
        targetCls = cls

    if "status" in obj and isinstance(obj["status"], str):
        obj["status"] = TaskStatus[obj["status"]]
    if "outputFolder" in obj and isinstance(obj["outputFolder"], str):
        obj["outputFolder"] = Path(obj["outputFolder"])

    if issubclass(targetCls, Task):
        rawSteps = obj.pop("steps", [])
        obj["steps"] = [fromDict(raw, TaskStep) for raw in rawSteps]

        rawFiles = obj.pop("files", None)
        if rawFiles is not None:
            fileCls = getattr(targetCls, "fileType", TaskFile)
            obj["files"] = [fileCls(**filterFields(fileCls, f)) for f in rawFiles]

    return targetCls(**filterFields(targetCls, obj))


def filterFields(cls: type, obj: dict[str, Any]) -> dict[str, Any]:
    allowed = {f.name for f in dataclass_fields(cls) if f.init}
    for klass in cls.__mro__:
        for name, val in vars(klass).items():
            if isinstance(val, property):
                allowed.discard(name)
    return {key: value for key, value in obj.items() if key in allowed}
