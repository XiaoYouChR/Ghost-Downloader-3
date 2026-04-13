# pyright: reportImplicitOverride=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportAttributeAccessIssue=false, reportCallIssue=false, reportAny=false, reportMissingTypeStubs=false, reportInconsistentConstructor=false

from __future__ import annotations

import os
import sys
import time
import unittest
from pathlib import Path
from typing import cast
from typing import final

_ = os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    _ = sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QObject
from PySide6.QtCore import Qt
from PySide6.QtCore import QThread
from PySide6.QtCore import Slot
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import QWidget

from app.feature_pack.api import DefaultTaskCard
from app.feature_pack.api import StageSnapshot
from app.feature_pack.api import Task
from app.feature_pack.api import TaskConfig
from app.feature_pack.api import TaskSnapshot
from app.feature_pack.api import TaskStage


def ensureApplication() -> QApplication:
    application = QApplication.instance()
    if application is not None:
        return cast(QApplication, application)

    return QApplication([])


@final
class ProjectionStage(TaskStage):
    state: str
    progress: float
    doneBytes: int
    speed: int
    error: str

    def __init__(self, *, id: str = "stage-1") -> None:
        super().__init__(id=id, kind="download", version=1, name=f"阶段 {id}")
        self.state = "waiting"
        self.progress = 0.0
        self.doneBytes = 0
        self.speed = 0
        self.error = ""

    async def run(self) -> None:
        return None

    def reset(self) -> None:
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

    @Slot()
    def emitRunningProjection(self) -> None:
        self.state = "running"
        self.progress = 37.5
        self.doneBytes = 768
        self.speed = 256
        self.error = ""
        snapshot = self.snapshot()
        self.stateChanged.emit(self.state)
        self.progressChanged.emit(self.progress)
        self.snapshotChanged.emit(snapshot)

    @Slot()
    def emitFailureProjection(self) -> None:
        self.state = "failed"
        self.error = "network error"
        self.failed.emit(self.error)
        self.snapshotChanged.emit(self.snapshot())


@final
class ProjectionTask(Task):
    state: str
    progress: float
    doneBytes: int
    totalBytes: int
    target: str

    def __init__(self, *, config: TaskConfig, stage: ProjectionStage) -> None:
        self.state = "waiting"
        self.progress = 0.0
        self.doneBytes = 0
        self.totalBytes = 2048
        self.target = str(config.folder / config.name)
        super().__init__(
            id="task-1",
            packId="demo_pack",
            kind="single_file",
            version=1,
            config=config,
            stages=[stage],
        )

    def syncOutput(self) -> None:
        self.target = str(self.config.folder / self.config.name)

    def reset(self) -> None:
        self.state = "waiting"
        self.progress = 0.0
        self.doneBytes = 0

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
            stages=self.stageSnapshots(),
        )


class RecordingEditor:
    def __init__(self) -> None:
        self.calls: list[tuple[Task, str, QWidget | None]] = []

    def editTask(
        self,
        task: Task,
        mode: str,
        parent: QWidget | None = None,
    ) -> bool:
        self.calls.append((task, mode, parent))
        return True


class TaskEventProjectionTests(unittest.TestCase):
    application: QApplication | None = None

    @classmethod
    def setUpClass(cls) -> None:
        cls.application = ensureApplication()

    def processEvents(self) -> None:
        application = self.application
        assert application is not None
        application.processEvents()

    def waitUntil(self, predicate: object, *, timeoutMs: int = 2000) -> None:
        deadline = time.monotonic() + (timeoutMs / 1000)
        while time.monotonic() < deadline:
            if callable(predicate) and predicate():
                return
            self.processEvents()
            QTest.qWait(10)

        self.fail("condition was not satisfied before timeout")

    def showWidget(self, widget: QWidget) -> None:
        widget.show()
        self.processEvents()
        self.addCleanup(widget.close)
        self.addCleanup(widget.deleteLater)

    def cleanupWorkerThread(self, worker: QThread, stage: ProjectionStage) -> None:
        stage.deleteLater()
        worker.quit()
        _ = worker.wait(2000)

    def createParent(self) -> QWidget:
        parent = QWidget()
        parent.resize(960, 720)
        self.showWidget(parent)
        return parent

    def makeConfig(self) -> TaskConfig:
        return TaskConfig(
            source="https://example.com/archive.zip",
            folder=Path("downloads"),
            name="archive.zip",
            headers={"User-Agent": "Ghost Downloader"},
            proxies={"https": "http://127.0.0.1:7890"},
            chunks=4,
        )

    def testTaskProjectsStageEventsToTaskCard(self) -> None:
        stage = ProjectionStage()
        task = ProjectionTask(config=self.makeConfig(), stage=stage)
        card = DefaultTaskCard(
            task=task,
            editor=RecordingEditor(),
            parent=self.createParent(),
        )
        self.showWidget(card)
        receivedEvents: list[tuple[str, str]] = []

        def onProjected(projectedStage: object, event: str, _payload: object) -> None:
            stageId = getattr(projectedStage, "id", "<unknown>")
            receivedEvents.append((stageId, event))

        _ = task.stageEventProjected.connect(onProjected)

        stage.emitRunningProjection()
        self.waitUntil(lambda: card.stateLabel.text() == "状态: running")
        self.waitUntil(lambda: card.progressLabel.text() == "37.5%  768.00 B / 2.00 KB")

        taskSnapshot = task.snapshot()
        self.assertEqual(
            receivedEvents,
            [
                ("stage-1", "state"),
                ("stage-1", "progress"),
                ("stage-1", "snapshot"),
            ],
        )
        self.assertEqual(taskSnapshot.state, "running")
        self.assertEqual(taskSnapshot.progress, 37.5)
        self.assertEqual(taskSnapshot.doneBytes, 768)
        self.assertEqual(taskSnapshot.stages[0].state, "running")
        self.assertEqual(taskSnapshot.stages[0].doneBytes, 768)

        stage.emitFailureProjection()
        self.waitUntil(lambda: card.stateLabel.text() == "状态: failed")

        failedSnapshot = task.snapshot()
        self.assertEqual(receivedEvents[-2:], [("stage-1", "failed"), ("stage-1", "snapshot")])
        self.assertEqual(failedSnapshot.state, "failed")
        self.assertEqual(failedSnapshot.stages[0].error, "network error")

    def testStageEventsUseQueuedConnectionAcrossThreads(self) -> None:
        stage = ProjectionStage()
        task = ProjectionTask(config=self.makeConfig(), stage=stage)
        card = DefaultTaskCard(
            task=task,
            editor=RecordingEditor(),
            parent=self.createParent(),
        )
        self.showWidget(card)
        worker = QThread()
        worker.setObjectName("feature-pack-stage-worker")
        projectedThreads: list[QObject] = []

        def onProjected(_stage: object, _event: str, _payload: object) -> None:
            projectedThreads.append(QThread.currentThread())

        _ = task.stageEventProjected.connect(onProjected)
        _ = stage.moveToThread(worker)
        self.addCleanup(self.cleanupWorkerThread, worker, stage)
        _ = worker.started.connect(
            stage.emitRunningProjection,
            Qt.ConnectionType.QueuedConnection,
        )
        worker.start()
        self.waitUntil(lambda: len(projectedThreads) == 3)
        self.waitUntil(lambda: card.stateLabel.text() == "状态: running")
        self.waitUntil(lambda: card.progressLabel.text() == "37.5%  768.00 B / 2.00 KB")

        self.assertIs(stage.thread(), worker)
        self.assertTrue(projectedThreads)
        self.assertTrue(all(thread is task.thread() for thread in projectedThreads))


if __name__ == "__main__":
    _ = unittest.main()
