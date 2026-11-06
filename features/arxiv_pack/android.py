from __future__ import annotations

from typing import TYPE_CHECKING, Any

from http_pack.android import editFields as editHttpFields

if TYPE_CHECKING:
    from .task import ArxivTask

UI_CLASS = "com.xychr.ghostdownloader.features.arxiv_pack.ArxivUi"


def editFields(task: ArxivTask) -> dict[str, Any]:
    fields = {**editHttpFields(task), "isBibtexEnabled": task.isBibtexEnabled}
    del fields["url"]
    if task.hasSource:
        fields["isSourceEnabled"] = task.isSourceEnabled
    return fields


def draftFields(task: ArxivTask) -> dict[str, Any]:
    return {
        "hasSource": task.hasSource,
        "isSourceEnabled": task.isSourceEnabled,
        "isBibtexEnabled": task.isBibtexEnabled,
    }


def setSideFile(task: ArxivTask, key: str, isEnabled: bool) -> None:
    task.setOptions({key: bool(isEnabled)})
