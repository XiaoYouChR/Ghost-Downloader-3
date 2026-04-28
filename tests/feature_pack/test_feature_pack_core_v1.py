# pyright: reportImplicitOverride=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false, reportAny=false, reportInconsistentConstructor=false, reportUnannotatedClassAttribute=false, reportUnusedCallResult=false, reportPrivateUsage=false

from __future__ import annotations

import asyncio
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from typing import cast
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    _ = sys.path.insert(0, str(ROOT))

from app.feature_pack.api import DefaultFeatureService
from app.feature_pack.api import EditMode
from app.feature_pack.api import FeaturePack
from app.feature_pack.api import FeatureService
from app.feature_pack.api import Manifest
from app.feature_pack.api import StageSnapshot
from app.feature_pack.api import Task
from app.feature_pack.api import TaskConfig
from app.feature_pack.api import TaskInput
from app.feature_pack.api import TaskSnapshot
from app.feature_pack.api import TaskStage
from app.feature_pack.internal import FeaturePackCoreService
from app.feature_pack.internal.recorder import TaskRecorder
from app.services.core_service import CoreService


class _FakeWindow:
    def __init__(self) -> None:
        self.installed: list[str] = []


class _DemoCoreStage(TaskStage):
    def __init__(self, *, id: str) -> None:
        super().__init__(id=id, kind="download", version=1, name=f"阶段 {id}")

    async def run(self) -> None:
        return None

    def reset(self) -> None:
        return None

    def snapshot(self) -> StageSnapshot:
        return StageSnapshot(
            id=self.id,
            kind=self.kind,
            name=self.name,
            state="waiting",
            progress=0.0,
            doneBytes=0,
            speed=0,
        )


class _DemoCoreTask(Task):
    def __init__(
        self,
        *,
        id: str,
        source: str,
        occupiesSlot: bool = True,
        willOccupySlot: bool | None = None,
    ) -> None:
        self.state = "waiting"
        self.progress = 0.0
        self.doneBytes = 0
        self.totalBytes = 1024
        self.target = ""
        self.runCalls = 0
        self.pauseCalls = 0
        self.resetCalls = 0
        self.occupiesSlot = occupiesSlot
        self.willOccupySlot = occupiesSlot if willOccupySlot is None else willOccupySlot
        self.enteredRun = asyncio.Event()
        self.releaseRun = asyncio.Event()
        super().__init__(
            id=id,
            packId="demo_pack",
            kind="demo",
            version=1,
            config=TaskConfig(
                source=source,
                folder=Path("downloads"),
                name=f"{id}.bin",
            ),
            stages=[_DemoCoreStage(id=f"{id}-stage")],
        )
        self.syncOutput()

    def syncOutput(self) -> None:
        self.target = str(self.config.folder / self.config.name)

    async def run(self) -> None:
        self.runCalls += 1
        self.enteredRun.set()
        await self.releaseRun.wait()

    async def pause(self) -> None:
        self.pauseCalls += 1
        self.state = "paused"

    def reset(self) -> None:
        self.resetCalls += 1
        self.state = "waiting"
        self.progress = 0.0
        self.doneBytes = 0
        self.enteredRun = asyncio.Event()
        self.releaseRun = asyncio.Event()

    def occupiesDownloadSlot(self) -> bool:
        return self.occupiesSlot

    def willOccupyDownloadSlotWhenStarted(self) -> bool:
        return self.willOccupySlot

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


class _RecordingFeatureService(FeatureService):
    def __init__(self, *, createdTasks: list[Task]) -> None:
        self.createdTasks = createdTasks
        self.createTaskInputs: list[TaskInput] = []

    def discoverPacks(self) -> list[Manifest]:
        return []

    def loadPacks(self, window: object) -> None:
        _ = window
        return None

    def pack(self, packId: str) -> FeaturePack | None:
        _ = packId
        return None

    def packForSource(self, source: str) -> FeaturePack | None:
        _ = source
        return None

    def packForTask(self, task: Task) -> FeaturePack | None:
        _ = task
        return None

    async def createTask(self, data: TaskInput) -> Task:
        self.createTaskInputs.append(data)
        return self.createdTasks.pop(0)

    def configureTask(self, taskId: str, config: TaskConfig) -> None:
        _ = taskId
        _ = config
        return None

    def installSettings(self, page: object) -> None:
        _ = page
        return None

    def editTask(
        self,
        task: Task,
        mode: EditMode,
        parent: object | None = None,
    ) -> bool:
        _ = task
        _ = mode
        _ = parent
        return False

    def createTaskCard(self, task: Task, parent: object | None = None) -> object:
        _ = task
        _ = parent
        return object()

    def createResultCard(self, task: Task, parent: object | None = None) -> object:
        _ = task
        _ = parent
        return object()


class FeaturePackCoreV1Tests(unittest.TestCase):
    _temporaryDirectory: tempfile.TemporaryDirectory[str] | None = None
    featuresPath: Path = ROOT
    tempPath: Path = ROOT

    def setUp(self) -> None:
        temporaryDirectory = tempfile.TemporaryDirectory()
        self._temporaryDirectory = temporaryDirectory
        self.addCleanup(temporaryDirectory.cleanup)
        self.tempPath = Path(temporaryDirectory.name)
        self.featuresPath = self.tempPath / "features"

    def createRecorder(self) -> TaskRecorder:
        recorder = TaskRecorder(recordFile=self.tempPath / "FeaturePackMemory.log")
        recorder.load()
        return recorder

    def createService(self) -> DefaultFeatureService:
        return DefaultFeatureService(featuresPath=self.featuresPath)

    def writePack(
        self,
        *,
        directoryName: str,
        entryBody: str,
    ) -> None:
        packDirectory = self.featuresPath / directoryName
        packDirectory.mkdir(parents=True, exist_ok=True)
        manifestBody = textwrap.dedent(
            f"""
            [pack]
            id = "{directoryName}"
            name = "{directoryName}"
            version = "1.0.0"
            api = 1
            entry = "pack.py"
            dependencies = []
            """
        ).strip()
        _ = (packDirectory / "manifest.toml").write_text(
            manifestBody + "\n",
            encoding="utf-8",
        )
        _ = (packDirectory / "pack.py").write_text(
            textwrap.dedent(entryBody).strip() + "\n",
            encoding="utf-8",
        )

    def testDefaultFeatureServiceCreateTaskRoutesTaskInputToLoadedPack(self) -> None:
        self.writePack(
            directoryName="demo_pack",
            entryBody="""
            from pathlib import Path

            from app.feature_pack.api import FeaturePack, StageSnapshot, Task, TaskConfig, TaskInput, TaskSnapshot, TaskStage


            class DemoStage(TaskStage):
                async def run(self) -> None:
                    return None

                def reset(self) -> None:
                    return None

                def snapshot(self) -> StageSnapshot:
                    return StageSnapshot(
                        id=self.id,
                        kind=self.kind,
                        name=self.name,
                        state="waiting",
                        progress=0.0,
                        doneBytes=0,
                        speed=0,
                    )


            class DemoTask(Task):
                def __init__(self, *, config: TaskConfig) -> None:
                    self.state = "waiting"
                    self.progress = 0.0
                    self.doneBytes = 0
                    self.totalBytes = 2048
                    self.target = ""
                    super().__init__(
                        id="created-task",
                        packId="demo_pack",
                        kind="demo",
                        version=1,
                        config=config,
                        stages=[
                            DemoStage(
                                id="stage-1",
                                kind="download",
                                version=1,
                                name="下载阶段",
                            )
                        ],
                    )
                    self.syncOutput()

                def syncOutput(self) -> None:
                    self.target = str(self.config.folder / self.config.name)

                def reset(self) -> None:
                    self.state = "waiting"

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


            class DemoPack(FeaturePack):
                def accepts(self, source: str) -> bool:
                    return source.startswith("demo:")

                async def createTask(self, data: TaskInput) -> Task | None:
                    return DemoTask(config=data.config)

                def owns(self, task: Task) -> bool:
                    return task.packId == self.manifest.id
            """,
        )
        service = self.createService()
        service.loadPacks(_FakeWindow())

        createdTask = asyncio.run(
            service.createTask(
                TaskInput(
                    config=TaskConfig(
                        source="demo:video",
                        folder=Path("downloads"),
                        name="demo.bin",
                    )
                )
            )
        )

        self.assertEqual(createdTask.id, "created-task")
        self.assertEqual(createdTask.packId, "demo_pack")
        self.assertEqual(createdTask.config.source, "demo:video")
        self.assertEqual(createdTask.snapshot().target, str(Path("downloads") / "demo.bin"))

    def testHostCoreServiceCreatesTaskFromTaskInputThroughV1FeatureService(self) -> None:
        task = _DemoCoreTask(id="task-host", source="demo:host")
        featureService = _RecordingFeatureService(createdTasks=[task])
        taskInput = TaskInput(
            config=TaskConfig(
                source="demo:host",
                folder=Path("downloads"),
                name="host.bin",
            )
        )

        with patch("app.services.core_service.featureService", featureService):
            createdTask = asyncio.run(
                CoreService._createTaskFromInput(
                    cast(CoreService, object()),
                    taskInput,
                )
            )

        self.assertIs(createdTask, task)
        self.assertEqual(featureService.createTaskInputs, [taskInput])

    def testCoreServiceCreateTaskSchedulesImmediatelyAndRecordsTask(self) -> None:
        recorder = self.createRecorder()
        task = _DemoCoreTask(id="task-1", source="demo:task-1")
        featureService = _RecordingFeatureService(createdTasks=[task])
        coreService = FeaturePackCoreService(
            featureService=featureService,
            recorder=recorder,
            maxRunningTasks=1,
        )
        taskInput = TaskInput(
            config=TaskConfig(
                source="demo:task-1",
                folder=Path("downloads"),
                name="task-1.bin",
            )
        )

        async def runScenario() -> None:
            createdTask = await coreService.createTask(taskInput)
            self.assertIs(createdTask, task)
            await task.enteredRun.wait()
            self.assertEqual(featureService.createTaskInputs, [taskInput])
            self.assertEqual(task.state, "running")
            self.assertEqual(task.runCalls, 1)
            self.assertIs(coreService.getTaskById(task.id), task)
            self.assertIn(task.id, recorder.memorizedTasks)

            task.releaseRun.set()
            await coreService.waitForIdle()

            self.assertEqual(task.state, "completed")
            self.assertFalse(coreService.runningTasks)
            self.assertEqual(coreService.runningTaskCount(), 0)

        asyncio.run(runScenario())

    def testCoreServiceQueuesSlotBoundTasksAndPromotesWaitingTaskAfterPause(self) -> None:
        recorder = self.createRecorder()
        firstTask = _DemoCoreTask(id="task-1", source="demo:task-1")
        secondTask = _DemoCoreTask(id="task-2", source="demo:task-2")
        featureService = _RecordingFeatureService(createdTasks=[firstTask, secondTask])
        coreService = FeaturePackCoreService(
            featureService=featureService,
            recorder=recorder,
            maxRunningTasks=1,
        )

        async def runScenario() -> None:
            await coreService.createTask(
                TaskInput(
                    config=TaskConfig(
                        source="demo:task-1",
                        folder=Path("downloads"),
                        name="task-1.bin",
                    )
                )
            )
            await firstTask.enteredRun.wait()

            await coreService.createTask(
                TaskInput(
                    config=TaskConfig(
                        source="demo:task-2",
                        folder=Path("downloads"),
                        name="task-2.bin",
                    )
                )
            )

            self.assertEqual(secondTask.state, "waiting")
            self.assertEqual(secondTask.runCalls, 0)
            self.assertEqual(coreService.waitingTaskIds, [secondTask.id])

            await coreService.stopTask(firstTask)
            await secondTask.enteredRun.wait()

            self.assertEqual(firstTask.pauseCalls, 1)
            self.assertEqual(firstTask.state, "paused")
            self.assertEqual(secondTask.state, "running")
            self.assertEqual(secondTask.runCalls, 1)

            secondTask.releaseRun.set()
            await coreService.waitForIdle()

            self.assertEqual(secondTask.state, "completed")
            self.assertFalse(coreService.waitingTaskIds)

        asyncio.run(runScenario())

    def testCoreServiceDoesNotCountNonSlotTasksAgainstDownloadLimit(self) -> None:
        recorder = self.createRecorder()
        slotTask = _DemoCoreTask(id="task-slot", source="demo:slot")
        sideTask = _DemoCoreTask(
            id="task-side",
            source="demo:side",
            occupiesSlot=False,
            willOccupySlot=False,
        )
        featureService = _RecordingFeatureService(createdTasks=[slotTask, sideTask])
        coreService = FeaturePackCoreService(
            featureService=featureService,
            recorder=recorder,
            maxRunningTasks=1,
        )

        async def runScenario() -> None:
            await coreService.createTask(
                TaskInput(
                    config=TaskConfig(
                        source="demo:slot",
                        folder=Path("downloads"),
                        name="slot.bin",
                    )
                )
            )
            await slotTask.enteredRun.wait()

            await coreService.createTask(
                TaskInput(
                    config=TaskConfig(
                        source="demo:side",
                        folder=Path("downloads"),
                        name="side.bin",
                    )
                )
            )
            await sideTask.enteredRun.wait()

            self.assertEqual(coreService.runningTaskCount(), 1)
            self.assertEqual(len(coreService.runningTasks), 2)
            self.assertEqual(sideTask.state, "running")
            self.assertFalse(coreService.waitingTaskIds)

            slotTask.releaseRun.set()
            sideTask.releaseRun.set()
            await coreService.waitForIdle()

            self.assertEqual(slotTask.state, "completed")
            self.assertEqual(sideTask.state, "completed")

        asyncio.run(runScenario())


if __name__ == "__main__":
    _ = unittest.main()
