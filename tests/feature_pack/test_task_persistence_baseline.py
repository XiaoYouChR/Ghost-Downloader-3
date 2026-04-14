from __future__ import annotations
# pyright: reportPrivateUsage=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false, reportUnknownLambdaType=false, reportImplicitOverride=false, reportExplicitAny=false

import sys
import tempfile
import unittest
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

from orjson import loads


ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    _ = sys.path.insert(0, str(ROOT))

from app.bases.models import Task, TaskStage, TaskStatus
from app.services.browser_service import BrowserMessageType, BrowserService
from app.supports.recorder import TaskRecorder
from features.ftp_pack.task import FtpConnectionInfo, FtpRemoteFile, FtpTask, FtpTaskStage


@dataclass(kw_only=True)
class HttpTaskStage(TaskStage):
    url: str
    fileSize: int
    headers: dict[str, str] = field(default_factory=dict)
    proxies: dict[str, str] = field(default_factory=dict)
    resolvePath: str = ""
    blockNum: int = 1
    supportsRange: bool = True


@dataclass(kw_only=True)
class HttpTask(Task):
    headers: dict[str, str] = field(default_factory=dict)
    proxies: dict[str, str] = field(default_factory=dict)
    blockNum: int = 1
    supportsRange: bool = True

    def syncStagePaths(self) -> None:
        resolvePath = self.resolvePath
        for stage in self.stages:
            if not isinstance(stage, HttpTaskStage):
                continue
            stage.resolvePath = resolvePath
            stage.fileSize = self.fileSize
            if self.headers and not stage.headers:
                stage.headers = dict(self.headers)
            if self.proxies and not stage.proxies:
                stage.proxies = dict(self.proxies)
            stage.blockNum = self.blockNum

    async def run(self) -> None:
        raise NotImplementedError


HttpTask.__module__ = "features.http_pack.task"
HttpTaskStage.__module__ = "features.http_pack.task"


class BrowserSnapshotHarness:
    def __init__(self, tasks: list[Task]):
        self._tasks: list[Task] = tasks

    def _allTrackedTasks(self) -> list[Task]:
        return self._tasks

    def _serializeTask(self, task: Task) -> dict[str, Any]:
        browserServiceLike = cast(BrowserService, cast(object, self))
        return BrowserService._serializeTask(browserServiceLike, task)

    def _buildTaskSnapshot(self) -> bytes:
        browserServiceLike = cast(BrowserService, cast(object, self))
        return BrowserService._buildTaskSnapshot(browserServiceLike)


class TaskPersistenceBaselineTests(unittest.TestCase):
    _temporaryDirectory: tempfile.TemporaryDirectory[str] | None = None
    tempPath: Path = ROOT

    def setUp(self) -> None:
        temporaryDirectory = tempfile.TemporaryDirectory()
        self._temporaryDirectory = temporaryDirectory
        self.addCleanup(temporaryDirectory.cleanup)
        self.tempPath = Path(temporaryDirectory.name)

    def createHttpTask(
        self,
        *,
        title: str = "example.mp4",
        createdAt: int = 1_000,
        fileSize: int = 256,
    ) -> HttpTask:
        stage = HttpTaskStage(
            stageIndex=1,
            url="https://example.com/example.mp4",
            fileSize=fileSize,
            headers={"referer": "https://example.com"},
            proxies={"http": "http://127.0.0.1:7890"},
            resolvePath="",
            blockNum=4,
        )
        return HttpTask(
            title=title,
            url="https://example.com/example.mp4",
            fileSize=fileSize,
            path=self.tempPath,
            stages=[stage],
            createdAt=createdAt,
        )

    def createFtpTask(self, *, createdAt: int = 2_000) -> FtpTask:
        task = FtpTask(
            title="series",
            url="ftp://example.com/media",
            fileSize=320,
            path=self.tempPath,
            stages=[
                FtpTaskStage(
                    stageIndex=1,
                    fileIndex=0,
                    remotePath="/media/episode-1.mp4",
                    fileSize=128,
                    resolvePath="",
                ),
                FtpTaskStage(
                    stageIndex=2,
                    fileIndex=1,
                    remotePath="/media/episode-2.mp4",
                    fileSize=192,
                    resolvePath="",
                ),
            ],
            createdAt=createdAt,
            connectionInfo=FtpConnectionInfo(
                host="example.com",
                scheme="ftp",
                port=21,
                username="anonymous",
                password="anon@",
                sourcePath="/media",
                portSpecified=False,
            ),
            sourceType="dir",
            files=[
                FtpRemoteFile(
                    index=0,
                    remotePath="/media/episode-1.mp4",
                    relativePath="episode-1.mp4",
                    size=128,
                ),
                FtpRemoteFile(
                    index=1,
                    remotePath="/media/episode-2.mp4",
                    relativePath="episode-2.mp4",
                    size=192,
                ),
            ],
            proxies={"ftp": "socks5://127.0.0.1:7890"},
            blockNum=8,
        )
        _ = task.updateSelectedFiles({0})
        return task

    def testTaskStageSerializeAndDeserializeRoundTripsSubclassFields(self) -> None:
        stage = HttpTaskStage(
            stageIndex=1,
            url="https://example.com/video.mp4",
            fileSize=512,
            headers={"accept": "*/*"},
            proxies={"http": "http://127.0.0.1:7890"},
            resolvePath=str(self.tempPath / "video.mp4"),
            blockNum=8,
        )
        stage.receivedBytes = 128
        stage.speed = 64
        stage.setStatus(TaskStatus.PAUSED, notifyTask=False)

        serialized = cast(dict[str, object], loads(stage.serialize()))

        self.assertEqual(serialized["type"], "HttpTaskStage")
        self.assertEqual(serialized["status"], "PAUSED")
        self.assertEqual(serialized["resolvePath"], str(self.tempPath / "video.mp4"))

        restored = TaskStage.deserialize(serialized)

        self.assertIsInstance(restored, HttpTaskStage)
        restoredStage = cast(HttpTaskStage, restored)
        self.assertEqual(restoredStage.stageIndex, 1)
        self.assertEqual(restoredStage.status, TaskStatus.PAUSED)
        self.assertEqual(restoredStage.receivedBytes, 128)
        self.assertEqual(restoredStage.speed, 0)
        self.assertEqual(restoredStage.resolvePath, str(self.tempPath / "video.mp4"))

    def testTaskSerializeUsesClassNamesAndDropsTransientFeaturePackName(self) -> None:
        task = self.createHttpTask()
        stage = cast(HttpTaskStage, task.stages[0])
        stage.receivedBytes = 128
        stage.speed = 32
        stage.progress = 50
        _ = task.syncStatusFromStages()
        setattr(task, "_featurePackName", "http_pack")

        # 当前旧模型直接把 Python 类名写进 type 字段，恢复时靠类名注册表反查。
        serialized = cast(dict[str, object], loads(task.serialize()))

        self.assertEqual(serialized["type"], "HttpTask")
        stages = cast(list[dict[str, object]], serialized["stages"])
        self.assertEqual(stages[0]["type"], "HttpTaskStage")
        self.assertNotIn("_featurePackName", serialized)

        restored = Task.deserialize(serialized)

        self.assertIsInstance(restored, HttpTask)
        restoredTask = cast(HttpTask, restored)
        self.assertIsInstance(restoredTask.path, Path)
        self.assertEqual(restoredTask.path, self.tempPath)
        self.assertEqual(restoredTask.status, TaskStatus.WAITING)
        self.assertFalse(hasattr(restoredTask, "_featurePackName"))
        self.assertIsInstance(restoredTask.stages[0], HttpTaskStage)
        self.assertEqual(
            cast(HttpTaskStage, restoredTask.stages[0]).resolvePath,
            str(self.tempPath / "example.mp4"),
        )

    def testFtpTaskDeserializeRebuildsTransientSelectionState(self) -> None:
        task = self.createFtpTask()
        selectedStage = cast(FtpTaskStage, task.stages[0])
        selectedStage.receivedBytes = 64
        selectedStage.progress = 50
        selectedStage.setStatus(TaskStatus.RUNNING)

        restored = cast(FtpTask, Task.deserialize(task.serialize()))

        self.assertIsInstance(restored, FtpTask)
        self.assertEqual(restored.selectedFileCount, 1)
        self.assertEqual(restored.totalFileCount, 2)
        self.assertEqual(restored.fileSize, 128)
        self.assertEqual(restored.fileByIndex(0).relativePath, "episode-1.mp4")
        self.assertFalse(restored.fileByIndex(1).selected)
        self.assertEqual([stage.fileIndex for stage in restored.selectedStages], [0])
        self.assertEqual(
            cast(FtpTaskStage, restored.stages[0]).resolvePath,
            str(self.tempPath / "series" / "episode-1.mp4"),
        )
        self.assertEqual(
            cast(FtpTaskStage, restored.stages[1]).resolvePath,
            str(self.tempPath / "series" / "episode-2.mp4"),
        )

    def testTaskRecorderRequiresLoadBeforeFlushAndRestoresTypedTasks(self) -> None:
        with patch(
            "app.supports.recorder.QStandardPaths.writableLocation",
            return_value=str(self.tempPath),
        ):
            recorder = TaskRecorder()

        httpTask = self.createHttpTask(createdAt=1_100)
        ftpTask = self.createFtpTask(createdAt=1_200)

        recorder.memorizedTasks[httpTask.taskId] = httpTask
        recorder.flush()
        self.assertEqual(recorder.recordFile.read_text(encoding="utf-8"), "")

        recorder.load()
        recorder.add(httpTask, flush=False)
        recorder.add(ftpTask, flush=True)

        lines = recorder.recordFile.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 2)
        self.assertEqual(cast(str, loads(lines[0])["type"]), "HttpTask")
        self.assertEqual(cast(str, loads(lines[1])["type"]), "FtpTask")

        restored = recorder.read()

        self.assertEqual(set(restored), {httpTask.taskId, ftpTask.taskId})
        self.assertIsInstance(restored[httpTask.taskId], HttpTask)
        self.assertIsInstance(restored[ftpTask.taskId], FtpTask)
        restoredFtpTask = cast(FtpTask, restored[ftpTask.taskId])
        self.assertEqual(restoredFtpTask.selectedFileCount, 1)
        self.assertEqual([stage.fileIndex for stage in restoredFtpTask.selectedStages], [0])

    def testBrowserTaskSnapshotKeepsCurrentFieldSetAndSortOrder(self) -> None:
        completedTask = self.createHttpTask(title="finished.mp4", createdAt=3_000, fileSize=400)
        completedStage = cast(HttpTaskStage, completedTask.stages[0])
        completedStage.receivedBytes = 400
        completedStage.speed = 0
        completedStage.setStatus(TaskStatus.COMPLETED)
        outputPath = Path(completedTask.resolvePath)
        outputPath.parent.mkdir(parents=True, exist_ok=True)
        _ = outputPath.write_text("done", encoding="utf-8")

        runningTask = self.createHttpTask(title="running.mkv", createdAt=2_000, fileSize=800)
        runningStage = cast(HttpTaskStage, runningTask.stages[0])
        runningStage.receivedBytes = 200
        runningStage.speed = 25
        runningStage.progress = 25
        runningStage.setStatus(TaskStatus.RUNNING)

        harness = BrowserSnapshotHarness([runningTask, completedTask])

        snapshot = cast(dict[str, object], loads(harness._buildTaskSnapshot()))

        self.assertEqual(snapshot["type"], BrowserMessageType.TASK_SNAPSHOT)
        tasks = cast(list[dict[str, object]], snapshot["tasks"])
        self.assertEqual([cast(str, item["taskId"]) for item in tasks], [completedTask.taskId, runningTask.taskId])
        self.assertEqual(
            set(tasks[0]),
            {
                "taskId",
                "title",
                "status",
                "progress",
                "receivedBytes",
                "fileSize",
                "speed",
                "createdAt",
                "resolvePath",
                "parentPath",
                "canPause",
                "canOpenFile",
                "canOpenFolder",
                "fileExt",
                "packName",
            },
        )
        self.assertEqual(tasks[0]["status"], "completed")
        self.assertEqual(tasks[0]["progress"], 100.0)
        self.assertEqual(tasks[0]["receivedBytes"], 400)
        self.assertEqual(tasks[0]["fileExt"], "mp4")
        self.assertEqual(tasks[0]["packName"], "http_pack")
        self.assertEqual(tasks[0]["resolvePath"], str(outputPath))
        self.assertEqual(tasks[0]["parentPath"], str(outputPath.parent))
        self.assertTrue(cast(bool, tasks[0]["canOpenFile"]))
        self.assertTrue(cast(bool, tasks[0]["canOpenFolder"]))
        self.assertEqual(tasks[1]["status"], "running")
        self.assertEqual(tasks[1]["progress"], 25.0)
        self.assertEqual(tasks[1]["receivedBytes"], 200)
        self.assertEqual(tasks[1]["speed"], 25)
        self.assertEqual(tasks[1]["fileExt"], "mkv")
        self.assertFalse(cast(bool, tasks[1]["canOpenFile"]))


if __name__ == "__main__":
    _ = unittest.main()
