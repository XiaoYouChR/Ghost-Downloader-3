# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportAny=false, reportImplicitOverride=false

from __future__ import annotations

import asyncio
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from typing import Any
from typing import cast
from unittest.mock import AsyncMock
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


class FFmpegInstallPackV1Tests(unittest.TestCase):
    _temporaryDirectory: tempfile.TemporaryDirectory[str] | None = None
    workspace: Path = ROOT

    def setUp(self) -> None:
        temporaryDirectory = tempfile.TemporaryDirectory()
        self._temporaryDirectory = temporaryDirectory
        self.addCleanup(temporaryDirectory.cleanup)
        self.workspace = Path(temporaryDirectory.name)
        for packName in ("http_pack", "extract_pack", "ffmpeg_pack"):
            shutil.copytree(ROOT / "features" / packName, self.workspace / packName)
        self.resetPackRegistries()

    def resetPackRegistries(self) -> None:
        Task.__recordRegistry__.pop(("http_pack", "http_download", 1), None)
        Task.__recordRegistry__.pop(("extract_pack", "extract_archive", 1), None)
        Task.__recordRegistry__.pop(("ffmpeg_pack", "ffmpeg_install", 1), None)
        TaskStage.__recordRegistry__.pop(("http_pack", "http_download", 1, "http_download", 1), None)
        TaskStage.__recordRegistry__.pop(("extract_pack", "extract_archive", 1, "extract_archive", 1), None)
        TaskStage.__recordRegistry__.pop(("ffmpeg_pack", "ffmpeg_install", 1, "http_download", 1), None)
        TaskStage.__recordRegistry__.pop(("ffmpeg_pack", "ffmpeg_install", 1, "extract_archive", 1), None)
        for moduleName in list(sys.modules):
            if moduleName.startswith("_ghost_feature_pack_http_pack"):
                del sys.modules[moduleName]
            if moduleName.startswith("_ghost_feature_pack_extract_pack"):
                del sys.modules[moduleName]
            if moduleName.startswith("_ghost_feature_pack_ffmpeg_pack"):
                del sys.modules[moduleName]

    def createService(self) -> DefaultFeatureService:
        service = DefaultFeatureService(featuresPath=self.workspace)
        service.loadPacks(_FakeWindow())
        return service

    def createFfmpegArchive(self, archiveName: str = "ffmpeg.zip") -> Path:
        archivePath = self.workspace / archiveName
        with zipfile.ZipFile(archivePath, "w") as archive:
            archive.writestr("ffmpeg-runtime/bin/ffmpeg.exe", b"ffmpeg-binary")
            archive.writestr("ffmpeg-runtime/bin/ffprobe.exe", b"ffprobe-binary")
        return archivePath

    def testFfmpegPackCreatesInstallTaskFromTaskInput(self) -> None:
        service = self.createService()
        pack = service.pack("ffmpeg_pack")
        self.assertIsNotNone(pack)
        if pack is None:
            raise AssertionError("ffmpeg_pack 未加载")

        installFolder = self.workspace / "Runtime"
        mockAsset = {
            "name": "ffmpeg-master-latest-win64-gpl.zip",
            "url": "https://downloads.example.com/ffmpeg.zip",
            "size": 4096,
        }
        with patch(
            "_ghost_feature_pack_ffmpeg_pack.install_task._requestLatestReleaseAsset",
            new=AsyncMock(return_value=mockAsset),
        ), patch(
            "_ghost_feature_pack_ffmpeg_pack.install_task._detectWindowsTarget",
            return_value=("win64", "x64"),
        ):
            task = asyncio.run(
                pack.createTask(
                    TaskInput(
                        config=TaskConfig(
                            source="gd3+ffmpeg://install",
                            folder=installFolder,
                            name="ignored.zip",
                        )
                    )
                )
            )

        self.assertIsNotNone(task)
        if task is None:
            raise AssertionError("ffmpeg_pack 未创建安装任务")

        self.assertEqual(type(task).__name__, "FFmpegInstallTask")
        self.assertEqual(task.packId, "ffmpeg_pack")
        self.assertEqual(task.kind, "ffmpeg_install")
        self.assertEqual(task.snapshot().name, "FFmpeg 安装 (x64)")
        self.assertEqual(task.snapshot().target, str(installFolder).replace("\\", "/"))
        self.assertEqual(task.snapshot().totalBytes, 4096)
        self.assertEqual(task.config.source, "https://downloads.example.com/ffmpeg.zip")
        self.assertEqual(task.config.name, "ffmpeg-master-latest-win64-gpl.zip")

        stages = list(task.stages)
        self.assertEqual([type(stage).__name__ for stage in stages], ["FFmpegInstallDownloadStage", "FFmpegInstallExtractStage"])
        self.assertEqual(cast(str, getattr(stages[0], "resolvePath")), str(installFolder / "ffmpeg-master-latest-win64-gpl.zip").replace("\\", "/"))
        self.assertEqual(cast(str, getattr(stages[1], "installFolder")), str(installFolder).replace("\\", "/"))

    def testFfmpegInstallTaskRunsAndRecorderRestores(self) -> None:
        service = self.createService()
        pack = service.pack("ffmpeg_pack")
        self.assertIsNotNone(pack)
        if pack is None:
            raise AssertionError("ffmpeg_pack 未加载")

        installFolder = self.workspace / "Runtime"
        archivePath = self.createFfmpegArchive()
        mockAsset = {
            "name": archivePath.name,
            "url": "https://downloads.example.com/ffmpeg.zip",
            "size": archivePath.stat().st_size,
        }
        with patch(
            "_ghost_feature_pack_ffmpeg_pack.install_task._requestLatestReleaseAsset",
            new=AsyncMock(return_value=mockAsset),
        ), patch(
            "_ghost_feature_pack_ffmpeg_pack.install_task._detectWindowsTarget",
            return_value=("win64", "x64"),
        ):
            task = asyncio.run(
                pack.createTask(
                    TaskInput(
                        config=TaskConfig(
                            source="gd3+ffmpeg://install",
                            folder=installFolder,
                            name="ignored.zip",
                        )
                    )
                )
            )

        self.assertIsNotNone(task)
        if task is None:
            raise AssertionError("ffmpeg_pack 未创建安装任务")

        task = cast(Any, task)
        task.config = TaskConfig(
            source="https://downloads.example.com/ffmpeg.zip",
            folder=installFolder,
            name=archivePath.name,
            headers=task.config.headers,
            proxies=task.config.proxies,
            chunks=task.config.chunks,
        )
        task.archiveSize = archivePath.stat().st_size
        task.syncOutput()

        downloadStage = task.stages[0]
        extractStage = task.stages[1]
        cast(Any, downloadStage).setStatus("completed", emitSignals=False, notifyTask=False)
        cast(Any, downloadStage).doneBytes = archivePath.stat().st_size
        cast(Any, downloadStage).progress = 100.0
        cast(Any, downloadStage).resolvePath = str(archivePath).replace("\\", "/")
        cast(Any, extractStage).archivePath = str(archivePath).replace("\\", "/")
        cast(Any, extractStage).installFolder = str(installFolder).replace("\\", "/")

        with patch.object(task, "downloadStage", return_value=downloadStage):
            asyncio.run(task.run())

        ffmpegPath = installFolder / "bin" / "ffmpeg.exe"
        ffprobePath = installFolder / "bin" / "ffprobe.exe"
        self.assertTrue(ffmpegPath.is_file())
        self.assertTrue(ffprobePath.is_file())
        self.assertFalse(archivePath.exists())
        self.assertEqual(task.snapshot().state, "completed")
        self.assertEqual(task.snapshot().progress, 100.0)
        self.assertEqual(task.ffmpegPath, str(ffmpegPath).replace("\\", "/"))
        self.assertEqual(task.ffprobePath, str(ffprobePath).replace("\\", "/"))

        with patch(
            "app.feature_pack.internal.recorder.QStandardPaths.writableLocation",
            return_value=str(self.workspace),
        ):
            recorder = TaskRecorder()

        recorder.load()
        recorder.add(task, flush=True)
        restored = recorder.read()[task.id]

        self.assertEqual(type(restored).__name__, "FFmpegInstallTask")
        self.assertEqual(restored.snapshot().state, "completed")
        self.assertEqual(restored.snapshot().target, str(installFolder).replace("\\", "/"))
        self.assertEqual(cast(str, getattr(restored, "ffmpegPath")), str(ffmpegPath).replace("\\", "/"))
        self.assertEqual(cast(str, getattr(restored, "ffprobePath")), str(ffprobePath).replace("\\", "/"))
        self.assertEqual([type(stage).__name__ for stage in restored.stages], ["FFmpegInstallDownloadStage", "FFmpegInstallExtractStage"])

    def testFfmpegInstallTaskUsesStableTaskAndStageIdentity(self) -> None:
        service = self.createService()
        pack = service.pack("ffmpeg_pack")
        self.assertIsNotNone(pack)
        if pack is None:
            raise AssertionError("ffmpeg_pack 未加载")

        installFolder = self.workspace / "Runtime"
        mockAsset = {
            "name": "ffmpeg-master-latest-win64-gpl.zip",
            "url": "https://downloads.example.com/ffmpeg.zip",
            "size": 1234,
        }
        with patch(
            "_ghost_feature_pack_ffmpeg_pack.install_task._requestLatestReleaseAsset",
            new=AsyncMock(return_value=mockAsset),
        ), patch(
            "_ghost_feature_pack_ffmpeg_pack.install_task._detectWindowsTarget",
            return_value=("win64", "x64"),
        ):
            task = asyncio.run(
                pack.createTask(
                    TaskInput(
                        config=TaskConfig(
                            source="gd3+ffmpeg://install",
                            folder=installFolder,
                            name="ignored.zip",
                        )
                    )
                )
            )

        self.assertIsNotNone(task)
        if task is None:
            raise AssertionError("ffmpeg_pack 未创建安装任务")

        recorder = TaskRecorder(recordFile=self.workspace / "FeaturePackMemory.log")
        record = recorder.serializeTask(cast(Task, task))

        self.assertEqual(record["packId"], "ffmpeg_pack")
        self.assertEqual(record["kind"], "ffmpeg_install")
        self.assertEqual(record["version"], 1)
        self.assertNotIn("type", record)
        stages = cast(list[dict[str, object]], record["stages"])
        self.assertEqual(
            [(cast(str, stage["kind"]), cast(int, stage["version"])) for stage in stages],
            [("http_download", 1), ("extract_archive", 1)],
        )


if __name__ == "__main__":
    _ = unittest.main()
