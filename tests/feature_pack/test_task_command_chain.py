# pyright: reportImplicitOverride=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportAttributeAccessIssue=false, reportCallIssue=false, reportAny=false, reportMissingTypeStubs=false, reportInconsistentConstructor=false

from __future__ import annotations

import asyncio
import os
import sys
import unittest
from pathlib import Path
from typing import cast
from typing import final

_ = os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    _ = sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Qt
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
class CommandChainStage(TaskStage):
    state: str
    progress: float
    doneBytes: int
    speed: int
    error: str
    pauseCalls: int

    def __init__(self, *, id: str = "stage-1") -> None:
        super().__init__(id=id, kind="download", version=1, name=f"阶段 {id}")
        self.state = "waiting"
        self.progress = 0.0
        self.doneBytes = 0
        self.speed = 0
        self.error = ""
        self.configureCalls: list[TaskConfig] = []
        self.pauseCalls = 0
        self.customCommands: list[tuple[str, object | None]] = []

    async def run(self) -> None:
        return None

    async def pause(self) -> None:
        self.pauseCalls += 1
        self.state = "paused"
        await asyncio.sleep(0)

    def configure(self, config: TaskConfig) -> None:
        self.configureCalls.append(config)

    def dispatchCustomCommand(
        self,
        command: str,
        payload: object | None = None,
    ) -> object | None:
        self.customCommands.append((command, payload))
        return None

    def reset(self) -> None:
        self.state = "waiting"

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
class CommandChainTask(Task):
    state: str
    progress: float
    doneBytes: int
    totalBytes: int
    target: str

    def __init__(self, *, config: TaskConfig, stage: CommandChainStage) -> None:
        self.state = "waiting"
        self.progress = 0.0
        self.doneBytes = 0
        self.totalBytes = 2048
        self.target = str(config.folder / config.name)
        self.customCommands: list[tuple[str, object | None]] = []
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

    def dispatchCustomCommand(
        self,
        command: str,
        payload: object | None = None,
    ) -> object | None:
        self.customCommands.append((command, payload))
        if command == "stage_custom":
            return self.dispatchToCurrentStage(command, payload)

        return super().dispatchCustomCommand(command, payload)

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


class TaskCommandChainTests(unittest.TestCase):
    application: QApplication | None = None

    @classmethod
    def setUpClass(cls) -> None:
        cls.application = ensureApplication()

    def showWidget(self, widget: QWidget) -> None:
        widget.show()
        application = self.application
        assert application is not None
        application.processEvents()
        self.addCleanup(widget.close)
        self.addCleanup(widget.deleteLater)

    def createParent(self) -> QWidget:
        parent = QWidget()
        parent.resize(960, 720)
        self.showWidget(parent)
        return parent

    def makeConfig(self, *, name: str = "demo.bin") -> TaskConfig:
        return TaskConfig(
            source="https://example.com/demo.bin",
            folder=Path("downloads"),
            name=name,
            headers={"User-Agent": "Ghost Downloader"},
            proxies={"https": "http://127.0.0.1:7890"},
            chunks=4,
        )

    def testTaskRoutesCommandsToStageThroughExplicitBoundary(self) -> None:
        stage = CommandChainStage()
        task = CommandChainTask(config=self.makeConfig(), stage=stage)
        receivedTaskCommands: list[tuple[str, object | None]] = []
        receivedStageCommands: list[tuple[str, str, object | None]] = []
        updatedConfig = self.makeConfig(name="updated.bin")

        def onTaskCommand(command: str, payload: object) -> None:
            receivedTaskCommands.append((command, payload))

        def onStageCommand(
            targetStage: object,
            command: str,
            payload: object,
        ) -> None:
            stageId = getattr(targetStage, "id", "<unknown>")
            receivedStageCommands.append((stageId, command, payload))

        _ = task.commandRequested.connect(onTaskCommand)
        _ = task.stageCommandForwarded.connect(onStageCommand)

        task.requestCommand("configure", updatedConfig)
        task.requestCommand("pause")
        task.requestCommand("stage_custom", {"origin": "task"})

        self.assertEqual(task.config, updatedConfig)
        self.assertEqual(stage.configureCalls, [updatedConfig])
        self.assertEqual(stage.pauseCalls, 1)
        self.assertEqual(stage.customCommands, [("stage_custom", {"origin": "task"})])
        self.assertEqual(
            [command for command, _payload in receivedTaskCommands],
            ["configure", "pause", "stage_custom"],
        )
        self.assertEqual(
            receivedStageCommands,
            [
                ("stage-1", "configure", updatedConfig),
                ("stage-1", "pause", None),
                ("stage-1", "stage_custom", {"origin": "task"}),
            ],
        )

    def testDefaultTaskCardSendsCommandsToTaskInsteadOfStage(self) -> None:
        stage = CommandChainStage()
        task = CommandChainTask(config=self.makeConfig(), stage=stage)
        editor = RecordingEditor()
        parent = self.createParent()
        card = DefaultTaskCard(task=task, editor=editor, parent=parent)
        self.showWidget(card)
        receivedTaskCommands: list[tuple[str, object | None]] = []
        receivedStageCommands: list[tuple[str, str, object | None]] = []

        def onTaskCommand(command: str, payload: object) -> None:
            receivedTaskCommands.append((command, payload))

        def onStageCommand(
            targetStage: object,
            command: str,
            payload: object,
        ) -> None:
            stageId = getattr(targetStage, "id", "<unknown>")
            receivedStageCommands.append((stageId, command, payload))

        _ = task.commandRequested.connect(onTaskCommand)
        _ = task.stageCommandForwarded.connect(onStageCommand)

        card.requestTaskCommand("stage_custom", {"origin": "card"})
        QTest.mouseClick(card.editButton, Qt.MouseButton.LeftButton)

        self.assertEqual(task.customCommands, [("stage_custom", {"origin": "card"})])
        self.assertEqual(stage.customCommands, [("stage_custom", {"origin": "card"})])
        self.assertEqual(receivedTaskCommands, [("stage_custom", {"origin": "card"})])
        self.assertEqual(
            receivedStageCommands,
            [("stage-1", "stage_custom", {"origin": "card"})],
        )
        self.assertEqual(len(editor.calls), 1)
        self.assertIs(editor.calls[0][0], task)


if __name__ == "__main__":
    _ = unittest.main()
