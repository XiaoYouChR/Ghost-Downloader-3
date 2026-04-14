# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false, reportUnknownVariableType=false, reportCallIssue=false, reportAttributeAccessIssue=false, reportAny=false, reportImplicitOverride=false

from __future__ import annotations

import asyncio
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from typing import Any, cast
from unittest.mock import AsyncMock
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
from app.feature_pack.api import TaskConfig
from app.feature_pack.api import TaskInput
from app.feature_pack.api import Task
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


class HttpPackV1Tests(unittest.TestCase):
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
        shutil.copytree(ROOT / "features" / "http_pack", self.workspace / "http_pack")
        self.resetHttpPackRegistries()

    def resetHttpPackRegistries(self) -> None:
        Task.__recordRegistry__.pop(("http_pack", "http_download", 1), None)
        TaskStage.__recordRegistry__.pop(
            ("http_pack", "http_download", 1, "http_download", 1),
            None,
        )
        for moduleName in list(sys.modules):
            if moduleName.startswith("_ghost_feature_pack_http_pack"):
                del sys.modules[moduleName]

    def createService(self) -> DefaultFeatureService:
        service = DefaultFeatureService(featuresPath=self.workspace)
        service.loadPacks(_FakeWindow())
        return service

    def packModule(self, service: DefaultFeatureService) -> ModuleType:
        pack = service.pack("http_pack")
        self.assertIsNotNone(pack)
        if pack is None:
            raise AssertionError("http_pack 未加载")
        return cast(ModuleType, sys.modules[type(pack).__module__])

    def buildTaskInput(
        self,
        *,
        source: str = "https://example.com/archive",
        name: str = "",
    ) -> TaskInput:
        return TaskInput(
            config=TaskConfig(
                source=source,
                folder=self.workspace / "downloads",
                name=name,
                headers={"User-Agent": "Ghost Downloader"},
                proxies={"https": "http://127.0.0.1:7890"},
                chunks=8,
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

    def testHttpPackCreateTaskBuildsSingleFileTaskFromTaskInput(self) -> None:
        service = self.createService()
        module = self.packModule(service)

        with patch.object(
            module,
            "_probeDownloadInfo",
            new=AsyncMock(
                return_value=(
                    4096,
                    True,
                    "https://cdn.example.com/files/archive",
                    {
                        "content-disposition": "attachment; filename*=UTF-8''episode-01.mp4",
                    },
                )
            ),
        ):
            task = asyncio.run(service.createTask(self.buildTaskInput()))

        self.assertEqual(type(task).__name__, "HttpTask")
        self.assertEqual(task.packId, "http_pack")
        self.assertEqual(task.kind, "http_download")
        self.assertEqual(task.config.name, "episode-01.mp4")
        self.assertEqual(task.config.folder, self.workspace / "downloads")
        self.assertEqual(task.config.chunks, 8)
        self.assertEqual(task.snapshot().target, str(self.workspace / "downloads" / "episode-01.mp4"))
        self.assertEqual(task.totalBytes, 4096)
        self.assertTrue(cast(bool, getattr(task, "supportsRange")))
        self.assertEqual(len(task.stages), 1)

        stage = task.stages[0]
        self.assertEqual(type(stage).__name__, "HttpTaskStage")
        self.assertEqual(stage.kind, "http_download")
        self.assertEqual(cast(str, getattr(stage, "resolvePath")), str(self.workspace / "downloads" / "episode-01.mp4"))
        self.assertEqual(cast(int, getattr(stage, "blockNum")), 8)

    def testHttpPackUsesDefaultCardsAndDefaultEditFlow(self) -> None:
        service = self.createService()
        module = self.packModule(service)

        with patch.object(
            module,
            "_probeDownloadInfo",
            new=AsyncMock(
                return_value=(
                    1024,
                    True,
                    "https://cdn.example.com/files/video.mp4",
                    {
                        "content-disposition": 'attachment; filename="video.mp4"',
                    },
                )
            ),
        ):
            task = asyncio.run(service.createTask(self.buildTaskInput(name="video.mp4")))

        taskCard = cast(DefaultTaskCard, service.createTaskCard(task, self.createParent()))
        resultCard = service.createResultCard(task, self.createParent())
        self.showWidget(taskCard)
        self.showWidget(cast(QWidget, resultCard))

        self.assertIsInstance(taskCard, DefaultTaskCard)
        self.assertIsInstance(resultCard, DefaultResultCard)
        self.assertEqual(taskCard.nameLabel.text(), "video.mp4")

        updatedConfig = TaskConfig(
            source="https://mirror.example.com/video.mp4",
            folder=self.workspace / "archive",
            name="renamed-video.mp4",
            headers={"Referer": "https://example.com"},
            proxies={"https": "socks5://127.0.0.1:1080"},
            chunks=4,
        )

        with patch("app.feature_pack.api.service.TaskConfigDialog") as dialogMock:
            dialog = dialogMock.return_value
            dialog.exec.return_value = QDialog.DialogCode.Accepted
            dialog.selectedIds.return_value = set()
            dialog.config.return_value = updatedConfig

            QTest.mouseClick(taskCard.editButton, Qt.MouseButton.LeftButton)

        self.assertEqual(task.config, updatedConfig)
        self.assertEqual(task.snapshot().target, str(self.workspace / "archive" / "renamed-video.mp4"))
        self.assertEqual(cast(str, getattr(task, "url")), "https://mirror.example.com/video.mp4")
        self.assertEqual(cast(str, getattr(task.stages[0], "resolvePath")), str(self.workspace / "archive" / "renamed-video.mp4"))

    def testHttpPackRecorderRestoresPersistedTask(self) -> None:
        service = self.createService()
        module = self.packModule(service)

        with patch.object(
            module,
            "_probeDownloadInfo",
            new=AsyncMock(
                return_value=(
                    512,
                    True,
                    "https://cdn.example.com/files/archive.zip",
                    {
                        "content-disposition": 'attachment; filename="archive.zip"',
                    },
                )
            ),
        ):
            task = asyncio.run(service.createTask(self.buildTaskInput(name="archive.zip")))

        stage = task.stages[0]
        cast(Any, stage).setStatus("running", emitSignals=False, notifyTask=False)
        cast(Any, stage).updateTransfer(
            doneBytes=256,
            speed=64,
            progress=50.0,
            notifyTask=False,
        )
        cast(Any, task).syncStatusFromStages()

        with patch(
            "app.feature_pack.internal.recorder.QStandardPaths.writableLocation",
            return_value=str(self.workspace),
        ):
            recorder = TaskRecorder()

        recorder.load()
        recorder.add(task, flush=True)
        restored = recorder.read()[task.id]

        self.assertEqual(type(restored).__name__, "HttpTask")
        self.assertEqual(restored.config.folder, self.workspace / "downloads")
        self.assertEqual(restored.config.name, "archive.zip")
        self.assertEqual(restored.config.headers, {"User-Agent": "Ghost Downloader"})
        self.assertEqual(restored.config.proxies, {"https": "http://127.0.0.1:7890"})
        self.assertEqual(restored.config.chunks, 8)
        self.assertEqual(restored.snapshot().target, str(self.workspace / "downloads" / "archive.zip"))
        self.assertEqual(restored.snapshot().state, "running")
        self.assertEqual(restored.snapshot().doneBytes, 256)
        self.assertEqual(restored.snapshot().totalBytes, 512)

        restoredStage = restored.stages[0]
        self.assertEqual(type(restoredStage).__name__, "HttpTaskStage")
        self.assertEqual(restoredStage.snapshot().state, "running")
        self.assertEqual(restoredStage.snapshot().doneBytes, 256)
        self.assertEqual(restoredStage.snapshot().speed, 64)
        self.assertEqual(cast(str, getattr(restoredStage, "resolvePath")), str(self.workspace / "downloads" / "archive.zip"))


if __name__ == "__main__":
    _ = unittest.main()
