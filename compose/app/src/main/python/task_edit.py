from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

from app.models.task import TaskOptions, TaskStatus


@dataclass
class PreparedEdit:
    source: object
    sourceUrl: str
    sourceOptions: dict
    options: dict
    task: object


class TaskEdits:
    """Platform edit workflow; shared Task/Step execution remains unchanged."""

    def __init__(self, taskById, parse, edit, adapters, loop):
        self.taskById = taskById
        self.parse = parse
        self.edit = edit
        self.adapters = adapters
        self.loop = loop
        self.prepared: dict[str, PreparedEdit] = {}

    def build(self, taskId: str) -> dict:
        task = self.taskById(taskId)
        if task is None or not task.canEdit or task.status == TaskStatus.COMPLETED:
            raise ValueError("This task cannot be edited")
        adapter = self.adapters.get(task.packId)
        fields = getattr(adapter, "editFields", None)
        return {"outputFolder": str(task.outputFolder), **(fields(task) if fields else {})}

    def cancel(self, taskId: str) -> None:
        self.prepared.pop(taskId, None)

    def update(self, taskId: str, values: dict, shouldDiscard: bool = False) -> dict:
        current = self.build(taskId)
        if set(values) - set(current):
            raise ValueError("Unsupported task option")
        for key, value in values.items():
            if type(value) is not type(current[key]):
                raise ValueError(f"Invalid option: {key}")
        if not values.get("outputFolder", "").strip() or not Path(values["outputFolder"]).is_absolute():
            raise ValueError("Output folder must be an absolute path")
        if "subworkerCount" in values and not 1 <= values["subworkerCount"] <= 256:
            raise ValueError("Connection count must be between 1 and 256")
        if "headers" in values and any(not isinstance(k, str) or not isinstance(v, str)
                                      or not k.strip() or "\n" in k + v or "\r" in k + v
                                      for k, v in values["headers"].items()):
            raise ValueError("Invalid headers")
        for key in ("decryptionKeys", "muxImports"):
            if key in values and any(not isinstance(item, str) for item in values[key]):
                raise ValueError(f"Invalid option: {key}")
        task = self.taskById(taskId)
        options = {key: value for key, value in values.items() if value != current[key]}
        if not options:
            self.cancel(taskId)
            return {"needsConfirmation": False}
        newUrl = options.get("url", task.url).strip()
        newTask = None
        if newUrl != task.url:
            if not newUrl:
                raise ValueError("URL must not be empty")
            prepared = self.prepared.get(taskId)
            if prepared is not None and (prepared.source is not task or prepared.sourceUrl != task.url
                                         or prepared.sourceOptions != current):
                self.cancel(taskId)
                raise ValueError("Task changed; reopen the editor")
            if prepared is None or prepared.sourceUrl != task.url or prepared.options != values:
                sourceUrl = task.url
                future = asyncio.run_coroutine_threadsafe(
                    self.parse(TaskOptions.fromOptions({**current, **values, "url": newUrl})), self.loop)
                try:
                    newTask = future.result(timeout=60)
                except Exception:
                    future.cancel()
                    raise
                if self.taskById(taskId) is not task or task.url != sourceUrl or type(newTask) is not type(task):
                    raise ValueError("Task type or source changed; reopen the editor or create a new task")
                if self.build(taskId) != current:
                    raise ValueError("Task options changed; reopen the editor")
                prepared = PreparedEdit(task, task.url, deepcopy(current), deepcopy(values), newTask)
                self.prepared[taskId] = prepared
                shouldDiscard = False
            newTask = prepared.task
            self.build(taskId)
            if not task.canReuseProgress(newTask) and task.currentSnapshot()[2] > 0 and not shouldDiscard:
                return {"needsConfirmation": True}
            # Replacing steps also replaces their options, including values the user kept.
            options = {**current, **values}
        options.pop("url", None)
        self.edit(task, options, newTask)
        self.cancel(taskId)
        return {"needsConfirmation": False}
