# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportAny=false, reportExplicitAny=false, reportImplicitOverride=false, reportUnannotatedClassAttribute=false, reportUnusedCallResult=false, reportUnnecessaryCast=false

from __future__ import annotations

import asyncio
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from typing import Any
from typing import cast
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    _ = sys.path.insert(0, str(ROOT))

from app.feature_pack.api import DefaultFeatureService
from app.feature_pack.api import Task
from app.feature_pack.api import TaskConfig
from app.feature_pack.api import TaskInput
from app.feature_pack.api import TaskStage
from app.feature_pack.internal.recorder import TaskRecorder


class _FakeWindow:
    def __init__(self) -> None:
        self.installed: list[str] = []


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


class M3U8PackV1Tests(unittest.TestCase):
    _temporaryDirectory: tempfile.TemporaryDirectory[str] | None = None
    workspace: Path = ROOT

    def setUp(self) -> None:
        temporaryDirectory = tempfile.TemporaryDirectory()
        self._temporaryDirectory = temporaryDirectory
        self.addCleanup(temporaryDirectory.cleanup)
        self.workspace = Path(temporaryDirectory.name)
        for packName in ("http_pack", "extract_pack", "ffmpeg_pack", "m3u8_pack"):
            shutil.copytree(ROOT / "features" / packName, self.workspace / packName)
        self.resetPackRegistries()

    def resetPackRegistries(self) -> None:
        for key in (
            ("http_pack", "http_download", 1),
            ("extract_pack", "extract_archive", 1),
            ("ffmpeg_pack", "ffmpeg_install", 1),
            ("ffmpeg_pack", "ffmpeg_merge", 1),
            ("m3u8_pack", "m3u8_download", 1),
        ):
            Task.__recordRegistry__.pop(key, None)

        for key in (
            ("http_pack", "http_download", 1, "http_download", 1),
            ("extract_pack", "extract_archive", 1, "extract_archive", 1),
            ("ffmpeg_pack", "ffmpeg_install", 1, "http_download", 1),
            ("ffmpeg_pack", "ffmpeg_install", 1, "extract_archive", 1),
            ("ffmpeg_pack", "ffmpeg_merge", 1, "http_download", 1),
            ("ffmpeg_pack", "ffmpeg_merge", 1, "ffmpeg_merge", 1),
            ("m3u8_pack", "m3u8_download", 1, "m3u8_download", 1),
        ):
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

    def createService(self) -> DefaultFeatureService:
        service = DefaultFeatureService(featuresPath=self.workspace)
        service.loadPacks(_FakeWindow())
        return service

    def taskModule(self) -> ModuleType:
        import importlib

        return cast(ModuleType, importlib.import_module("_ghost_feature_pack_m3u8_pack.task"))

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
