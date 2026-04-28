# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportAny=false, reportExplicitAny=false, reportImplicitOverride=false, reportAttributeAccessIssue=false, reportCallIssue=false, reportUnusedCallResult=false, reportUnnecessaryCast=false, reportUnannotatedClassAttribute=false

from __future__ import annotations

import asyncio
import importlib
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from typing import Any
from typing import cast
from urllib.parse import parse_qs
from urllib.parse import urlparse
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
from app.feature_pack.internal import buildBrowserTaskSummary
from app.feature_pack.internal.recorder import TaskRecorder


class _FakeWindow:
    def __init__(self) -> None:
        self.installed: list[str] = []


class _FakeResponse:
    def __init__(
        self,
        payload: dict[str, object],
        *,
        statusCode: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        self._payload = payload
        self.status_code = statusCode
        self.headers = headers or {}
        self.url = "https://example.test/response"

    def json(self) -> dict[str, object]:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def close(self) -> None:
        return None


class _FakeAsyncSession:
    trust_env: bool

    def __init__(self, *args: object, **kwargs: object) -> None:
        _ = args
        _ = kwargs
        self.trust_env = False

    async def get(self, url: str, *args: object, **kwargs: object) -> _FakeResponse:
        _ = args
        _ = kwargs
        if "x/web-interface/view" in url:
            return _FakeResponse(
                {
                    "code": 0,
                    "data": {
                        "title": "Sample Video",
                        "pages": [
                            {"cid": 101, "page": 1, "part": "Intro"},
                            {"cid": 102, "page": 2, "part": "Middle"},
                            {"cid": 103, "page": 3, "part": "End"},
                        ],
                    },
                }
            )

        if "x/player/wbi/playurl" in url:
            query = parse_qs(urlparse(url).query)
            cid = int(query["cid"][0])
            return _FakeResponse(
                {
                    "code": 0,
                    "data": {
                        "dash": {
                            "video": [
                                {
                                    "id": 64,
                                    "baseUrl": f"https://media.example.test/video-{cid}.m4s",
                                }
                            ],
                            "audio": [
                                {
                                    "id": 30280,
                                    "baseUrl": f"https://media.example.test/audio-{cid}.m4s",
                                }
                            ],
                        },
                        "accept_quality": [64],
                    },
                }
            )

        raise AssertionError(f"Unexpected fake Bilibili request: {url}")

    async def close(self) -> None:
        return None


async def _fakeFileSize(
    url: str,
    headers: dict[str, str],
    proxies: dict[str, str] | None,
    client: object,
) -> int:
    _ = headers
    _ = proxies
    _ = client
    sizes = {
        "https://media.example.test/video-101.m4s": 100,
        "https://media.example.test/audio-101.m4s": 10,
        "https://media.example.test/video-102.m4s": 200,
        "https://media.example.test/audio-102.m4s": 20,
        "https://media.example.test/video-103.m4s": 300,
        "https://media.example.test/audio-103.m4s": 30,
    }
    return sizes[url]


def ensureApplication() -> QApplication:
    application = QApplication.instance()
    if application is not None:
        return cast(QApplication, application)

    return QApplication([])


class BiliPackV1Tests(unittest.TestCase):
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
        for packId in ("http_pack", "extract_pack", "ffmpeg_pack", "bili_pack"):
            shutil.copytree(ROOT / "features" / packId, self.workspace / packId)
        self.resetBiliPackRegistries()

    def resetBiliPackRegistries(self) -> None:
        packIds = {"http_pack", "extract_pack", "ffmpeg_pack", "bili_pack"}
        for key in list(Task.__recordRegistry__):
            if key[0] in packIds:
                Task.__recordRegistry__.pop(key, None)
        for key in list(TaskStage.__recordRegistry__):
            if key[0] in packIds:
                TaskStage.__recordRegistry__.pop(key, None)
        for moduleName in list(sys.modules):
            if moduleName.startswith("_ghost_feature_pack_bili_pack"):
                del sys.modules[moduleName]
            if moduleName.startswith("_ghost_feature_pack_extract_pack"):
                del sys.modules[moduleName]
            if moduleName.startswith("_ghost_feature_pack_ffmpeg_pack"):
                del sys.modules[moduleName]
            if moduleName.startswith("_ghost_feature_pack_http_pack"):
                del sys.modules[moduleName]
            if moduleName.startswith("features.bili_pack"):
                del sys.modules[moduleName]
            if moduleName.startswith("bili_pack"):
                del sys.modules[moduleName]

    def createService(self) -> DefaultFeatureService:
        service = DefaultFeatureService(featuresPath=self.workspace)
        service.loadPacks(_FakeWindow())
        return service

    def packModule(self) -> ModuleType:
        return cast(ModuleType, importlib.import_module("_ghost_feature_pack_bili_pack"))

    def buildTaskInput(
        self,
        *,
        source: str = "https://www.bilibili.com/video/BV1xx411c7mD",
        name: str = "",
    ) -> TaskInput:
        return TaskInput(
            config=TaskConfig(
                source=source,
                folder=self.workspace / "downloads",
                name=name,
                proxies={"http": "http://127.0.0.1:7890"},
                chunks=8,
            ),
        )

    def createBiliTask(self, *, source: str | None = None) -> Task:
        service = self.createService()
        packModule = self.packModule()
        with patch.object(packModule.niquests, "AsyncSession", _FakeAsyncSession):
            with patch.object(packModule, "_getFileSizeWithClient", _fakeFileSize):
                return asyncio.run(
                    service.createTask(
                        self.buildTaskInput(source=source or "https://www.bilibili.com/video/BV1xx411c7mD")
                    )
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

    def testBiliPackCreatesMultiFileTaskWithEpisodeSelection(self) -> None:
        service = self.createService()
        packModule = self.packModule()

        with patch.object(packModule.niquests, "AsyncSession", _FakeAsyncSession):
            with patch.object(packModule, "_getFileSizeWithClient", _fakeFileSize):
                routedPack = service.packForSource("https://www.bilibili.com/video/BV1xx411c7mD?p=2")
                task = asyncio.run(
                    service.createTask(
                        self.buildTaskInput(source="https://www.bilibili.com/video/BV1xx411c7mD?p=2")
                    )
                )

        self.assertIsNotNone(routedPack)
        if routedPack is None:
            raise AssertionError("bili_pack should route Bilibili video URLs")
        self.assertEqual(routedPack.manifest.id, "bili_pack")
        self.assertIsInstance(task, MultiFileTask)
        self.assertEqual(type(task).__name__, "BilibiliTask")
        self.assertEqual(task.packId, "bili_pack")
        self.assertEqual(task.kind, "bilibili_download")
        self.assertEqual(task.config.name, "Sample Video")
        self.assertEqual(task.fileCount, 3)
        self.assertEqual(task.selectedIds, {"page-2"})
        self.assertEqual(cast(Any, task).selectedPages, [2])
        self.assertEqual(task.snapshot().target, str(self.workspace / "downloads" / "Sample Video"))
        self.assertEqual(task.snapshot().totalBytes, 220)
        self.assertEqual(
            [(file.id, file.path, file.size, file.selected, file.note) for file in task.files],
            [
                ("page-1", "Sample Video - P1 Intro.mp4", 110, False, "P1 · Intro"),
                ("page-2", "Sample Video - P2 Middle.mp4", 220, True, "P2 · Middle"),
                ("page-3", "Sample Video - P3 End.mp4", 330, False, "P3 · End"),
            ],
        )
        self.assertEqual(len(task.stages), 9)
        self.assertEqual([type(stage).__name__ for stage in task.stages[3:6]], [
            "BilibiliDownloadStage",
            "BilibiliDownloadStage",
            "BilibiliMergeStage",
        ])
        self.assertTrue(str(getattr(task.stages[3], "resolvePath")).endswith("Sample Video - P2 Middle.video.m4s"))
        self.assertTrue(str(getattr(task.stages[4], "resolvePath")).endswith("Sample Video - P2 Middle.audio.m4s"))
        self.assertTrue(str(getattr(task.stages[5], "resolvePath")).endswith("Sample Video - P2 Middle.mp4"))

        packForTask = service.packForTask(task)
        self.assertIsNotNone(packForTask)
        if packForTask is None:
            raise AssertionError("Bilibili task should route back to Bilibili Pack")
        self.assertEqual(packForTask.manifest.id, "bili_pack")

    def testBiliTaskUsesDefaultEditFlowForEpisodeSelectionAndConfig(self) -> None:
        service = self.createService()
        packModule = self.packModule()
        with patch.object(packModule.niquests, "AsyncSession", _FakeAsyncSession):
            with patch.object(packModule, "_getFileSizeWithClient", _fakeFileSize):
                task = asyncio.run(service.createTask(self.buildTaskInput()))

        taskCard = cast(DefaultTaskCard, service.createTaskCard(task, self.createParent()))
        resultCard = service.createResultCard(task, self.createParent())
        self.showWidget(taskCard)
        self.showWidget(cast(QWidget, resultCard))

        self.assertIsInstance(taskCard, DefaultTaskCard)
        self.assertIsInstance(resultCard, DefaultResultCard)
        self.assertEqual(taskCard.nameLabel.text(), "Sample Video")

        updatedConfig = TaskConfig(
            source=task.config.source,
            folder=self.workspace / "archive",
            name="Renamed Video",
            headers=task.config.headers,
            proxies={"https": "socks5://127.0.0.1:1080"},
            chunks=16,
        )

        with patch("app.feature_pack.api.service.TaskConfigDialog") as dialogMock:
            dialog = dialogMock.return_value
            dialog.exec.return_value = QDialog.DialogCode.Accepted
            dialog.selectedIds.return_value = {"page-1", "page-3"}
            dialog.config.return_value = updatedConfig

            QTest.mouseClick(taskCard.editButton, Qt.MouseButton.LeftButton)

        self.assertEqual(task.selectedIds, {"page-1", "page-3"})
        self.assertEqual(task.selectedCount, 2)
        self.assertEqual(task.config, updatedConfig)
        self.assertEqual(task.snapshot().totalBytes, 440)
        self.assertEqual(task.snapshot().target, str(self.workspace / "archive" / "Renamed Video"))
        self.assertTrue(str(getattr(task.stages[0], "resolvePath")).endswith("Renamed Video - P1 Intro.video.m4s"))
        self.assertTrue(str(getattr(task.stages[8], "resolvePath")).endswith("Renamed Video - P3 End.mp4"))
        self.assertEqual(cast(Any, task.stages[0]).proxies, {"https": "socks5://127.0.0.1:1080"})
        self.assertEqual(cast(Any, task.stages[0]).blockNum, 16)

    def testBiliTaskRecorderRestoresEpisodesAndBrowserProjection(self) -> None:
        task = self.createBiliTask()
        task = cast(Any, task)
        task.select({"page-3"})
        videoStage = task.stages[6]
        getattr(videoStage, "setStatus")("running", emitSignals=False, notifyTask=False)
        getattr(videoStage, "updateTransfer")(
            doneBytes=150,
            speed=25,
            progress=50.0,
            notifyTask=False,
        )
        task.syncStatusFromStages()

        recorder = TaskRecorder(recordFile=self.workspace / "FeaturePackMemory.log")
        recorder.load()
        recorder.add(cast(Task, task), flush=True)
        record = recorder.serializeTask(cast(Task, task))
        restored = recorder.read()[task.id]

        self.assertEqual(record["packId"], "bili_pack")
        self.assertEqual(record["kind"], "bilibili_download")
        self.assertEqual(record["version"], 1)
        self.assertNotIn("type", record)
        self.assertEqual(type(restored).__name__, "BilibiliTask")
        self.assertIsInstance(restored, MultiFileTask)
        self.assertEqual(restored.selectedIds, {"page-3"})
        self.assertEqual(restored.fileCount, 3)
        self.assertEqual(restored.snapshot().state, "running")
        self.assertEqual(restored.snapshot().doneBytes, 150)
        self.assertEqual(restored.snapshot().totalBytes, 330)
        self.assertEqual(
            [(file.id, file.path, file.selected, file.doneBytes) for file in restored.files],
            [
                ("page-1", "Sample Video - P1 Intro.mp4", False, 0),
                ("page-2", "Sample Video - P2 Middle.mp4", False, 0),
                ("page-3", "Sample Video - P3 End.mp4", True, 150),
            ],
        )

        summary = buildBrowserTaskSummary(restored)
        self.assertEqual(summary.id, restored.id)
        self.assertEqual(summary.packId, "bili_pack")
        self.assertEqual(summary.kind, "bilibili_download")
        self.assertEqual(summary.name, "Sample Video")
        self.assertEqual(summary.state, "running")
        self.assertEqual(summary.target, str(self.workspace / "downloads" / "Sample Video"))
        self.assertEqual(summary.folder, str(self.workspace / "downloads"))
        self.assertEqual(summary.totalBytes, 330)
        self.assertEqual(summary.speed, 25)


if __name__ == "__main__":
    _ = unittest.main()
