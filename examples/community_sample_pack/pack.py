# pyright: reportImplicitOverride=false, reportInconsistentConstructor=false, reportUninitializedInstanceVariable=false

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import final
from urllib.parse import urlparse
from uuid import uuid4

from app.feature_pack.api import FeaturePack
from app.feature_pack.api import FormField
from app.feature_pack.api import SettingItem
from app.feature_pack.api import SettingSection
from app.feature_pack.api import SingleFileTask
from app.feature_pack.api import StageSnapshot
from app.feature_pack.api import Task
from app.feature_pack.api import TaskConfig
from app.feature_pack.api import TaskForm
from app.feature_pack.api import TaskInput
from app.feature_pack.api import TaskSnapshot
from app.feature_pack.api import TaskStage


packId = "community_sample_pack"
taskKind = "sample_echo"
stageKind = "sample_write"
taskVersion = 1
stageVersion = 1


def copyHeaders(headers: dict[str, str] | None) -> dict[str, str]:
    if headers is None:
        return {}
    return {str(key): str(value) for key, value in headers.items()}


def copyProxies(proxies: dict[str, str] | None) -> dict[str, str] | None:
    if proxies is None:
        return None
    return {str(key): str(value) for key, value in proxies.items()}


def messageFromSource(source: str) -> str:
    parsedSource = urlparse(source)
    message = f"{parsedSource.netloc}{parsedSource.path}".strip("/")
    if message:
        return message
    return source.removeprefix("sample:").strip("/") or "hello from sample pack"


def normalizeConfig(config: TaskConfig) -> TaskConfig:
    normalizedName = config.name.strip() or "sample.txt"
    return TaskConfig(
        source=config.source.strip(),
        folder=Path(config.folder),
        name=normalizedName,
        headers=copyHeaders(config.headers),
        proxies=copyProxies(config.proxies),
        chunks=max(1, int(config.chunks)),
    )


@final
class SampleWriteStage(TaskStage):
    def __init__(
        self,
        *,
        message: str,
        outputPath: Path,
        id: str | None = None,
    ) -> None:
        super().__init__(
            id=id or f"sample-stage-{uuid4().hex}",
            kind=stageKind,
            version=stageVersion,
            name="Sample write",
        )
        self.message = message
        self.outputPath = outputPath
        self.state = "waiting"
        self.progress = 0.0
        self.doneBytes = 0
        self.speed = 0
        self.error = ""

    def configure(self, config: TaskConfig) -> None:
        normalizedConfig = normalizeConfig(config)
        self.message = messageFromSource(normalizedConfig.source)
        self.outputPath = normalizedConfig.folder / normalizedConfig.name

    async def run(self) -> None:
        self.setState("running")
        await asyncio.sleep(0)

        try:
            self.outputPath.parent.mkdir(parents=True, exist_ok=True)
            text = f"{self.message}\n"
            _ = self.outputPath.write_text(text, encoding="utf-8")
        except OSError as error:
            self.error = str(error)
            self.setState("failed")
            self.failed.emit(self.error)
            raise

        self.doneBytes = len(text.encode("utf-8"))
        self.progress = 100.0
        self.setState("completed")

    def reset(self) -> None:
        self.state = "waiting"
        self.progress = 0.0
        self.doneBytes = 0
        self.speed = 0
        self.error = ""
        self.snapshotChanged.emit(self.snapshot())

    def setState(self, state: str) -> None:
        self.state = state
        self.stateChanged.emit(state)
        self.snapshotChanged.emit(self.snapshot())

    def snapshot(self) -> StageSnapshot:
        return StageSnapshot(
            id=self.id,
            kind=self.kind,
            name=self.name,
            state=self.state,
            progress=self.progress,
            doneBytes=self.doneBytes,
            speed=self.speed,
            error=self.error,
        )


@final
class SampleTask(SingleFileTask):
    def __init__(
        self,
        *,
        config: TaskConfig,
        id: str | None = None,
    ) -> None:
        normalizedConfig = normalizeConfig(config)
        stage = SampleWriteStage(
            message=messageFromSource(normalizedConfig.source),
            outputPath=normalizedConfig.folder / normalizedConfig.name,
        )
        self.state = "waiting"
        self.progress = 0.0
        self.doneBytes = 0
        self.totalBytes = 0
        super().__init__(
            id=id or f"sample-task-{uuid4().hex}",
            packId=packId,
            kind=taskKind,
            version=taskVersion,
            config=normalizedConfig,
            stages=[stage],
        )
        self.syncOutput()

    def configure(self, config: TaskConfig) -> None:
        super().configure(normalizeConfig(config))

    def syncOutput(self) -> None:
        for stage in self.stages:
            if isinstance(stage, SampleWriteStage):
                stage.outputPath = self.path

    def editForm(self, _mode: str) -> TaskForm | None:
        return TaskForm(
            title="Edit sample task",
            fields=(
                FormField(
                    key="source",
                    label="Sample source",
                    kind="text",
                    placeholder="sample://hello-world",
                ),
                FormField(
                    key="name",
                    label="Output name",
                    kind="text",
                    placeholder="sample.txt",
                ),
                FormField(
                    key="folder",
                    label="Output folder",
                    kind="folder",
                ),
            ),
        )

    async def run(self) -> None:
        self.state = "running"
        self.progress = 0.0
        self.snapshotChanged.emit(self.snapshot())

        await super().run()
        self.syncStateFromStages()
        self.snapshotChanged.emit(self.snapshot())

    def reset(self) -> None:
        self.state = "waiting"
        self.progress = 0.0
        self.doneBytes = 0
        self.currentStageIndex = 0
        for stage in self.stages:
            stage.reset()
        self.snapshotChanged.emit(self.snapshot())

    def syncStateFromStages(self) -> None:
        stageSnapshots = tuple(stage.snapshot() for stage in self.stages)
        if not stageSnapshots:
            return

        if any(stage.state == "failed" for stage in stageSnapshots):
            self.state = "failed"
        elif all(stage.state == "completed" for stage in stageSnapshots):
            self.state = "completed"
        elif any(stage.state == "running" for stage in stageSnapshots):
            self.state = "running"
        else:
            self.state = "waiting"

        self.doneBytes = sum(stage.doneBytes for stage in stageSnapshots)
        self.totalBytes = self.doneBytes
        self.progress = sum(stage.progress for stage in stageSnapshots) / len(stageSnapshots)

    def snapshot(self) -> TaskSnapshot:
        self.syncStateFromStages()
        return TaskSnapshot(
            id=self.id,
            packId=self.packId,
            kind=self.kind,
            name=self.config.name,
            state=self.state,
            progress=self.progress,
            doneBytes=self.doneBytes,
            totalBytes=self.totalBytes,
            canPause=self.canPause(),
            target=str(self.path),
            stages=tuple(stage.snapshot() for stage in self.stages),
        )


@final
class CommunitySamplePack(FeaturePack):
    def accepts(self, source: str) -> bool:
        return urlparse(source).scheme.lower() == "sample"

    async def createTask(self, data: TaskInput) -> Task | None:
        normalizedConfig = normalizeConfig(data.config)
        if not self.accepts(normalizedConfig.source):
            return None
        return SampleTask(config=normalizedConfig)

    def owns(self, task: Task) -> bool:
        return isinstance(task, SampleTask) and task.packId == self.manifest.id

    def settingSection(self) -> SettingSection:
        return SettingSection(
            id=self.manifest.id,
            title="Community Sample Pack",
            items=(
                SettingItem(
                    key="status",
                    label="Sample status",
                    kind="text",
                    extra={"value": "Ready"},
                ),
            ),
        )


__all__ = ["CommunitySamplePack", "SampleTask", "SampleWriteStage"]
