# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false, reportUnknownVariableType=false, reportAttributeAccessIssue=false, reportCallIssue=false, reportAny=false, reportInconsistentConstructor=false, reportImplicitOverride=false, reportMissingTypeStubs=false

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from typing import cast
from unittest.mock import patch

_ = os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    _ = sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QPoint
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import QDialog
from PySide6.QtWidgets import QWidget

from app.feature_pack.api import DefaultResultCard
from app.feature_pack.api import DefaultTaskCard
from app.feature_pack.api import DefaultTaskEditor
from app.feature_pack.api import FormField
from app.feature_pack.api import MultiFileTask
from app.feature_pack.api import SingleFileTask
from app.feature_pack.api import StageSnapshot
from app.feature_pack.api import TaskConfig
from app.feature_pack.api import TaskFile
from app.feature_pack.api import TaskForm
from app.feature_pack.api import TaskSnapshot
from app.feature_pack.api import TaskStage


def ensureApplication() -> QApplication:
    application = QApplication.instance()
    if application is not None:
        return cast(QApplication, application)

    return QApplication([])


class DemoCardStage(TaskStage):
    def __init__(self, *, id: str = "stage-1") -> None:
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
            error="",
        )


class EditableSingleFileTask(SingleFileTask):
    state: str
    progress: float
    doneBytes: int
    totalBytes: int
    target: str

    def __init__(self, *, config: TaskConfig) -> None:
        self.state = "running"
        self.progress = 42.5
        self.doneBytes = 425
        self.totalBytes = 1000
        self.target = ""
        self.configureCalls: list[TaskConfig] = []
        super().__init__(
            id="task-single",
            packId="demo_pack",
            kind="single_file",
            version=1,
            config=config,
            stages=[DemoCardStage()],
        )

    def syncOutput(self) -> None:
        self.target = str(self.path)

    def configure(self, config: TaskConfig) -> None:
        self.configureCalls.append(config)
        super().configure(config)

    def editForm(self, _mode: str) -> TaskForm | None:
        return TaskForm(
            title="编辑单文件任务",
            fields=(
                FormField(key="source", label="来源", kind="text"),
                FormField(key="name", label="文件名", kind="text"),
                FormField(key="folder", label="目录", kind="folder"),
            ),
        )

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
            target=str(self.path),
            stages=tuple(stage.snapshot() for stage in self.stages),
        )


class EditableMultiFileTask(MultiFileTask):
    state: str
    progress: float
    doneBytes: int
    totalBytes: int
    target: str

    def __init__(self, *, config: TaskConfig, files: list[TaskFile]) -> None:
        self.state = "waiting"
        self.progress = 0.0
        self.doneBytes = 0
        self.totalBytes = sum(file.size for file in files)
        self.target = ""
        self.actionLog: list[str] = []
        self.configureCalls: list[TaskConfig] = []
        self.selectCalls: list[set[str]] = []
        super().__init__(
            id="task-multi",
            packId="demo_pack",
            kind="multi_file",
            version=1,
            config=config,
            stages=[DemoCardStage()],
            files=files,
        )

    def syncOutput(self) -> None:
        self.target = str(self.root)

    def select(self, ids: set[str]) -> None:
        self.actionLog.append("select")
        self.selectCalls.append(set(ids))
        super().select(ids)

    def configure(self, config: TaskConfig) -> None:
        self.actionLog.append("configure")
        self.configureCalls.append(config)
        super().configure(config)

    def editForm(self, _mode: str) -> TaskForm | None:
        return TaskForm(
            title="编辑多文件任务",
            fields=(
                FormField(key="source", label="来源", kind="text"),
                FormField(key="name", label="目录名", kind="text"),
                FormField(key="folder", label="输出目录", kind="folder"),
                FormField(key="files", label="保留内容", kind="files"),
            ),
        )

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
            target=str(self.root),
            stages=tuple(stage.snapshot() for stage in self.stages),
        )


class RecordingEditor:
    def __init__(self) -> None:
        self.calls: list[tuple[object, str, object | None]] = []

    def editTask(self, task: object, mode: str, parent: object | None = None) -> bool:
        self.calls.append((task, mode, parent))
        return True


class DefaultTaskCardsTests(unittest.TestCase):
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

    def makeConfig(self) -> TaskConfig:
        return TaskConfig(
            source="https://example.com/archive.zip",
            folder=Path("downloads"),
            name="archive.zip",
            headers={"User-Agent": "Ghost Downloader"},
            proxies={"https": "http://127.0.0.1:7890"},
            chunks=8,
        )

    def makeFiles(self) -> list[TaskFile]:
        return [
            TaskFile(id="file-1", path="Season 1/episode-1.mp4", size=100, selected=True),
            TaskFile(id="file-2", path="Season 1/episode-2.mp4", size=120, selected=False),
            TaskFile(id="file-3", path="Season 1/episode-3.mp4", size=140, selected=True),
        ]

    def testDefaultTaskCardUsesHostEditTaskEntryPoint(self) -> None:
        task = EditableSingleFileTask(config=self.makeConfig())
        editor = RecordingEditor()
        card = DefaultTaskCard(task=task, editor=editor, parent=self.createParent())
        self.showWidget(card)

        self.assertEqual(card.nameLabel.text(), "archive.zip")
        self.assertEqual(card.stateLabel.text(), "状态: running")
        self.assertEqual(card.progressLabel.text(), "42.5%  425.00 B / 1000.00 B")

        QTest.mouseClick(card.editButton, Qt.MouseButton.LeftButton)

        self.assertEqual(len(editor.calls), 1)
        self.assertIs(editor.calls[0][0], task)
        self.assertEqual(editor.calls[0][1], "running")
        self.assertIs(editor.calls[0][2], card)
        self.assertEqual(task.configureCalls, [])

    def testDefaultResultCardUsesHostEditTaskEntryPointOnDoubleClick(self) -> None:
        task = EditableSingleFileTask(config=self.makeConfig())
        editor = RecordingEditor()
        card = DefaultResultCard(task=task, editor=editor, parent=self.createParent())
        self.showWidget(card)

        self.assertEqual(card.nameLabel.text(), "archive.zip")
        self.assertEqual(card.detailLabel.text(), "目标: downloads\\archive.zip")

        QTest.mouseDClick(
            card,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            QPoint(card.width() // 2, card.height() // 2),
        )

        self.assertEqual(len(editor.calls), 1)
        self.assertIs(editor.calls[0][0], task)
        self.assertEqual(editor.calls[0][1], "before")
        self.assertIs(editor.calls[0][2], card)
        self.assertEqual(task.configureCalls, [])

    def testDefaultTaskEditorAppliesSelectionAndConfigThroughTaskBoundaries(self) -> None:
        task = EditableMultiFileTask(config=self.makeConfig(), files=self.makeFiles())
        editor = DefaultTaskEditor()
        receivedSnapshots: list[TaskSnapshot] = []

        def collectSnapshot(snapshot: object) -> None:
            receivedSnapshots.append(cast(TaskSnapshot, snapshot))

        _ = task.snapshotChanged.connect(collectSnapshot)
        newConfig = TaskConfig(
            source="https://mirror.example.com/archive.zip",
            folder=Path("archive"),
            name="season-1",
            headers=task.config.headers,
            proxies=task.config.proxies,
            chunks=task.config.chunks,
        )

        with patch("app.feature_pack.api.service.TaskConfigDialog") as dialogMock:
            dialog = dialogMock.return_value
            dialog.exec.return_value = QDialog.DialogCode.Accepted
            dialog.selectedIds.return_value = {"file-2"}
            dialog.config.return_value = newConfig

            accepted = editor.editTask(task, "before", self.createParent())

        self.assertTrue(accepted)
        dialogMock.assert_called_once()
        self.assertEqual(task.actionLog, ["select", "configure"])
        self.assertEqual(task.selectCalls, [{"file-2"}])
        self.assertEqual(task.configureCalls, [newConfig])
        self.assertEqual(task.selectedIds, {"file-2"})
        self.assertEqual(task.config, newConfig)
        self.assertEqual(task.target, str(Path("archive") / "season-1"))
        self.assertEqual(len(receivedSnapshots), 1)
        self.assertEqual(receivedSnapshots[0].target, str(Path("archive") / "season-1"))

    def testDefaultTaskEditorReturnsFalseWhenTaskHasNoEditForm(self) -> None:
        task = EditableSingleFileTask(config=self.makeConfig())

        def noEditForm(_mode: object) -> None:
            return None

        setattr(task, "editForm", noEditForm)
        editor = DefaultTaskEditor()

        accepted = editor.editTask(task, "running", self.createParent())

        self.assertFalse(accepted)
        self.assertEqual(task.configureCalls, [])


if __name__ == "__main__":
    _ = unittest.main()
