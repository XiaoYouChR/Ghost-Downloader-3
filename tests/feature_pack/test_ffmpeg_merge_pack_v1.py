# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportAny=false, reportImplicitOverride=false

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


class FFmpegMergePackV1Tests(unittest.TestCase):
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
        Task.__recordRegistry__.pop(("ffmpeg_pack", "ffmpeg_merge", 1), None)
        TaskStage.__recordRegistry__.pop(("http_pack", "http_download", 1, "http_download", 1), None)
        TaskStage.__recordRegistry__.pop(("extract_pack", "extract_archive", 1, "extract_archive", 1), None)
        TaskStage.__recordRegistry__.pop(("ffmpeg_pack", "ffmpeg_install", 1, "http_download", 1), None)
        TaskStage.__recordRegistry__.pop(("ffmpeg_pack", "ffmpeg_install", 1, "extract_archive", 1), None)
        TaskStage.__recordRegistry__.pop(("ffmpeg_pack", "ffmpeg_merge", 1, "http_download", 1), None)
        TaskStage.__recordRegistry__.pop(("ffmpeg_pack", "ffmpeg_merge", 1, "ffmpeg_merge", 1), None)
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

    def mergeModule(self) -> ModuleType:
        import importlib

        return cast(ModuleType, importlib.import_module("_ghost_feature_pack_ffmpeg_pack.merge_task"))

    def buildTaskInput(self, *, outputName: str = "") -> TaskInput:
        return TaskInput(
            config=TaskConfig(
                source="gd3+ffmpeg://merge",
                folder=self.workspace / "downloads",
                name=outputName,
                proxies={"https": "http://127.0.0.1:7890"},
                chunks=8,
            ),
            hints=(
                {
                    "outputTitle": "Episode 01",
                    "resources": [
                        {
                            "url": "https://cdn.example.com/video/episode-01.video.m4s",
                            "headers": {"Referer": "https://example.com/watch"},
                            "filename": "episode-01.video.m4s",
                            "size": 1024,
                            "supportsRange": True,
                            "pageTitle": "Episode 01",
                        },
                        {
                            "url": "https://cdn.example.com/audio/episode-01.audio.m4a",
                            "headers": {"Referer": "https://example.com/watch"},
                            "filename": "episode-01.audio.m4a",
                            "size": 512,
                            "supportsRange": True,
                        },
                    ],
                },
            ),
        )

    def testFfmpegPackCreatesMergeTaskFromTaskInput(self) -> None:
        service = self.createService()
        mergeModule = self.mergeModule()

        with patch.object(
            mergeModule,
            "resolveFFmpegExecutables",
            return_value=("ffmpeg", "ffprobe"),
        ):
            task = asyncio.run(service.createTask(self.buildTaskInput()))

        self.assertEqual(type(task).__name__, "FFmpegMergeTask")
        self.assertEqual(task.packId, "ffmpeg_pack")
        self.assertEqual(task.kind, "ffmpeg_merge")
        self.assertEqual(task.config.name, "Episode 01.mp4")
        self.assertEqual(task.snapshot().target, str(self.workspace / "downloads" / "Episode 01.mp4").replace("\\", "/"))
        self.assertEqual(task.snapshot().totalBytes, 1536)

        stages = list(task.stages)
        self.assertEqual(
            [type(stage).__name__ for stage in stages],
            ["FFmpegMergeDownloadStage", "FFmpegMergeDownloadStage", "FFmpegStage"],
        )
        self.assertEqual(cast(str, getattr(stages[0], "resolvePath")), str(self.workspace / "downloads" / "Episode 01.video.m4s").replace("\\", "/"))
        self.assertEqual(cast(str, getattr(stages[1], "resolvePath")), str(self.workspace / "downloads" / "Episode 01.audio.m4a").replace("\\", "/"))
        self.assertEqual(cast(str, getattr(stages[2], "resolvePath")), str(self.workspace / "downloads" / "Episode 01.mp4").replace("\\", "/"))
        self.assertEqual(cast(str, getattr(stages[0], "url")), "https://cdn.example.com/video/episode-01.video.m4s")
        self.assertEqual(cast(str, getattr(stages[1], "url")), "https://cdn.example.com/audio/episode-01.audio.m4a")
        self.assertEqual(cast(dict[str, str], getattr(stages[0], "headers")), {"Referer": "https://example.com/watch"})
        self.assertEqual(cast(int, getattr(stages[0], "blockNum")), 8)
        self.assertEqual(cast(dict[str, str] | None, getattr(stages[0], "proxies")), {"https": "http://127.0.0.1:7890"})

    def testFfmpegMergeTaskConfigureUpdatesOutputPathsWithoutOverwritingResourceUrls(self) -> None:
        service = self.createService()
        mergeModule = self.mergeModule()

        with patch.object(
            mergeModule,
            "resolveFFmpegExecutables",
            return_value=("ffmpeg", "ffprobe"),
        ):
            task = asyncio.run(service.createTask(self.buildTaskInput()))

        updatedConfig = TaskConfig(
            source="gd3+ffmpeg://merge",
            folder=self.workspace / "archive",
            name="renamed-output",
            proxies={"https": "socks5://127.0.0.1:1080"},
            chunks=3,
        )
        task = cast(Any, task)
        task.configure(updatedConfig)

        self.assertEqual(task.config.name, "renamed-output.mp4")
        self.assertEqual(task.snapshot().target, str(self.workspace / "archive" / "renamed-output.mp4").replace("\\", "/"))
        self.assertEqual(cast(str, getattr(task.stages[0], "url")), "https://cdn.example.com/video/episode-01.video.m4s")
        self.assertEqual(cast(str, getattr(task.stages[1], "url")), "https://cdn.example.com/audio/episode-01.audio.m4a")
        self.assertEqual(cast(dict[str, str], getattr(task.stages[0], "headers")), {"Referer": "https://example.com/watch"})
        self.assertEqual(cast(dict[str, str] | None, getattr(task.stages[0], "proxies")), {"https": "socks5://127.0.0.1:1080"})
        self.assertEqual(cast(int, getattr(task.stages[0], "blockNum")), 3)
        self.assertEqual(cast(str, getattr(task.stages[0], "resolvePath")), str(self.workspace / "archive" / "renamed-output.video.m4s").replace("\\", "/"))
        self.assertEqual(cast(str, getattr(task.stages[1], "resolvePath")), str(self.workspace / "archive" / "renamed-output.audio.m4a").replace("\\", "/"))
        self.assertEqual(cast(str, getattr(task.stages[2], "resolvePath")), str(self.workspace / "archive" / "renamed-output.mp4").replace("\\", "/"))

    def testFfmpegMergeTaskRunsAndRecorderRestores(self) -> None:
        service = self.createService()
        mergeModule = self.mergeModule()

        with patch.object(
            mergeModule,
            "resolveFFmpegExecutables",
            return_value=("ffmpeg", "ffprobe"),
        ):
            task = asyncio.run(service.createTask(self.buildTaskInput()))

        task = cast(Any, task)

        class FakeHttpWorker:
            def __init__(self, stage: object) -> None:
                self.stage = stage

            async def run(self) -> None:
                resolvePath = Path(cast(str, getattr(self.stage, "resolvePath")))
                resolvePath.parent.mkdir(parents=True, exist_ok=True)
                payload = b"video-data" if cast(int, getattr(self.stage, "stageIndex")) == 1 else b"audio-data"
                resolvePath.write_bytes(payload)
                Path(str(resolvePath) + ".ghd").write_bytes(b"resume")
                getattr(self.stage, "updateTransfer")(doneBytes=len(payload), speed=0, progress=100.0)
                getattr(self.stage, "setStatus")("completed")

        class FakeFFmpegWorker:
            def __init__(self, stage: object) -> None:
                self.stage = stage

            async def run(self) -> None:
                videoPath = Path(cast(str, getattr(self.stage, "videoPath")))
                audioPath = Path(cast(str, getattr(self.stage, "audioPath")))
                outputPath = Path(cast(str, getattr(self.stage, "resolvePath")))
                outputPath.parent.mkdir(parents=True, exist_ok=True)
                outputPath.write_bytes(videoPath.read_bytes() + audioPath.read_bytes())
                if cast(bool, getattr(self.stage, "cleanupSource")):
                    for sourcePath in (videoPath, audioPath):
                        sourcePath.unlink()
                        ghdPath = Path(str(sourcePath) + ".ghd")
                        if ghdPath.exists():
                            ghdPath.unlink()
                getattr(self.stage, "updateTransfer")(doneBytes=outputPath.stat().st_size, speed=0, progress=100.0)
                getattr(self.stage, "setStatus")("completed")

        with patch.object(mergeModule, "HttpWorker", FakeHttpWorker), patch.object(
            mergeModule,
            "FFmpegWorker",
            FakeFFmpegWorker,
        ):
            asyncio.run(task.run())

        finalPath = self.workspace / "downloads" / "Episode 01.mp4"
        self.assertTrue(finalPath.is_file())
        self.assertFalse((self.workspace / "downloads" / "Episode 01.video.m4s").exists())
        self.assertFalse((self.workspace / "downloads" / "Episode 01.audio.m4a").exists())
        self.assertFalse((self.workspace / "downloads" / "Episode 01.video.m4s.ghd").exists())
        self.assertFalse((self.workspace / "downloads" / "Episode 01.audio.m4a.ghd").exists())
        self.assertEqual(task.snapshot().state, "completed")
        self.assertEqual(task.snapshot().progress, 100.0)

        recorder = TaskRecorder(recordFile=self.workspace / "FeaturePackMemory.log")
        recorder.load()
        recorder.add(task, flush=True)
        record = recorder.serializeTask(cast(Task, task))
        restored = recorder.read()[task.id]

        self.assertEqual(record["packId"], "ffmpeg_pack")
        self.assertEqual(record["kind"], "ffmpeg_merge")
        self.assertEqual(record["version"], 1)
        self.assertNotIn("type", record)
        self.assertEqual(
            [
                (cast(str, stageRecord["kind"]), cast(int, stageRecord["version"]))
                for stageRecord in cast(list[dict[str, object]], record["stages"])
            ],
            [("http_download", 1), ("http_download", 1), ("ffmpeg_merge", 1)],
        )
        self.assertEqual(type(restored).__name__, "FFmpegMergeTask")
        self.assertEqual(restored.snapshot().state, "completed")
        self.assertEqual(restored.snapshot().target, str(finalPath).replace("\\", "/"))
        self.assertEqual(
            [type(stage).__name__ for stage in restored.stages],
            ["FFmpegMergeDownloadStage", "FFmpegMergeDownloadStage", "FFmpegStage"],
        )


if __name__ == "__main__":
    _ = unittest.main()
