# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportAny=false, reportExplicitAny=false, reportImplicitOverride=false, reportAttributeAccessIssue=false, reportCallIssue=false, reportUnusedCallResult=false, reportUnnecessaryCast=false, reportUnannotatedClassAttribute=false, reportUnusedParameter=false

from __future__ import annotations

import asyncio
import importlib
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from pathlib import PurePosixPath
from types import ModuleType
from typing import Any
from typing import cast
from unittest.mock import patch

_ = os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    _ = sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import QDialog
from PySide6.QtWidgets import QWidget

from app.feature_pack.api import DefaultFeatureService
from app.feature_pack.api import DefaultResultCard
from app.feature_pack.api import DefaultTaskCard
from app.feature_pack.api import MultiFileTask
from app.feature_pack.api import Task
from app.feature_pack.api import TaskConfig
from app.feature_pack.api import TaskInput
from app.feature_pack.api import TaskStage
from app.feature_pack.internal.recorder import TaskRecorder


class _FakeWindow:
    def __init__(self) -> None:
        self.installed: list[str] = []


def ensureApplication() -> QApplication:
    application = QApplication.instance()
    if application is not None:
        return cast(QApplication, application)

    return QApplication([])


class FakeFtpClient:
    def __init__(self, *, sourceType: str = "dir", supportsRange: bool = True) -> None:
        self.sourceType = sourceType
        self.supportsRange = supportsRange
        self.closed = False
        self.quitCalls = 0

    async def stat(self, path: PurePosixPath) -> dict[str, object]:
        if self.sourceType == "file":
            return {"type": "file", "size": 512}
        return {"type": "dir", "size": 0}

    async def command(self, command: str, expectedCode: str) -> None:
        _ = command
        _ = expectedCode
        if not self.supportsRange:
            raise RuntimeError("REST not supported")

    async def list(self, path: PurePosixPath, recursive: bool = True):
        _ = path
        _ = recursive
        entries = [
            (PurePosixPath("/media/Season 1/episode-1.mp4"), {"type": "file", "size": 128}),
            (PurePosixPath("/media/Season 1/episode-2.mp4"), {"type": "file", "size": 256}),
            (PurePosixPath("/media/Season 1"), {"type": "dir", "size": 0}),
        ]
        for entry in entries:
            yield entry

    async def quit(self) -> None:
        self.quitCalls += 1
        self.closed = True

    def close(self) -> None:
        self.closed = True


class FtpPackV1Tests(unittest.TestCase):
    application: QApplication | None = None
    _temporaryDirectory: tempfile.TemporaryDirectory[str] | None = None
    workspace: Path = ROOT

    @classmethod
    def setUpClass(cls) -> None:
        cls.application = ensureApplication()

    def setUp(self) -> None:
        temporaryDirectory = tempfile.TemporaryDirectory()
        self._temporaryDirectory = temporaryDirectory
        self.addCleanup(temporaryDirectory.cleanup)
        self.workspace = Path(temporaryDirectory.name)
        shutil.copytree(ROOT / "features" / "ftp_pack", self.workspace / "ftp_pack")
        self.resetFtpPackRegistries()

    def resetFtpPackRegistries(self) -> None:
        Task.__recordRegistry__.pop(("ftp_pack", "ftp_download", 1), None)
        TaskStage.__recordRegistry__.pop(
            ("ftp_pack", "ftp_download", 1, "ftp_download", 1),
            None,
        )
        for moduleName in list(sys.modules):
            if moduleName.startswith("_ghost_feature_pack_ftp_pack"):
                del sys.modules[moduleName]
            if moduleName.startswith("features.ftp_pack"):
                del sys.modules[moduleName]
            if moduleName.startswith("ftp_pack"):
                del sys.modules[moduleName]

    def createService(self) -> DefaultFeatureService:
        service = DefaultFeatureService(featuresPath=self.workspace)
        service.loadPacks(_FakeWindow())
        return service

    def taskModule(self) -> ModuleType:
        return cast(ModuleType, importlib.import_module("_ghost_feature_pack_ftp_pack.task"))

    def buildTaskInput(
        self,
        *,
        source: str = "ftp://user:pass@example.com/media",
        name: str = "",
    ) -> TaskInput:
        return TaskInput(
            config=TaskConfig(
                source=source,
                folder=self.workspace / "downloads",
                name=name,
                proxies={"ftp": "socks5://127.0.0.1:7890"},
                chunks=4,
            ),
        )

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

    def createDirectoryTask(self) -> Task:
        service = self.createService()
        taskModule = self.taskModule()
        fakeClient = FakeFtpClient(sourceType="dir", supportsRange=True)
        with patch.object(taskModule, "_openClient", return_value=fakeClient):
            return asyncio.run(service.createTask(self.buildTaskInput()))

    def testFtpPackCreatesMultiFileTaskFromDirectoryInput(self) -> None:
        service = self.createService()
        taskModule = self.taskModule()
        fakeClient = FakeFtpClient(sourceType="dir", supportsRange=True)

        with patch.object(taskModule, "_openClient", return_value=fakeClient):
            routedPack = service.packForSource("ftp://example.com/media")
            task = asyncio.run(service.createTask(self.buildTaskInput()))

        self.assertIsNotNone(routedPack)
        if routedPack is None:
            raise AssertionError("ftp_pack should route ftp sources")
        self.assertEqual(routedPack.manifest.id, "ftp_pack")
        self.assertTrue(fakeClient.closed)

        self.assertIsInstance(task, MultiFileTask)
        self.assertEqual(type(task).__name__, "FtpTask")
        self.assertEqual(task.packId, "ftp_pack")
        self.assertEqual(task.kind, "ftp_download")
        self.assertEqual(task.config.name, "media")
        self.assertEqual(task.fileCount, 2)
        self.assertEqual(task.selectedCount, 2)
        self.assertEqual(task.selectedIds, {"file-0", "file-1"})
        self.assertEqual(task.snapshot().target, str(self.workspace / "downloads" / "media"))
        self.assertEqual(task.snapshot().totalBytes, 384)

        self.assertEqual(
            [(file.id, file.path, file.size, file.selected) for file in task.files],
            [
                ("file-0", "Season 1/episode-1.mp4", 128, True),
                ("file-1", "Season 1/episode-2.mp4", 256, True),
            ],
        )

        stages = task.stages
        self.assertEqual([type(stage).__name__ for stage in stages], ["FtpTaskStage", "FtpTaskStage"])
        self.assertEqual(cast(str, getattr(stages[0], "remotePath")), "/media/Season 1/episode-1.mp4")
        self.assertEqual(cast(str, getattr(stages[1], "remotePath")), "/media/Season 1/episode-2.mp4")
        self.assertEqual(
            cast(str, getattr(stages[0], "resolvePath")),
            str(self.workspace / "downloads" / "media" / "Season 1" / "episode-1.mp4"),
        )
        self.assertEqual(cast(int, getattr(stages[0], "blockNum")), 4)
        self.assertEqual(cast(dict[str, str] | None, getattr(stages[0], "proxies")), {"ftp": "socks5://127.0.0.1:7890"})

        packForTask = service.packForTask(task)
        self.assertIsNotNone(packForTask)
        if packForTask is None:
            raise AssertionError("FTP task should route back to FTP Pack")
        self.assertEqual(packForTask.manifest.id, "ftp_pack")

    def testFtpTaskUsesDefaultCardsAndDefaultEditFlowForSelectionAndConfig(self) -> None:
        service = self.createService()
        taskModule = self.taskModule()
        fakeClient = FakeFtpClient(sourceType="dir", supportsRange=True)
        with patch.object(taskModule, "_openClient", return_value=fakeClient):
            task = asyncio.run(service.createTask(self.buildTaskInput()))

        taskCard = cast(DefaultTaskCard, service.createTaskCard(task, self.createParent()))
        resultCard = service.createResultCard(task, self.createParent())
        self.showWidget(taskCard)
        self.showWidget(cast(QWidget, resultCard))

        self.assertIsInstance(taskCard, DefaultTaskCard)
        self.assertIsInstance(resultCard, DefaultResultCard)
        self.assertEqual(taskCard.nameLabel.text(), "media")

        updatedConfig = TaskConfig(
            source=task.config.source,
            folder=self.workspace / "archive",
            name="renamed-media",
            proxies={"ftp": "socks4://127.0.0.1:1081"},
            chunks=2,
        )

        with patch("app.feature_pack.api.service.TaskConfigDialog") as dialogMock:
            dialog = dialogMock.return_value
            dialog.exec.return_value = QDialog.DialogCode.Accepted
            dialog.selectedIds.return_value = {"file-1"}
            dialog.config.return_value = updatedConfig

            QTest.mouseClick(taskCard.editButton, Qt.MouseButton.LeftButton)

        self.assertEqual(task.selectedIds, {"file-1"})
        self.assertEqual(task.selectedCount, 1)
        self.assertEqual(task.snapshot().totalBytes, 256)
        self.assertEqual(task.config, updatedConfig)
        self.assertEqual(task.snapshot().target, str(self.workspace / "archive" / "renamed-media"))
        self.assertEqual(
            cast(str, getattr(task.stages[1], "resolvePath")),
            str(self.workspace / "archive" / "renamed-media" / "Season 1" / "episode-2.mp4"),
        )
        self.assertEqual(cast(int, getattr(task.stages[1], "blockNum")), 2)
        self.assertEqual(cast(dict[str, str] | None, getattr(task.stages[1], "proxies")), {"ftp": "socks4://127.0.0.1:1081"})

    def testFtpTaskRecorderRestoresSelectionFilesAndStageState(self) -> None:
        service = self.createService()
        taskModule = self.taskModule()
        fakeClient = FakeFtpClient(sourceType="dir", supportsRange=True)
        with patch.object(taskModule, "_openClient", return_value=fakeClient):
            task = asyncio.run(service.createTask(self.buildTaskInput()))

        task = cast(Any, task)
        task.select({"file-0"})
        stage = task.stages[0]
        getattr(stage, "setStatus")("running", emitSignals=False, notifyTask=False)
        getattr(stage, "updateTransfer")(
            doneBytes=64,
            speed=32,
            progress=50.0,
            notifyTask=False,
        )
        task.syncStatusFromStages()

        recorder = TaskRecorder(recordFile=self.workspace / "FeaturePackMemory.log")
        recorder.load()
        recorder.add(task, flush=True)
        record = recorder.serializeTask(cast(Task, task))
        restored = recorder.read()[task.id]

        self.assertEqual(record["packId"], "ftp_pack")
        self.assertEqual(record["kind"], "ftp_download")
        self.assertEqual(record["version"], 1)
        self.assertNotIn("type", record)
        self.assertEqual(type(restored).__name__, "FtpTask")
        self.assertIsInstance(restored, MultiFileTask)
        self.assertEqual(restored.selectedIds, {"file-0"})
        self.assertEqual(restored.selectedCount, 1)
        self.assertEqual(restored.fileCount, 2)
        self.assertEqual(restored.snapshot().state, "running")
        self.assertEqual(restored.snapshot().doneBytes, 64)
        self.assertEqual(restored.snapshot().totalBytes, 128)
        self.assertEqual(
            [(file.id, file.path, file.selected, file.doneBytes) for file in restored.files],
            [
                ("file-0", "Season 1/episode-1.mp4", True, 64),
                ("file-1", "Season 1/episode-2.mp4", False, 0),
            ],
        )

        restoredStage = restored.stages[0]
        self.assertEqual(type(restoredStage).__name__, "FtpTaskStage")
        self.assertEqual(cast(str, getattr(restoredStage, "remotePath")), "/media/Season 1/episode-1.mp4")
        self.assertEqual(
            cast(str, getattr(restoredStage, "resolvePath")),
            str(self.workspace / "downloads" / "media" / "Season 1" / "episode-1.mp4"),
        )


if __name__ == "__main__":
    _ = unittest.main()
