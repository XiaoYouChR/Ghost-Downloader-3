# pyright: reportImplicitOverride=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnannotatedClassAttribute=false, reportUnusedCallResult=false, reportInconsistentConstructor=false, reportUnnecessaryCast=false, reportAny=false

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from typing import cast

from PySide6.QtCore import QObject


ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    _ = sys.path.insert(0, str(ROOT))

from app.feature_pack.api import StageSnapshot
from app.feature_pack.api import Task
from app.feature_pack.api import TaskConfig
from app.feature_pack.api import TaskSnapshot
from app.feature_pack.api import TaskStage


class DemoTaskStage(TaskStage):
    def __init__(
        self,
        *,
        id: str,
        canPause: bool = True,
    ) -> None:
        super().__init__(id=id, kind="download", version=1, name=f"阶段 {id}")
        self.state = "waiting"
        self.progress = 0.0
        self.doneBytes = 0
        self.speed = 0
        self.error = ""
        self.configureCalls: list[TaskConfig] = []
        self.runCalls = 0
        self.resetCalls = 0
        self.pauseCalls = 0
        self.allowPause = canPause
        self.syncedTarget = ""

    async def run(self) -> None:
        self.runCalls += 1
        self.state = "running"
        self.progress = 100.0
        self.doneBytes = 1024
        self.speed = 0
        await asyncio.sleep(0)
        self.state = "completed"

    async def pause(self) -> None:
        self.pauseCalls += 1
        self.state = "paused"
        await asyncio.sleep(0)

    def canPause(self) -> bool:
        return self.allowPause

    def reset(self) -> None:
        self.resetCalls += 1
        self.state = "waiting"
        self.progress = 0.0
        self.doneBytes = 0
        self.speed = 0
        self.error = ""

    def configure(self, config: TaskConfig) -> None:
        self.configureCalls.append(config)

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

    def attachedTask(self) -> object | None:
        return self._task


class MissingSnapshotTask(Task):
    def syncOutput(self) -> None:
        return None

    def reset(self) -> None:
        return None


class DemoTask(Task):
    def __init__(self, *, config: TaskConfig, stages: list[TaskStage]) -> None:
        self.syncOutputCalls = 0
        self.resetCalls = 0
        self.state = "waiting"
        self.progress = 0.0
        self.doneBytes = 0
        self.totalBytes = 2048
        self.target = ""
        super().__init__(
            id="task-1",
            packId="demo_pack",
            kind="single_file",
            version=1,
            config=config,
            stages=stages,
        )

    def syncOutput(self) -> None:
        self.syncOutputCalls += 1
        self.target = str(self.config.folder / self.config.name)
        for stage in self.stages:
            if isinstance(stage, DemoTaskStage):
                stage.syncedTarget = self.target

    def reset(self) -> None:
        self.resetCalls += 1
        self.state = "waiting"
        self.progress = 0.0
        self.doneBytes = 0
        self.currentStageIndex = 0
        for stage in self.stages:
            stage.reset()

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


class TaskBaseTests(unittest.TestCase):
    def makeConfig(self) -> TaskConfig:
        return TaskConfig(
            source="https://example.com/file.bin",
            folder=Path("downloads"),
            name="file.bin",
            headers={"User-Agent": "Ghost Downloader"},
            proxies={"https": "http://127.0.0.1:7890"},
            chunks=8,
        )

    def testTaskRequiresSyncOutputResetAndSnapshotImplementations(self) -> None:
        self.assertEqual(
            getattr(Task, "__abstractmethods__", frozenset()),
            frozenset({"reset", "snapshot", "syncOutput"}),
        )
        self.assertEqual(
            getattr(MissingSnapshotTask, "__abstractmethods__", frozenset()),
            frozenset({"snapshot"}),
        )

        with self.assertRaises(TypeError):
            _ = Task(
                id="task-1",
                packId="demo_pack",
                kind="download",
                version=1,
                config=self.makeConfig(),
                stages=[],
            )

        with self.assertRaises(TypeError):
            _ = MissingSnapshotTask(
                id="task-2",
                packId="demo_pack",
                kind="download",
                version=1,
                config=self.makeConfig(),
                stages=[],
            )

    def testTaskKeepsQObjectIdentityAndNamedSignals(self) -> None:
        workflow = DemoTask(config=self.makeConfig(), stages=[])
        metaObject = workflow.metaObject()

        self.assertIsInstance(workflow, QObject)
        self.assertEqual(workflow.id, "task-1")
        self.assertEqual(workflow.packId, "demo_pack")
        self.assertEqual(workflow.kind, "single_file")
        self.assertEqual(workflow.version, 1)
        self.assertEqual(workflow.currentStageIndex, 0)
        self.assertGreaterEqual(metaObject.indexOfSignal("stateChanged(QString)"), 0)
        self.assertGreaterEqual(metaObject.indexOfSignal("progressChanged(double)"), 0)
        self.assertGreaterEqual(metaObject.indexOfSignal("snapshotChanged(PyObject)"), 0)

    def testTaskAddsStagesAndConfiguresWorkflowOutput(self) -> None:
        config = self.makeConfig()
        stageOne = DemoTaskStage(id="stage-1")
        stageTwo = DemoTaskStage(id="stage-2")
        workflow = DemoTask(config=config, stages=[stageOne])

        workflow.addStage(stageTwo)
        workflow.configure(config)

        self.assertEqual([stage.id for stage in workflow.iterStages()], ["stage-1", "stage-2"])
        self.assertIs(stageOne.attachedTask(), workflow)
        self.assertIs(stageTwo.attachedTask(), workflow)
        self.assertEqual(workflow.syncOutputCalls, 1)
        self.assertEqual(stageOne.configureCalls, [config])
        self.assertEqual(stageTwo.configureCalls, [config])
        self.assertEqual(stageOne.syncedTarget, str(config.folder / config.name))
        self.assertEqual(stageTwo.syncedTarget, str(config.folder / config.name))

    def testTaskCanPauseAggregatesAcrossStages(self) -> None:
        workflow = DemoTask(
            config=self.makeConfig(),
            stages=[
                DemoTaskStage(id="stage-1", canPause=True),
                DemoTaskStage(id="stage-2", canPause=False),
            ],
        )

        self.assertFalse(workflow.canPause())

    def testTaskRunPauseAndSnapshotCoordinateStages(self) -> None:
        stageOne = DemoTaskStage(id="stage-1")
        stageTwo = DemoTaskStage(id="stage-2")
        workflow = DemoTask(config=self.makeConfig(), stages=[stageOne, stageTwo])
        receivedStates: list[str] = []
        receivedProgress: list[float] = []
        receivedSnapshots: list[object] = []

        workflow.stateChanged.connect(receivedStates.append)
        workflow.progressChanged.connect(receivedProgress.append)
        workflow.snapshotChanged.connect(receivedSnapshots.append)

        asyncio.run(workflow.run())
        workflow.state = "running"
        workflow.progress = 100.0
        workflow.doneBytes = 2048
        workflow.stateChanged.emit(workflow.state)
        workflow.progressChanged.emit(workflow.progress)
        workflow.snapshotChanged.emit(workflow.snapshot())
        asyncio.run(workflow.pause())

        taskSnapshot = workflow.snapshot()

        self.assertEqual(stageOne.runCalls, 1)
        self.assertEqual(stageTwo.runCalls, 1)
        self.assertEqual(stageOne.pauseCalls, 0)
        self.assertEqual(stageTwo.pauseCalls, 1)
        self.assertEqual(workflow.currentStageIndex, 1)
        self.assertEqual(receivedStates, ["running"])
        self.assertEqual(receivedProgress, [100.0])
        self.assertEqual(len(receivedSnapshots), 1)
        self.assertIsInstance(receivedSnapshots[0], TaskSnapshot)
        self.assertIsInstance(taskSnapshot, TaskSnapshot)
        self.assertEqual(taskSnapshot.id, "task-1")
        self.assertEqual(taskSnapshot.packId, "demo_pack")
        self.assertEqual(taskSnapshot.kind, "single_file")
        self.assertEqual(taskSnapshot.name, "file.bin")
        self.assertEqual(taskSnapshot.state, "running")
        self.assertEqual(taskSnapshot.progress, 100.0)
        self.assertEqual(taskSnapshot.doneBytes, 2048)
        self.assertEqual(taskSnapshot.totalBytes, 2048)
        self.assertTrue(taskSnapshot.canPause)
        self.assertEqual(taskSnapshot.target, "")
        self.assertEqual(len(taskSnapshot.stages), 2)
        self.assertEqual(
            [type(stage) for stage in taskSnapshot.stages],
            [StageSnapshot, StageSnapshot],
        )

    def testTaskResetAndDefaultEditFormStaySimple(self) -> None:
        workflow = DemoTask(
            config=self.makeConfig(),
            stages=[DemoTaskStage(id="stage-1"), DemoTaskStage(id="stage-2")],
        )
        workflow.state = "failed"
        workflow.progress = 50.0
        workflow.doneBytes = 512
        workflow.currentStageIndex = 1

        workflow.reset()

        self.assertEqual(workflow.resetCalls, 1)
        self.assertEqual(workflow.state, "waiting")
        self.assertEqual(workflow.progress, 0.0)
        self.assertEqual(workflow.doneBytes, 0)
        self.assertEqual(workflow.currentStageIndex, 0)
        self.assertEqual(workflow.editForm("before"), None)
        resetCounts = [cast(DemoTaskStage, stage).resetCalls for stage in workflow.stages]
        self.assertEqual(resetCounts, [1, 1])


if __name__ == "__main__":
    _ = unittest.main()
