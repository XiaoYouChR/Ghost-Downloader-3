# pyright: reportImplicitOverride=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportPrivateUsage=false, reportAny=false, reportInconsistentConstructor=false, reportUnannotatedClassAttribute=false

from __future__ import annotations

from collections.abc import Mapping
import sys
import tempfile
import unittest
from pathlib import Path
from typing import cast
from unittest.mock import patch

from orjson import loads


ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    _ = sys.path.insert(0, str(ROOT))

from app.feature_pack.api import MultiFileTask
from app.feature_pack.api import SingleFileTask
from app.feature_pack.api import StageSnapshot
from app.feature_pack.api import TaskConfig
from app.feature_pack.api import TaskFile
from app.feature_pack.api import TaskSnapshot
from app.feature_pack.api import TaskStage
from app.feature_pack.internal.recorder import TaskRecordError
from app.feature_pack.internal.recorder import TaskRecorder


class DemoPersistentStage(TaskStage):
    recordTaskPackId = "demo_pack"
    recordTaskKind = "demo_single"
    recordTaskVersion = 1
    recordKind = "download"
    recordVersion = 1

    def __init__(
        self,
        *,
        id: str,
        kind: str = "download",
        version: int = 1,
        name: str = "下载阶段",
    ) -> None:
        super().__init__(id=id, kind=kind, version=version, name=name)
        self.state = "waiting"
        self.progress = 0.0
        self.doneBytes = 0
        self.speed = 0
        self.error = ""
        self.configuredChunks = 0
        self.outputTarget = ""
        self.resetCalls = 0

    async def run(self) -> None:
        return None

    def reset(self) -> None:
        self.resetCalls += 1
        self.state = "waiting"
        self.progress = 0.0
        self.doneBytes = 0
        self.speed = 0
        self.error = ""

    def configure(self, config: TaskConfig) -> None:
        self.configuredChunks = config.chunks

    def persistenceState(self) -> dict[str, object]:
        return {
            "state": self.state,
            "progress": self.progress,
            "doneBytes": self.doneBytes,
            "speed": self.speed,
            "error": self.error,
            "configuredChunks": self.configuredChunks,
            "outputTarget": self.outputTarget,
        }

    def restorePersistentState(self, state: Mapping[str, object]) -> None:
        rawState = state.get("state")
        rawProgress = state.get("progress")
        rawDoneBytes = state.get("doneBytes")
        rawSpeed = state.get("speed")
        rawError = state.get("error")
        rawChunks = state.get("configuredChunks")
        rawTarget = state.get("outputTarget")

        if isinstance(rawState, str):
            self.state = rawState
        if isinstance(rawProgress, int | float):
            self.progress = float(rawProgress)
        if isinstance(rawDoneBytes, int) and not isinstance(rawDoneBytes, bool):
            self.doneBytes = rawDoneBytes
        if isinstance(rawSpeed, int) and not isinstance(rawSpeed, bool):
            self.speed = rawSpeed
        if isinstance(rawError, str):
            self.error = rawError
        if isinstance(rawChunks, int) and not isinstance(rawChunks, bool):
            self.configuredChunks = rawChunks
        if isinstance(rawTarget, str):
            self.outputTarget = rawTarget

    @classmethod
    def createPersistentStage(
        cls,
        *,
        id: str,
        kind: str,
        version: int,
        name: str,
        state: Mapping[str, object],
    ) -> "DemoPersistentStage":
        _ = state
        return cls(id=id, kind=kind, version=version, name=name)

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


class DemoPersistentSingleFileTask(SingleFileTask):
    recordPackId = "demo_pack"
    recordKind = "demo_single"
    recordVersion = 1

    def __init__(
        self,
        *,
        id: str = "demo-single-task",
        config: TaskConfig | None = None,
        stages: list[TaskStage] | None = None,
    ) -> None:
        self.state = "waiting"
        self.progress = 0.0
        self.doneBytes = 0
        self.totalBytes = 0
        self.target = ""
        super().__init__(
            id=id,
            packId="demo_pack",
            kind="demo_single",
            version=1,
            config=config
            if config is not None
            else TaskConfig(
                source="https://example.com/demo.bin",
                folder=Path("downloads"),
                name="demo.bin",
                chunks=4,
            ),
            stages=stages or [],
        )
        self.syncOutput()

    def syncOutput(self) -> None:
        self.target = str(self.path)
        for stage in self.stages:
            if isinstance(stage, DemoPersistentStage):
                stage.outputTarget = self.target

    def reset(self) -> None:
        self.state = "waiting"
        self.progress = 0.0
        self.doneBytes = 0
        self.currentStageIndex = 0
        for stage in self.stages:
            stage.reset()

    def persistenceState(self) -> dict[str, object]:
        state = super().persistenceState()
        state.update(
            {
                "state": self.state,
                "progress": self.progress,
                "doneBytes": self.doneBytes,
                "totalBytes": self.totalBytes,
                "target": self.target,
            }
        )
        return state

    def restorePersistentState(self, state: Mapping[str, object]) -> None:
        super().restorePersistentState(state)
        rawState = state.get("state")
        rawProgress = state.get("progress")
        rawDoneBytes = state.get("doneBytes")
        rawTotalBytes = state.get("totalBytes")
        rawTarget = state.get("target")

        if isinstance(rawState, str):
            self.state = rawState
        if isinstance(rawProgress, int | float):
            self.progress = float(rawProgress)
        if isinstance(rawDoneBytes, int) and not isinstance(rawDoneBytes, bool):
            self.doneBytes = rawDoneBytes
        if isinstance(rawTotalBytes, int) and not isinstance(rawTotalBytes, bool):
            self.totalBytes = rawTotalBytes
        if isinstance(rawTarget, str) and rawTarget:
            self.target = rawTarget

    @classmethod
    def createPersistentTask(
        cls,
        *,
        id: str,
        packId: str,
        kind: str,
        version: int,
        config: TaskConfig,
        stages: list[TaskStage],
        state: Mapping[str, object],
    ) -> "DemoPersistentSingleFileTask":
        _ = packId
        _ = kind
        _ = version
        _ = state
        return cls(id=id, config=config, stages=stages)

    def snapshot(self) -> TaskSnapshot:
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
            target=self.target,
            stages=tuple(stage.snapshot() for stage in self.stages),
        )


class DemoPersistentMultiStage(TaskStage):
    recordTaskPackId = "demo_pack"
    recordTaskKind = "demo_multi"
    recordTaskVersion = 1
    recordKind = "index"
    recordVersion = 1

    def __init__(self, *, id: str, name: str = "索引阶段") -> None:
        super().__init__(id=id, kind="index", version=1, name=name)
        self.state = "waiting"
        self.progress = 0.0
        self.doneBytes = 0
        self.speed = 0
        self.error = ""

    async def run(self) -> None:
        return None

    def reset(self) -> None:
        self.state = "waiting"

    def persistenceState(self) -> dict[str, object]:
        return {"state": self.state}

    def restorePersistentState(self, state: Mapping[str, object]) -> None:
        rawState = state.get("state")
        if isinstance(rawState, str):
            self.state = rawState

    @classmethod
    def createPersistentStage(
        cls,
        *,
        id: str,
        kind: str,
        version: int,
        name: str,
        state: Mapping[str, object],
    ) -> "DemoPersistentMultiStage":
        _ = kind
        _ = version
        _ = state
        return cls(id=id, name=name)

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


class DemoPersistentMultiFileTask(MultiFileTask):
    recordPackId = "demo_pack"
    recordKind = "demo_multi"
    recordVersion = 1

    def __init__(
        self,
        *,
        id: str = "demo-multi-task",
        config: TaskConfig | None = None,
        stages: list[TaskStage] | None = None,
        files: list[TaskFile] | None = None,
    ) -> None:
        self.state = "waiting"
        self.progress = 0.0
        self.doneBytes = 0
        self.totalBytes = 0
        self.target = ""
        super().__init__(
            id=id,
            packId="demo_pack",
            kind="demo_multi",
            version=1,
            config=config
            if config is not None
            else TaskConfig(
                source="ftp://example.com/library",
                folder=Path("downloads"),
                name="library",
                chunks=2,
            ),
            stages=stages or [],
            files=files or [],
        )
        self.totalBytes = sum(file.size for file in self.files)
        self.syncOutput()

    def syncOutput(self) -> None:
        self.target = str(self.root)

    def reset(self) -> None:
        self.state = "waiting"

    def persistenceState(self) -> dict[str, object]:
        state = super().persistenceState()
        state.update(
            {
                "state": self.state,
                "progress": self.progress,
                "doneBytes": self.doneBytes,
                "totalBytes": self.totalBytes,
                "target": self.target,
            }
        )
        return state

    def restorePersistentState(self, state: Mapping[str, object]) -> None:
        super().restorePersistentState(state)
        rawState = state.get("state")
        rawProgress = state.get("progress")
        rawDoneBytes = state.get("doneBytes")
        rawTotalBytes = state.get("totalBytes")
        rawTarget = state.get("target")

        if isinstance(rawState, str):
            self.state = rawState
        if isinstance(rawProgress, int | float):
            self.progress = float(rawProgress)
        if isinstance(rawDoneBytes, int) and not isinstance(rawDoneBytes, bool):
            self.doneBytes = rawDoneBytes
        if isinstance(rawTotalBytes, int) and not isinstance(rawTotalBytes, bool):
            self.totalBytes = rawTotalBytes
        else:
            self.totalBytes = sum(file.size for file in self.files)
        if isinstance(rawTarget, str) and rawTarget:
            self.target = rawTarget

    @classmethod
    def createPersistentTask(
        cls,
        *,
        id: str,
        packId: str,
        kind: str,
        version: int,
        config: TaskConfig,
        stages: list[TaskStage],
        state: Mapping[str, object],
    ) -> "DemoPersistentMultiFileTask":
        _ = packId
        _ = kind
        _ = version
        rawFiles = state.get("files")
        files: list[TaskFile] = []
        if isinstance(rawFiles, list):
            for rawFile in rawFiles:
                if not isinstance(rawFile, Mapping):
                    continue
                fileId = rawFile.get("id")
                filePath = rawFile.get("path")
                fileSize = rawFile.get("size")
                rawDoneBytes = rawFile.get("doneBytes", 0)
                if (
                    not isinstance(fileId, str)
                    or not isinstance(filePath, str)
                    or isinstance(fileSize, bool)
                    or not isinstance(fileSize, int)
                    or isinstance(rawDoneBytes, bool)
                    or not isinstance(rawDoneBytes, int)
                ):
                    continue
                note = rawFile.get("note")
                files.append(
                    TaskFile(
                        id=fileId,
                        path=filePath,
                        size=fileSize,
                        selected=bool(rawFile.get("selected", True)),
                        note=note if isinstance(note, str) else "",
                        doneBytes=rawDoneBytes,
                        finished=bool(rawFile.get("finished", False)),
                    )
                )

        return cls(id=id, config=config, stages=stages, files=files)

    def snapshot(self) -> TaskSnapshot:
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
            target=self.target,
            stages=tuple(stage.snapshot() for stage in self.stages),
        )


class FeaturePackTaskRecorderV1Tests(unittest.TestCase):
    _temporaryDirectory: tempfile.TemporaryDirectory[str] | None = None
    tempPath: Path = ROOT

    def setUp(self) -> None:
        temporaryDirectory = tempfile.TemporaryDirectory()
        self._temporaryDirectory = temporaryDirectory
        self.addCleanup(temporaryDirectory.cleanup)
        self.tempPath = Path(temporaryDirectory.name)

    def createRecorder(self) -> TaskRecorder:
        with patch(
            "app.feature_pack.internal.recorder.QStandardPaths.writableLocation",
            return_value=str(self.tempPath),
        ):
            return TaskRecorder()

    def createSingleFileTask(self) -> DemoPersistentSingleFileTask:
        task = DemoPersistentSingleFileTask(
            config=TaskConfig(
                source="https://example.com/archive.zip",
                folder=self.tempPath / "downloads",
                name="archive.zip",
                headers={"User-Agent": "Ghost Downloader"},
                proxies={"https": "http://127.0.0.1:7890"},
                chunks=8,
            ),
            stages=[DemoPersistentStage(id="stage-1")],
        )
        task.state = "running"
        task.progress = 37.5
        task.doneBytes = 384
        task.totalBytes = 1024
        task.currentStageIndex = 0
        stage = cast(DemoPersistentStage, task.stages[0])
        stage.state = "running"
        stage.progress = 37.5
        stage.doneBytes = 384
        stage.speed = 64
        stage.error = ""
        stage.configure(task.config)
        task.syncOutput()
        return task

    def createMultiFileTask(self) -> DemoPersistentMultiFileTask:
        task = DemoPersistentMultiFileTask(
            config=TaskConfig(
                source="ftp://example.com/series",
                folder=self.tempPath / "downloads",
                name="series",
                chunks=3,
            ),
            stages=[DemoPersistentMultiStage(id="stage-1")],
            files=[
                TaskFile(
                    id="file-1",
                    path="episode-1.mp4",
                    size=100,
                    selected=True,
                    note="1080p",
                    doneBytes=40,
                    finished=False,
                ),
                TaskFile(
                    id="file-2",
                    path="episode-2.mp4",
                    size=200,
                    selected=False,
                    note="720p",
                    doneBytes=0,
                    finished=False,
                ),
            ],
        )
        task.state = "paused"
        task.progress = 20.0
        task.doneBytes = 40
        task.totalBytes = 300
        task.currentStageIndex = 0
        cast(DemoPersistentMultiStage, task.stages[0]).state = "paused"
        task.syncOutput()
        return task

    def testSerializeTaskUsesStableIdentityFieldsInsteadOfClassNames(self) -> None:
        recorder = self.createRecorder()
        task = self.createSingleFileTask()

        record = recorder.serializeTask(task)

        self.assertEqual(record["id"], task.id)
        self.assertEqual(record["packId"], "demo_pack")
        self.assertEqual(record["kind"], "demo_single")
        self.assertEqual(record["version"], 1)
        self.assertNotIn("type", record)

        config = cast(dict[str, object], record["config"])
        self.assertEqual(config["source"], "https://example.com/archive.zip")
        self.assertEqual(config["folder"], str(self.tempPath / "downloads"))
        self.assertEqual(config["name"], "archive.zip")
        self.assertEqual(config["chunks"], 8)

        stages = cast(list[dict[str, object]], record["stages"])
        self.assertEqual(
            stages,
            [
                {
                    "id": "stage-1",
                    "kind": "download",
                    "version": 1,
                    "name": "下载阶段",
                    "state": {
                        "state": "running",
                        "progress": 37.5,
                        "doneBytes": 384,
                        "speed": 64,
                        "error": "",
                        "configuredChunks": 8,
                        "outputTarget": str(self.tempPath / "downloads" / "archive.zip"),
                    },
                }
            ],
        )

    def testRecorderFlushAndReadRoundTripSingleFileTask(self) -> None:
        recorder = self.createRecorder()
        task = self.createSingleFileTask()

        recorder.memorizedTasks[task.id] = task
        recorder.flush()
        self.assertEqual(recorder.recordFile.read_text(encoding="utf-8"), "")

        recorder.load()
        recorder.add(task, flush=True)

        lines = recorder.recordFile.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        record = cast(dict[str, object], loads(lines[0]))
        self.assertEqual(record["packId"], "demo_pack")
        self.assertEqual(record["kind"], "demo_single")
        self.assertEqual(record["version"], 1)

        restored = recorder.read()
        restoredTask = cast(DemoPersistentSingleFileTask, restored[task.id])
        self.assertIsInstance(restoredTask, DemoPersistentSingleFileTask)
        self.assertEqual(restoredTask.config.folder, self.tempPath / "downloads")
        self.assertEqual(restoredTask.config.name, "archive.zip")
        self.assertEqual(restoredTask.config.headers, {"User-Agent": "Ghost Downloader"})
        self.assertEqual(restoredTask.config.proxies, {"https": "http://127.0.0.1:7890"})
        self.assertEqual(restoredTask.config.chunks, 8)
        self.assertEqual(restoredTask.state, "running")
        self.assertEqual(restoredTask.progress, 37.5)
        self.assertEqual(restoredTask.doneBytes, 384)
        self.assertEqual(restoredTask.totalBytes, 1024)
        self.assertEqual(restoredTask.currentStageIndex, 0)
        self.assertEqual(restoredTask.target, str(self.tempPath / "downloads" / "archive.zip"))

        restoredStage = cast(DemoPersistentStage, restoredTask.stages[0])
        self.assertIsInstance(restoredStage, DemoPersistentStage)
        self.assertIs(restoredStage._task, restoredTask)
        self.assertEqual(restoredStage.state, "running")
        self.assertEqual(restoredStage.progress, 37.5)
        self.assertEqual(restoredStage.doneBytes, 384)
        self.assertEqual(restoredStage.speed, 64)
        self.assertEqual(restoredStage.configuredChunks, 8)
        self.assertEqual(restoredStage.outputTarget, str(self.tempPath / "downloads" / "archive.zip"))

    def testRecorderRestoresMultiFileSelectionAndFileState(self) -> None:
        recorder = self.createRecorder()
        task = self.createMultiFileTask()
        recorder.load()
        recorder.add(task, flush=True)

        restored = recorder.read()
        restoredTask = cast(DemoPersistentMultiFileTask, restored[task.id])

        self.assertIsInstance(restoredTask, DemoPersistentMultiFileTask)
        self.assertEqual(restoredTask.root, self.tempPath / "downloads" / "series")
        self.assertEqual(restoredTask.selectedIds, {"file-1"})
        self.assertEqual(restoredTask.selectedCount, 1)
        self.assertEqual(restoredTask.fileCount, 2)
        self.assertEqual(restoredTask.totalBytes, 300)
        self.assertEqual(
            [(file.id, file.path, file.selected, file.note, file.doneBytes) for file in restoredTask.files],
            [
                ("file-1", "episode-1.mp4", True, "1080p", 40),
                ("file-2", "episode-2.mp4", False, "720p", 0),
            ],
        )

    def testRecorderRejectsUnknownTaskIdentityDuringRestore(self) -> None:
        recorder = self.createRecorder()
        invalidRecord = {
            "schemaVersion": 1,
            "id": "missing-task",
            "packId": "missing_pack",
            "kind": "missing_kind",
            "version": 1,
            "config": {
                "source": "https://example.com/file.bin",
                "folder": str(self.tempPath),
                "name": "file.bin",
                "headers": {},
                "proxies": None,
                "chunks": 1,
            },
            "state": {},
            "stages": [],
        }

        with self.assertRaises(TaskRecordError) as context:
            _ = recorder.deserializeTask(invalidRecord)

        self.assertEqual(context.exception.code, "unknown-task-identity")


if __name__ == "__main__":
    _ = unittest.main()
