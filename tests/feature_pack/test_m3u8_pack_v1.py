# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportAny=false, reportExplicitAny=false, reportImplicitOverride=false, reportUnannotatedClassAttribute=false, reportUnusedCallResult=false, reportUnnecessaryCast=false, reportMissingTypeStubs=false

from __future__ import annotations

import asyncio
import os
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import ModuleType
from typing import Any
from typing import cast
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
from PySide6.QtWidgets import QVBoxLayout
from PySide6.QtWidgets import QWidget
from qfluentwidgets import FluentIcon
from qfluentwidgets import SettingCard
from qfluentwidgets import SettingCardGroup

from app.feature_pack.api import DefaultFeatureService
from app.feature_pack.api import DefaultResultCard
from app.feature_pack.api import DefaultTaskCard
from app.feature_pack.api import SettingSection
from app.feature_pack.api import Task
from app.feature_pack.api import TaskConfig
from app.feature_pack.api import TaskInput
from app.feature_pack.api import TaskStage
from app.feature_pack.internal.recorder import TaskRecorder


class _FakeWindow:
    def __init__(self) -> None:
        self.installed: list[str] = []


class _FakeSettingPage:
    container: QWidget
    vBoxLayout: QVBoxLayout

    def __init__(self) -> None:
        self.container = QWidget()
        self.vBoxLayout = QVBoxLayout(self.container)


class _FakeManifestResponse:
    def __init__(
        self,
        *,
        url: str = "https://cdn.example.com/video/episode-01.m3u8",
        text: str = "#EXTM3U\n#EXT-X-TARGETDURATION:8\n#EXT-X-ENDLIST\n",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.url = url
        self.text = text
        self.headers = headers or {
            "content-type": "application/vnd.apple.mpegurl",
            "content-disposition": "attachment; filename*=UTF-8''episode-01.m3u8",
        }

    def raise_for_status(self) -> None:
        return None

    def close(self) -> None:
        return None


class _FakeManifestSession:
    def __init__(self, response: _FakeManifestResponse) -> None:
        self.response = response
        self.trust_env = False
        self.requests: list[dict[str, object]] = []

    async def get(self, url: str, **kwargs: object) -> _FakeManifestResponse:
        self.requests.append({"url": url, **kwargs})
        return self.response

    async def close(self) -> None:
        return None


def ensureApplication() -> QApplication:
    application = QApplication.instance()
    if application is not None:
        return cast(QApplication, application)

    return QApplication([])


class M3U8PackV1Tests(unittest.TestCase):
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
        for packName in ("http_pack", "extract_pack", "ffmpeg_pack", "m3u8_pack"):
            shutil.copytree(ROOT / "features" / packName, self.workspace / packName)
        self.resetPackRegistries()

    def resetPackRegistries(self) -> None:
        packIds = {"http_pack", "extract_pack", "ffmpeg_pack", "m3u8_pack"}
        for key in list(Task.__recordRegistry__):
            if key[0] in packIds:
                Task.__recordRegistry__.pop(key, None)

        for key in list(TaskStage.__recordRegistry__):
            if key[0] in packIds:
                TaskStage.__recordRegistry__.pop(key, None)

        for moduleName in list(sys.modules):
            if moduleName.startswith("_ghost_feature_pack_http_pack"):
                del sys.modules[moduleName]
            if moduleName.startswith("_ghost_feature_pack_extract_pack"):
                del sys.modules[moduleName]
            if moduleName.startswith("_ghost_feature_pack_ffmpeg_pack"):
                del sys.modules[moduleName]
            if moduleName.startswith("_ghost_feature_pack_m3u8_pack"):
                del sys.modules[moduleName]
            if moduleName.startswith("features.m3u8_pack"):
                del sys.modules[moduleName]
            if moduleName.startswith("m3u8_pack"):
                del sys.modules[moduleName]

    def createService(self) -> DefaultFeatureService:
        service = DefaultFeatureService(featuresPath=self.workspace)
        service.loadPacks(_FakeWindow())
        return service

    def taskModule(self) -> ModuleType:
        import importlib

        return cast(ModuleType, importlib.import_module("_ghost_feature_pack_m3u8_pack.task"))

    def configModule(self) -> ModuleType:
        import importlib

        return cast(ModuleType, importlib.import_module("_ghost_feature_pack_m3u8_pack.config"))

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

    def buildTaskInput(
        self,
        *,
        source: str = "https://cdn.example.com/video/episode-01.m3u8",
        name: str = "",
    ) -> TaskInput:
        return TaskInput(
            config=TaskConfig(
                source=source,
                folder=self.workspace / "downloads",
                name=name,
                headers={"Referer": "https://example.com/watch"},
                proxies={"https": "http://127.0.0.1:7890"},
                chunks=6,
            ),
        )

    def createM3U8Task(self) -> Task:
        service = self.createService()
        taskModule = self.taskModule()
        fakeSession = _FakeManifestSession(_FakeManifestResponse())

        with patch.object(
            taskModule.niquests,
            "AsyncSession",
            return_value=fakeSession,
        ):
            task = asyncio.run(service.createTask(self.buildTaskInput()))

        self.assertEqual(fakeSession.requests[0]["url"], "https://cdn.example.com/video/episode-01.m3u8")
        return task

    def createM3U8Archive(self, executableName: str) -> Path:
        archivePath = self.workspace / "N_m3u8DL-RE.zip"
        with zipfile.ZipFile(archivePath, "w") as archive:
            archive.writestr(f"N_m3u8DL-RE/{executableName}", b"m3u8-runtime")
        return archivePath

    def testM3U8PackRoutesBeforeGenericHttpAndCreatesSingleFileTask(self) -> None:
        service = self.createService()
        routedPack = service.packForSource("https://cdn.example.com/video/episode-01.m3u8")
        self.assertIsNotNone(routedPack)
        self.assertEqual(type(routedPack).__name__, "M3U8Pack")

        taskModule = self.taskModule()
        fakeSession = _FakeManifestSession(_FakeManifestResponse())
        with patch.object(taskModule.niquests, "AsyncSession", return_value=fakeSession):
            task = asyncio.run(service.createTask(self.buildTaskInput()))

        self.assertEqual(type(task).__name__, "M3U8Task")
        self.assertEqual(task.packId, "m3u8_pack")
        self.assertEqual(task.kind, "m3u8_download")
        self.assertEqual(task.config.name, "episode-01.mp4")
        self.assertEqual(task.config.folder, self.workspace / "downloads")
        self.assertEqual(task.config.chunks, 6)
        self.assertEqual(task.snapshot().target, str(self.workspace / "downloads" / "episode-01.mp4").replace("\\", "/"))
        self.assertEqual(cast(str, getattr(task, "manifestType")), "m3u8")
        self.assertFalse(cast(bool, getattr(task, "isLive")))

        stage = task.stages[0]
        self.assertEqual(type(stage).__name__, "M3U8TaskStage")
        self.assertEqual(stage.kind, "m3u8_download")
        self.assertEqual(cast(str, getattr(stage, "resolvePath")), str(self.workspace / "downloads" / "episode-01.mp4").replace("\\", "/"))
        self.assertIn(".gd3_m3u8", cast(str, getattr(stage, "tempDir")))

    def testM3U8TaskConfigureUsesTaskConfigAndSyncOutput(self) -> None:
        task = self.createM3U8Task()
        updatedConfig = TaskConfig(
            source="https://mirror.example.com/live/channel.mpd",
            folder=self.workspace / "archive",
            name="renamed-stream",
            headers={"User-Agent": "Ghost Downloader"},
            proxies={"https": "socks5://127.0.0.1:1080"},
            chunks=3,
        )

        task = cast(Any, task)
        task.configure(updatedConfig)

        self.assertEqual(task.config.source, "https://mirror.example.com/live/channel.mpd")
        self.assertEqual(task.config.name, "renamed-stream.mp4")
        self.assertEqual(task.threadCount, 3)
        self.assertEqual(task.headers, {"User-Agent": "Ghost Downloader"})
        self.assertEqual(task.proxies, {"https": "socks5://127.0.0.1:1080"})
        self.assertEqual(task.snapshot().target, str(self.workspace / "archive" / "renamed-stream.mp4").replace("\\", "/"))
        self.assertEqual(cast(str, getattr(task.stages[0], "resolvePath")), str(self.workspace / "archive" / "renamed-stream.mp4").replace("\\", "/"))
        self.assertIn(".gd3_m3u8", cast(str, getattr(task.stages[0], "tempDir")))

    def testM3U8TaskUsesDefaultEditFlowForConfig(self) -> None:
        service = self.createService()
        taskModule = self.taskModule()
        fakeSession = _FakeManifestSession(_FakeManifestResponse())
        with patch.object(taskModule.niquests, "AsyncSession", return_value=fakeSession):
            task = asyncio.run(service.createTask(self.buildTaskInput()))
        taskCard = cast(DefaultTaskCard, service.createTaskCard(task, self.createParent()))
        resultCard = service.createResultCard(task, self.createParent())
        self.showWidget(taskCard)
        self.showWidget(cast(QWidget, resultCard))

        self.assertIsInstance(taskCard, DefaultTaskCard)
        self.assertIsInstance(resultCard, DefaultResultCard)

        updatedConfig = TaskConfig(
            source="https://mirror.example.com/video/edited.m3u8",
            folder=self.workspace / "archive",
            name="edited-stream",
            headers={"Referer": "https://mirror.example.com/watch"},
            proxies={"https": "socks5://127.0.0.1:1080"},
            chunks=2,
        )

        with patch("app.feature_pack.api.service.TaskConfigDialog") as dialogMock:
            dialog = dialogMock.return_value
            dialog.exec.return_value = QDialog.DialogCode.Accepted
            dialog.config.return_value = updatedConfig

            QTest.mouseClick(taskCard.editButton, Qt.MouseButton.LeftButton)

        dialogMock.assert_called_once()
        self.assertIs(dialogMock.call_args.kwargs["task"], task)
        self.assertEqual(dialogMock.call_args.kwargs["mode"], "running")
        self.assertEqual(task.config.name, "edited-stream.mp4")
        self.assertEqual(task.config.folder, self.workspace / "archive")
        self.assertEqual(cast(str, getattr(task.stages[0], "resolvePath")), str(self.workspace / "archive" / "edited-stream.mp4").replace("\\", "/"))

        resultConfig = TaskConfig(
            source=task.config.source,
            folder=self.workspace / "result-archive",
            name="result-edited-stream",
            headers=task.config.headers,
            proxies=task.config.proxies,
            chunks=4,
        )

        resultCard = cast(DefaultResultCard, resultCard)
        with patch("app.feature_pack.api.service.TaskConfigDialog") as dialogMock:
            dialog = dialogMock.return_value
            dialog.exec.return_value = QDialog.DialogCode.Accepted
            dialog.config.return_value = resultConfig

            QTest.mouseClick(resultCard.editButton, Qt.MouseButton.LeftButton)

        dialogMock.assert_called_once()
        self.assertIs(dialogMock.call_args.kwargs["task"], task)
        self.assertEqual(dialogMock.call_args.kwargs["mode"], "before")
        self.assertEqual(task.config.name, "result-edited-stream.mp4")
        self.assertEqual(task.snapshot().target, str(self.workspace / "result-archive" / "result-edited-stream.mp4").replace("\\", "/"))

    def testM3U8PackCreatesInstallTaskFromTaskInput(self) -> None:
        service = self.createService()
        routedPack = service.packForSource("gd3+m3u8://install")
        self.assertIsNotNone(routedPack)
        self.assertEqual(type(routedPack).__name__, "M3U8Pack")

        installFolder = self.workspace / "Runtime"
        mockAsset = {
            "name": "N_m3u8DL-RE_Beta_win-x64_20241203.zip",
            "url": "https://downloads.example.com/N_m3u8DL-RE.zip",
            "size": 2048,
        }
        with patch(
            "_ghost_feature_pack_m3u8_pack.task._requestReleaseAsset",
            new=AsyncMock(return_value=mockAsset),
        ), patch(
            "_ghost_feature_pack_m3u8_pack.task._detectRuntimeTarget",
            return_value=("win-x64", "Windows x64"),
        ):
            task = asyncio.run(
                service.createTask(
                    TaskInput(
                        config=TaskConfig(
                            source="gd3+m3u8://install",
                            folder=installFolder,
                            name="ignored.zip",
                            proxies={"https": "http://127.0.0.1:7890"},
                            chunks=5,
                        )
                    )
                )
            )

        self.assertEqual(type(task).__name__, "M3U8InstallTask")
        self.assertEqual(task.packId, "m3u8_pack")
        self.assertEqual(task.kind, "m3u8_install")
        self.assertEqual(task.snapshot().name, "N_m3u8DL-RE 安装 (Windows x64)")
        self.assertEqual(task.snapshot().target, str(installFolder).replace("\\", "/"))
        self.assertEqual(task.snapshot().totalBytes, 2048)
        self.assertEqual(task.config.source, "https://downloads.example.com/N_m3u8DL-RE.zip")
        self.assertEqual(task.config.name, "N_m3u8DL-RE_Beta_win-x64_20241203.zip")
        self.assertEqual(task.config.chunks, 5)

        stages = list(task.stages)
        self.assertEqual([type(stage).__name__ for stage in stages], ["M3U8InstallDownloadStage", "M3U8InstallExtractStage"])
        self.assertEqual([(stage.kind, stage.version) for stage in stages], [("http_download", 1), ("extract_archive", 1)])
        self.assertEqual(cast(str, getattr(stages[0], "resolvePath")), str(installFolder / "N_m3u8DL-RE_Beta_win-x64_20241203.zip").replace("\\", "/"))
        self.assertEqual(cast(str, getattr(stages[1], "installFolder")), str(installFolder).replace("\\", "/"))

        taskCard = cast(DefaultTaskCard, service.createTaskCard(task, self.createParent()))
        self.showWidget(taskCard)
        self.assertIsInstance(taskCard, DefaultTaskCard)

        updatedConfig = TaskConfig(
            source=task.config.source,
            folder=self.workspace / "EditedRuntime",
            name=task.config.name,
            headers=task.config.headers,
            proxies=task.config.proxies,
            chunks=3,
        )
        with patch("app.feature_pack.api.service.TaskConfigDialog") as dialogMock:
            dialog = dialogMock.return_value
            dialog.exec.return_value = QDialog.DialogCode.Accepted
            dialog.config.return_value = updatedConfig

            QTest.mouseClick(taskCard.editButton, Qt.MouseButton.LeftButton)

        self.assertEqual(task.config.folder, self.workspace / "EditedRuntime")
        self.assertEqual(task.config.chunks, 3)
        self.assertEqual(cast(str, getattr(task.stages[0], "resolvePath")), str(self.workspace / "EditedRuntime" / "N_m3u8DL-RE_Beta_win-x64_20241203.zip").replace("\\", "/"))
        self.assertEqual(cast(str, getattr(task.stages[1], "installFolder")), str(self.workspace / "EditedRuntime").replace("\\", "/"))

    def testM3U8InstallTaskRunsAndRecorderRestores(self) -> None:
        service = self.createService()
        taskModule = self.taskModule()
        executableName = cast(str, taskModule._executableName("N_m3u8DL-RE"))
        archivePath = self.createM3U8Archive(executableName)
        installFolder = self.workspace / "Runtime"
        mockAsset = {
            "name": archivePath.name,
            "url": "https://downloads.example.com/N_m3u8DL-RE.zip",
            "size": archivePath.stat().st_size,
        }

        with patch(
            "_ghost_feature_pack_m3u8_pack.task._requestReleaseAsset",
            new=AsyncMock(return_value=mockAsset),
        ), patch(
            "_ghost_feature_pack_m3u8_pack.task._detectRuntimeTarget",
            return_value=("win-x64", "Windows x64"),
        ):
            task = asyncio.run(
                service.createTask(
                    TaskInput(
                        config=TaskConfig(
                            source="gd3+m3u8://install",
                            folder=installFolder,
                            name="ignored.zip",
                        )
                    )
                )
            )

        class FakeHttpWorker:
            def __init__(self, stage: object) -> None:
                self.stage = stage

            async def run(self) -> None:
                target = Path(cast(str, getattr(self.stage, "resolvePath")))
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(archivePath, target)
                getattr(self.stage, "updateTransfer")(
                    doneBytes=archivePath.stat().st_size,
                    speed=0,
                    progress=100.0,
                )
                getattr(self.stage, "setStatus")("completed")

        with patch.object(taskModule, "HttpWorker", FakeHttpWorker):
            asyncio.run(cast(Any, task).run())

        executablePath = installFolder / executableName
        self.assertTrue(executablePath.is_file())
        self.assertFalse((installFolder / archivePath.name).exists())
        self.assertEqual(task.snapshot().state, "completed")
        self.assertEqual(task.snapshot().progress, 100.0)
        self.assertEqual(cast(str, getattr(task, "executablePath")), str(executablePath).replace("\\", "/"))

        recorder = TaskRecorder(recordFile=self.workspace / "FeaturePackMemory.log")
        recorder.load()
        recorder.add(task, flush=True)
        record = recorder.serializeTask(task)
        restored = recorder.read()[task.id]

        self.assertEqual(record["packId"], "m3u8_pack")
        self.assertEqual(record["kind"], "m3u8_install")
        self.assertEqual(record["version"], 1)
        self.assertNotIn("type", record)
        stages = cast(list[dict[str, object]], record["stages"])
        self.assertEqual(
            [(cast(str, stage["kind"]), cast(int, stage["version"])) for stage in stages],
            [("http_download", 1), ("extract_archive", 1)],
        )
        self.assertEqual(type(restored).__name__, "M3U8InstallTask")
        self.assertEqual(restored.snapshot().state, "completed")
        self.assertEqual(restored.snapshot().target, str(installFolder).replace("\\", "/"))
        self.assertEqual(cast(str, getattr(restored, "executablePath")), str(executablePath).replace("\\", "/"))
        self.assertEqual([type(stage).__name__ for stage in restored.stages], ["M3U8InstallDownloadStage", "M3U8InstallExtractStage"])

    def testM3U8PackInstallsSettingsThroughSettingSection(self) -> None:
        service = self.createService()
        pack = service.pack("m3u8_pack")
        self.assertIsNotNone(pack)
        if pack is None:
            raise AssertionError("m3u8_pack should load through the V1 service")

        section = pack.settingSection()
        self.assertIsInstance(section, SettingSection)
        section = cast(SettingSection, section)
        self.assertEqual(section.id, "m3u8_pack")
        self.assertEqual(section.title, "流媒体下载")
        self.assertEqual(
            [(item.key, item.kind) for item in section.items[:4]],
            [
                ("installFolder", "custom"),
                ("runtime", "custom"),
                ("outputFormat", "custom"),
                ("threadCount", "custom"),
            ],
        )

        configModule = self.configModule()
        config = cast(Any, configModule.m3u8Config)
        settingPage = _FakeSettingPage()
        self.showWidget(settingPage.container)

        def createRuntimeCard(group: SettingCardGroup) -> SettingCard:
            card = SettingCard(FluentIcon.INFO, "当前 N_m3u8DL-RE", "测试运行时卡片", group)
            config.runtimeCard = card
            return card

        with patch.object(config, "_createRuntimeCard", side_effect=createRuntimeCard):
            service.installSettings(settingPage)

        self.assertGreaterEqual(settingPage.vBoxLayout.count(), 1)
        group = cast(
            SettingCardGroup,
            settingPage.container.findChild(SettingCardGroup, "featurePackSection:m3u8_pack"),
        )
        self.assertIsInstance(group, SettingCardGroup)
        self.assertEqual(group.titleLabel.text(), "流媒体下载")

        cards = {
            key: cast(SettingCard, group.findChild(SettingCard, f"settingCard:{key}"))
            for key in ("installFolder", "runtime", "outputFormat", "threadCount")
        }
        for key, card in cards.items():
            self.assertIsInstance(card, SettingCard, key)

        self.assertIs(cards["installFolder"], config.installFolderCard)
        self.assertIs(cards["runtime"], config.runtimeCard)
        self.assertIs(cards["outputFormat"], config.outputFormatCard)
        self.assertIs(cards["threadCount"], config.threadCountCard)

    def testM3U8TaskRunsThroughDownloadStageAndRecorderRestores(self) -> None:
        task = self.createM3U8Task()
        taskModule = self.taskModule()

        class FakeM3U8Worker:
            def __init__(self, stage: object) -> None:
                self.stage = stage

            async def run(self) -> None:
                owner = cast(Any, getattr(self.stage, "_task"))
                outputPath = Path(cast(str, getattr(self.stage, "resolvePath")))
                outputPath.parent.mkdir(parents=True, exist_ok=True)
                outputPath.write_bytes(b"stream-data")
                getattr(self.stage, "updateTransfer")(doneBytes=11, speed=0, progress=100.0)
                owner.fileSize = 11
                getattr(self.stage, "setStatus")("completed")

        with patch.object(taskModule, "M3U8Worker", FakeM3U8Worker):
            asyncio.run(cast(Any, task).run())

        finalPath = self.workspace / "downloads" / "episode-01.mp4"
        self.assertTrue(finalPath.is_file())
        self.assertEqual(task.snapshot().state, "completed")
        self.assertEqual(task.snapshot().progress, 100.0)
        self.assertEqual(task.snapshot().totalBytes, 11)

        recorder = TaskRecorder(recordFile=self.workspace / "FeaturePackMemory.log")
        recorder.load()
        recorder.add(task, flush=True)
        record = recorder.serializeTask(task)
        restored = recorder.read()[task.id]

        self.assertEqual(record["packId"], "m3u8_pack")
        self.assertEqual(record["kind"], "m3u8_download")
        self.assertEqual(record["version"], 1)
        self.assertNotIn("type", record)
        self.assertEqual(cast(list[dict[str, object]], record["stages"])[0]["kind"], "m3u8_download")
        self.assertEqual(type(restored).__name__, "M3U8Task")
        self.assertEqual(restored.config.name, "episode-01.mp4")
        self.assertEqual(restored.snapshot().state, "completed")
        self.assertEqual(restored.snapshot().target, str(finalPath).replace("\\", "/"))


if __name__ == "__main__":
    _ = unittest.main()
