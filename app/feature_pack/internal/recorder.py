# pyright: reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnnecessaryIsInstance=false, reportAny=false, reportUnannotatedClassAttribute=false

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict
from dataclasses import is_dataclass
from pathlib import Path

import orjson
from PySide6.QtCore import QStandardPaths
from loguru import logger

from app.feature_pack.api import Task
from app.feature_pack.api import TaskConfig
from app.feature_pack.api import TaskStage


def _toRecordValue(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value) and not isinstance(value, type):
        return _toRecordValue(asdict(value))
    if isinstance(value, Mapping):
        record: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TaskRecordError(
                    code="invalid-state-key",
                    reason="持久化状态中的字典键必须是字符串",
                )
            record[key] = _toRecordValue(item)
        return record
    if isinstance(value, (list, tuple)):
        return [_toRecordValue(item) for item in value]

    raise TaskRecordError(
        code="invalid-state-value",
        reason=f"不支持持久化的状态值类型: {type(value).__name__}",
    )


class TaskRecordError(ValueError):
    code: str
    reason: str

    def __init__(self, *, code: str, reason: str) -> None:
        self.code = code
        self.reason = reason
        super().__init__(f"[{code}] {reason}")


class TaskRecorder:
    recordSchemaVersion: int = 1
    recordFile: Path
    _loaded: bool

    def __init__(self, *, recordFile: str | Path | None = None) -> None:
        self.recordFile = Path(recordFile) if recordFile is not None else self._defaultRecordFile()
        if not self.recordFile.exists():
            self.recordFile.parent.mkdir(parents=True, exist_ok=True)
            self.recordFile.touch()

        self.memorizedTasks: dict[str, Task] = {}
        self._loaded = False

    def load(self) -> None:
        self.memorizedTasks = self.read()
        self._loaded = True

    def read(self) -> dict[str, Task]:
        tasks: dict[str, Task] = {}
        with open(self.recordFile, "r", encoding="utf-8") as file:
            for lineNumber, rawLine in enumerate(file, start=1):
                line = rawLine.strip()
                if not line:
                    continue

                try:
                    task = self.deserializeTask(orjson.loads(line))
                    tasks[task.id] = task
                except Exception as error:
                    logger.opt(exception=error).error(
                        "failed to parse feature-pack task record {}:{}",
                        self.recordFile,
                        lineNumber,
                    )

        return tasks

    def add(self, task: Task, flush: bool = True) -> None:
        if task.id in self.memorizedTasks:
            raise ValueError(f"task {task.id} already exists")

        self.memorizedTasks[task.id] = task
        if flush:
            self.flush()

    def remove(self, task: Task, flush: bool = True) -> None:
        if task.id not in self.memorizedTasks:
            return

        del self.memorizedTasks[task.id]
        if flush:
            self.flush()

    def flush(self) -> None:
        if not self._loaded:
            logger.warning("skip flush because feature-pack task recorder has not been loaded")
            return

        lines: list[str] = []
        for task in self.memorizedTasks.values():
            try:
                lines.append(orjson.dumps(self.serializeTask(task)).decode("utf-8") + "\n")
            except Exception as error:
                logger.opt(exception=error).error(
                    "failed to write feature-pack task {}",
                    task.id,
                )

        tempFile = self.recordFile.with_name(self.recordFile.name + ".tmp")
        with open(tempFile, "w", encoding="utf-8") as file:
            file.writelines(lines)

        _ = tempFile.replace(self.recordFile)

    def serializeTask(self, task: Task) -> dict[str, object]:
        state = task.persistenceState()
        if not isinstance(state, Mapping):
            raise TaskRecordError(
                code="invalid-task-state",
                reason="Task.persistenceState() 必须返回字典映射",
            )

        return {
            "schemaVersion": self.recordSchemaVersion,
            "id": task.id,
            "packId": task.packId,
            "kind": task.kind,
            "version": task.version,
            "config": self._serializeConfig(task.config),
            "state": _toRecordValue(dict(state)),
            "stages": [self.serializeStage(stage) for stage in task.stages],
        }

    def serializeStage(self, stage: TaskStage) -> dict[str, object]:
        state = stage.persistenceState()
        if not isinstance(state, Mapping):
            raise TaskRecordError(
                code="invalid-stage-state",
                reason="TaskStage.persistenceState() 必须返回字典映射",
            )

        return {
            "id": stage.id,
            "kind": stage.kind,
            "version": stage.version,
            "name": stage.name,
            "state": _toRecordValue(dict(state)),
        }

    def deserializeTask(self, data: object) -> Task:
        record = self._expectMapping(data, "task record")
        schemaVersion = self._readInt(record, "schemaVersion")
        if schemaVersion != self.recordSchemaVersion:
            raise TaskRecordError(
                code="unsupported-schema-version",
                reason=f"不支持的任务记录版本: {schemaVersion}",
            )

        taskId = self._readString(record, "id")
        packId = self._readString(record, "packId")
        taskKind = self._readString(record, "kind")
        taskVersion = self._readInt(record, "version")
        config = self._deserializeConfig(record.get("config"))
        taskState = self._readState(record.get("state"), "task")

        taskCls = Task.persistentClass(
            packId=packId,
            kind=taskKind,
            version=taskVersion,
        )
        if taskCls is None:
            raise TaskRecordError(
                code="unknown-task-identity",
                reason=f"未注册的任务身份: {packId}/{taskKind}@{taskVersion}",
            )

        rawStages = record.get("stages")
        if not isinstance(rawStages, list):
            raise TaskRecordError(
                code="invalid-task-stages",
                reason="任务记录中的 stages 必须是列表",
            )

        stageRecords: list[dict[str, object]] = []
        stages: list[TaskStage] = []
        for rawStage in rawStages:
            stageRecord = dict(self._expectMapping(rawStage, "stage record"))
            stageRecords.append(stageRecord)
            stages.append(
                self.deserializeStage(
                    taskPackId=packId,
                    taskKind=taskKind,
                    taskVersion=taskVersion,
                    data=stageRecord,
                )
            )

        task = taskCls.createPersistentTask(
            id=taskId,
            packId=packId,
            kind=taskKind,
            version=taskVersion,
            config=config,
            stages=stages,
            state=taskState,
        )
        if not isinstance(task, Task):
            raise TaskRecordError(
                code="invalid-task-instance",
                reason="createPersistentTask() 必须返回 Task 实例",
            )

        task.restorePersistentState(taskState)
        for stage, stageRecord in zip(task.stages, stageRecords, strict=True):
            stage.restorePersistentState(self._readState(stageRecord.get("state"), "stage"))

        return task

    def deserializeStage(
        self,
        *,
        taskPackId: str,
        taskKind: str,
        taskVersion: int,
        data: object,
    ) -> TaskStage:
        record = self._expectMapping(data, "stage record")
        stageId = self._readString(record, "id")
        stageKind = self._readString(record, "kind")
        stageVersion = self._readInt(record, "version")
        stageName = self._readString(record, "name")
        stageState = self._readState(record.get("state"), "stage")

        stageCls = TaskStage.persistentClass(
            taskPackId=taskPackId,
            taskKind=taskKind,
            taskVersion=taskVersion,
            kind=stageKind,
            version=stageVersion,
        )
        if stageCls is None:
            raise TaskRecordError(
                code="unknown-stage-identity",
                reason=(
                    "未注册的阶段身份: "
                    f"{taskPackId}/{taskKind}@{taskVersion} -> {stageKind}@{stageVersion}"
                ),
            )

        stage = stageCls.createPersistentStage(
            id=stageId,
            kind=stageKind,
            version=stageVersion,
            name=stageName,
            state=stageState,
        )
        if not isinstance(stage, TaskStage):
            raise TaskRecordError(
                code="invalid-stage-instance",
                reason="createPersistentStage() 必须返回 TaskStage 实例",
            )

        return stage

    def _serializeConfig(self, config: TaskConfig) -> dict[str, object]:
        return {
            "source": config.source,
            "folder": str(config.folder),
            "name": config.name,
            "headers": dict(config.headers),
            "proxies": None if config.proxies is None else dict(config.proxies),
            "chunks": config.chunks,
        }

    def _deserializeConfig(self, data: object) -> TaskConfig:
        record = self._expectMapping(data, "task config")
        return TaskConfig(
            source=self._readString(record, "source"),
            folder=Path(self._readString(record, "folder")),
            name=self._readString(record, "name"),
            headers=self._readStringMapping(record.get("headers"), "headers"),
            proxies=self._readOptionalStringMapping(record.get("proxies"), "proxies"),
            chunks=self._readInt(record, "chunks"),
        )

    def _defaultRecordFile(self) -> Path:
        appLocalDataLocation = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.GenericDataLocation
        )
        return Path(appLocalDataLocation) / "GhostDownloader" / "FeaturePackMemory.log"

    def _expectMapping(
        self,
        data: object,
        label: str,
    ) -> Mapping[str, object]:
        if not isinstance(data, Mapping):
            raise TaskRecordError(
                code="invalid-record-shape",
                reason=f"{label} 必须是对象",
            )

        normalized: dict[str, object] = {}
        for key, value in data.items():
            if not isinstance(key, str):
                raise TaskRecordError(
                    code="invalid-record-key",
                    reason=f"{label} 包含非字符串键",
                )
            normalized[key] = value
        return normalized

    def _readString(self, record: Mapping[str, object], key: str) -> str:
        value = record.get(key)
        if not isinstance(value, str) or not value:
            raise TaskRecordError(
                code="invalid-string-field",
                reason=f"字段 {key} 必须是非空字符串",
            )
        return value

    def _readInt(self, record: Mapping[str, object], key: str) -> int:
        value = record.get(key)
        if isinstance(value, bool) or not isinstance(value, int):
            raise TaskRecordError(
                code="invalid-int-field",
                reason=f"字段 {key} 必须是整数",
            )
        return value

    def _readState(self, data: object, owner: str) -> Mapping[str, object]:
        if data is None:
            return {}
        if not isinstance(data, Mapping):
            raise TaskRecordError(
                code="invalid-state-shape",
                reason=f"{owner} state 必须是对象",
            )
        return self._expectMapping(data, f"{owner} state")

    def _readStringMapping(
        self,
        data: object,
        key: str,
    ) -> dict[str, str]:
        if data is None:
            return {}
        if not isinstance(data, Mapping):
            raise TaskRecordError(
                code="invalid-mapping-field",
                reason=f"字段 {key} 必须是字典",
            )

        result: dict[str, str] = {}
        for itemKey, itemValue in data.items():
            if not isinstance(itemKey, str) or not isinstance(itemValue, str):
                raise TaskRecordError(
                    code="invalid-mapping-item",
                    reason=f"字段 {key} 的键和值必须都是字符串",
                )
            result[itemKey] = itemValue
        return result

    def _readOptionalStringMapping(
        self,
        data: object,
        key: str,
    ) -> dict[str, str] | None:
        if data is None:
            return None
        return self._readStringMapping(data, key)


taskRecorder = TaskRecorder()


__all__ = ["TaskRecordError", "TaskRecorder", "taskRecorder"]
