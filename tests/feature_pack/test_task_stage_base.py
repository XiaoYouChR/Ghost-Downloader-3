# pyright: reportImplicitOverride=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnannotatedClassAttribute=false, reportUnusedCallResult=false, reportInconsistentConstructor=false, reportUnnecessaryCast=false

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path

from PySide6.QtCore import QObject


ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    _ = sys.path.insert(0, str(ROOT))

from app.feature_pack.api import StageSnapshot
from app.feature_pack.api import TaskConfig
from app.feature_pack.api import TaskStage


class DemoTaskStage(TaskStage):
    def __init__(
        self,
        *,
        id: str = "stage-1",
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
        self.resetCount = 0
        self.runCount = 0

    async def run(self) -> None:
        self.runCount += 1
        self.state = "running"
        await asyncio.sleep(0)
        self.progress = 50.0
        self.doneBytes = 1024
        self.speed = 256

    def reset(self) -> None:
        self.resetCount += 1
        self.state = "waiting"
        self.progress = 0.0
        self.doneBytes = 0
        self.speed = 0
        self.error = ""

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


class MissingSnapshotTaskStage(TaskStage):
    async def run(self) -> None:
        return None

    def reset(self) -> None:
        return None


class TaskStageBaseTests(unittest.TestCase):
    def testTaskStageRequiresRunResetAndSnapshotImplementations(self) -> None:
        self.assertEqual(
            getattr(TaskStage, "__abstractmethods__", frozenset()),
            frozenset({"reset", "run", "snapshot"}),
        )
        self.assertEqual(
            getattr(MissingSnapshotTaskStage, "__abstractmethods__", frozenset()),
            frozenset({"snapshot"}),
        )

        with self.assertRaises(TypeError):
            _ = TaskStage(
                id="stage-1",
                kind="download",
                version=1,
                name="下载阶段",
            )

        with self.assertRaises(TypeError):
            _ = MissingSnapshotTaskStage(
                id="stage-2",
                kind="download",
                version=1,
                name="未完成阶段",
            )

    def testTaskStageKeepsQObjectIdentityAndNamedSignals(self) -> None:
        stage = DemoTaskStage()
        metaObject = stage.metaObject()

        self.assertIsInstance(stage, QObject)
        self.assertEqual(stage.id, "stage-1")
        self.assertEqual(stage.kind, "download")
        self.assertEqual(stage.version, 1)
        self.assertEqual(stage.name, "下载阶段")
        self.assertGreaterEqual(metaObject.indexOfSignal("stateChanged(QString)"), 0)
        self.assertGreaterEqual(metaObject.indexOfSignal("progressChanged(double)"), 0)
        self.assertGreaterEqual(metaObject.indexOfSignal("snapshotChanged(PyObject)"), 0)
        self.assertGreaterEqual(metaObject.indexOfSignal("failed(QString)"), 0)
        self.assertGreaterEqual(metaObject.indexOfSignal("commandRequested(QString,PyObject)"), 0)

    def testTaskStageAttachConfigureAndCanPauseUseDefaultContract(self) -> None:
        stage = DemoTaskStage()
        owner = object()
        config = TaskConfig(
            source="https://example.com/video.mp4",
            folder=Path("downloads"),
            name="video.mp4",
            headers={"User-Agent": "Ghost Downloader"},
            proxies={"https": "socks5://127.0.0.1:1080"},
            chunks=4,
        )

        attachResult = stage.attach(owner)
        configureResult = stage.configure(config)
        stage.requestCommand("configure", config)

        self.assertIsNone(attachResult)
        self.assertIs(stage.attachedTask(), owner)
        self.assertTrue(stage.canPause())
        self.assertIsNone(configureResult)
        self.assertEqual(stage.snapshot().state, "waiting")

    def testTaskStageRunResetAndSnapshotStayQtFree(self) -> None:
        stage = DemoTaskStage()
        receivedStates: list[str] = []
        receivedProgress: list[float] = []
        receivedSnapshots: list[object] = []
        receivedErrors: list[str] = []

        stage.stateChanged.connect(receivedStates.append)
        stage.progressChanged.connect(receivedProgress.append)
        stage.snapshotChanged.connect(receivedSnapshots.append)
        stage.failed.connect(receivedErrors.append)

        asyncio.run(stage.run())
        stage.stateChanged.emit(stage.snapshot().state)
        stage.progressChanged.emit(stage.snapshot().progress)
        stage.snapshotChanged.emit(stage.snapshot())
        stage.failed.emit("network error")
        stage.reset()

        stageSnapshot = stage.snapshot()

        self.assertEqual(stage.runCount, 1)
        self.assertEqual(stage.resetCount, 1)
        self.assertEqual(receivedStates, ["running"])
        self.assertEqual(receivedProgress, [50.0])
        self.assertEqual(receivedErrors, ["network error"])
        self.assertEqual(len(receivedSnapshots), 1)
        self.assertIsInstance(receivedSnapshots[0], StageSnapshot)
        self.assertIsInstance(stageSnapshot, StageSnapshot)
        self.assertEqual(stageSnapshot.id, "stage-1")
        self.assertEqual(stageSnapshot.kind, "download")
        self.assertEqual(stageSnapshot.name, "下载阶段")
        self.assertEqual(stageSnapshot.state, "waiting")
        self.assertEqual(stageSnapshot.progress, 0.0)
        self.assertEqual(stageSnapshot.doneBytes, 0)
        self.assertEqual(stageSnapshot.speed, 0)
        self.assertEqual(stageSnapshot.error, "")


if __name__ == "__main__":
    _ = unittest.main()
