# pyright: reportImplicitOverride=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportAny=false, reportInconsistentConstructor=false, reportUnannotatedClassAttribute=false, reportMissingSuperCall=false, reportAttributeAccessIssue=false, reportArgumentType=false, reportPrivateUsage=false

from __future__ import annotations

import asyncio
import sys
import tempfile
import unittest
from pathlib import Path
from typing import cast

from orjson import loads
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    _ = sys.path.insert(0, str(ROOT))

from app.feature_pack.api import StageSnapshot
from app.feature_pack.api import Task
from app.feature_pack.api import TaskConfig
from app.feature_pack.api import TaskInput
from app.feature_pack.api import TaskSnapshot
from app.feature_pack.api import TaskStage
from app.feature_pack.internal import BrowserMessageType
from app.feature_pack.internal import BrowserTaskAction
from app.feature_pack.internal import BrowserTaskActionMapper
from app.feature_pack.internal import buildBrowserTaskSnapshot
from app.feature_pack.internal import buildBrowserTaskSummary
from app.services.browser_service import BrowserMessageType as HostBrowserMessageType
from app.services.browser_service import BrowserService
from app.services.browser_service import _BrowserClientSession


class DemoBrowserStage(TaskStage):
    def __init__(
        self,
        *,
        id: str,
        speed: int,
    ) -> None:
        super().__init__(id=id, kind="download", version=1, name=f"阶段 {id}")
        self.state = "waiting"
        self.progress = 0.0
        self.doneBytes = 0
        self.speed = speed

    async def run(self) -> None:
        return None

    def reset(self) -> None:
        self.state = "waiting"
        self.progress = 0.0
        self.doneBytes = 0
        self.speed = 0

    def snapshot(self) -> StageSnapshot:
        return StageSnapshot(
            id=self.id,
            kind=self.kind,
            name=self.name,
            state=self.state,
            progress=self.progress,
            doneBytes=self.doneBytes,
            speed=self.speed,
        )


class DemoBrowserTask(Task):
    def __init__(
        self,
        *,
        id: str = "task-1",
        packId: str = "demo_pack",
        kind: str = "single_file",
        name: str = "snapshot.bin",
        state: str = "waiting",
        progress: float = 0.0,
        doneBytes: int = 0,
        totalBytes: int = 0,
        target: str = "",
        canPause: bool = True,
        stageSpeeds: tuple[int, ...] = (),
    ) -> None:
        self.snapshotName = name
        self.snapshotState = state
        self.snapshotProgress = progress
        self.snapshotDoneBytes = doneBytes
        self.snapshotTotalBytes = totalBytes
        self.snapshotTarget = target
        self.snapshotCanPause = canPause
        self.pauseCalls = 0
        self.resetCalls = 0
        super().__init__(
            id=id,
            packId=packId,
            kind=kind,
            version=1,
            config=TaskConfig(
                source="demo:source",
                folder=Path("legacy-folder"),
                name="legacy.bin",
            ),
            stages=[
                DemoBrowserStage(id=f"stage-{index}", speed=speed)
                for index, speed in enumerate(stageSpeeds, start=1)
            ],
        )

    def syncOutput(self) -> None:
        return None

    async def pause(self) -> None:
        self.pauseCalls += 1
        self.snapshotState = "paused"

    def canPause(self) -> bool:
        return self.snapshotCanPause

    def reset(self) -> None:
        self.resetCalls += 1
        self.snapshotState = "waiting"
        self.snapshotProgress = 0.0
        self.snapshotDoneBytes = 0

    def snapshot(self) -> TaskSnapshot:
        return TaskSnapshot(
            id=self.id,
            packId=self.packId,
            kind=self.kind,
            name=self.snapshotName,
            state=self.snapshotState,
            progress=self.snapshotProgress,
            doneBytes=self.snapshotDoneBytes,
            totalBytes=self.snapshotTotalBytes,
            canPause=self.snapshotCanPause,
            target=self.snapshotTarget,
            stages=tuple(stage.snapshot() for stage in self.stages),
        )


class _FakeBrowserSocket:
    pass


class _BrowserMainWindow:
    def __init__(self) -> None:
        self.addedTasks: list[Task] = []

    def addTask(self, task: Task) -> bool:
        self.addedTasks.append(task)
        return True


class _BrowserServiceHarness(BrowserService):
    def __init__(self, tasks: list[Task] | None = None) -> None:
        self.mainWindow = _BrowserMainWindow()
        self.sentPayloads: list[dict[str, object]] = []
        self.broadcasts = 0
        self._tasks = tasks or []

    def _send(self, session: _BrowserClientSession, payload: dict[str, object]) -> None:
        _ = session
        self.sentPayloads.append(payload)

    def _broadcastTaskSnapshots(self) -> None:
        self.broadcasts += 1

    def _allTrackedTasks(self) -> list[Task]:
        return list(self._tasks)


class _RecordingHostCoreService:
    def __init__(self, task: Task) -> None:
        self.task = task
        self.inputs: list[object] = []

    def createTaskFromInput(self, data: object, callback) -> str:
        self.inputs.append(data)
        callback(self.task, None)
        return "request-1"


class FeaturePackBrowserV1Tests(unittest.TestCase):
    _temporaryDirectory: tempfile.TemporaryDirectory[str] | None = None
    tempPath: Path = ROOT

    def setUp(self) -> None:
        temporaryDirectory = tempfile.TemporaryDirectory()
        self._temporaryDirectory = temporaryDirectory
        self.addCleanup(temporaryDirectory.cleanup)
        self.tempPath = Path(temporaryDirectory.name)

    def testBuildBrowserTaskSummaryUsesTaskSnapshotFields(self) -> None:
        target = self.tempPath / "downloads" / "snapshot-video.mp4"
        target.parent.mkdir(parents=True, exist_ok=True)
        _ = target.write_text("done", encoding="utf-8")
        task = DemoBrowserTask(
            name="Snapshot Video",
            state="running",
            progress=42.345,
            doneBytes=128,
            totalBytes=512,
            target=str(target),
            stageSpeeds=(9, 6),
        )

        summary = buildBrowserTaskSummary(task)

        self.assertEqual(summary.id, "task-1")
        self.assertEqual(summary.packId, "demo_pack")
        self.assertEqual(summary.kind, "single_file")
        self.assertEqual(summary.name, "Snapshot Video")
        self.assertEqual(summary.state, "running")
        self.assertEqual(summary.progress, 42.34)
        self.assertEqual(summary.doneBytes, 128)
        self.assertEqual(summary.totalBytes, 512)
        self.assertEqual(summary.speed, 15)
        self.assertEqual(summary.target, str(target))
        self.assertEqual(summary.folder, str(target.parent))
        self.assertTrue(summary.canPause)
        self.assertTrue(summary.canOpenFile)
        self.assertTrue(summary.canOpenFolder)
        self.assertEqual(summary.fileExt, "mp4")

    def testBuildBrowserTaskSnapshotSerializesStableTaskProjection(self) -> None:
        fileTarget = self.tempPath / "downloads" / "episode-01.mkv"
        fileTarget.parent.mkdir(parents=True, exist_ok=True)
        _ = fileTarget.write_text("video", encoding="utf-8")
        folderTarget = self.tempPath / "downloads" / "series"
        folderTarget.mkdir(parents=True, exist_ok=True)

        snapshotPayload = loads(
            buildBrowserTaskSnapshot(
                [
                    DemoBrowserTask(
                        id="task-file",
                        name="Episode 01",
                        state="completed",
                        progress=100.0,
                        doneBytes=1024,
                        totalBytes=1024,
                        target=str(fileTarget),
                        stageSpeeds=(0,),
                    ),
                    DemoBrowserTask(
                        id="task-folder",
                        kind="multi_file",
                        name="Series",
                        state="waiting",
                        progress=0.0,
                        doneBytes=0,
                        totalBytes=2048,
                        target=str(folderTarget),
                        stageSpeeds=(3, 5),
                    ),
                ]
            )
        )

        self.assertEqual(snapshotPayload["type"], BrowserMessageType.TASK_SNAPSHOT)
        tasks = snapshotPayload["tasks"]
        self.assertEqual([task["id"] for task in tasks], ["task-file", "task-folder"])
        self.assertEqual(
            set(tasks[0]),
            {
                "id",
                "packId",
                "kind",
                "name",
                "state",
                "progress",
                "doneBytes",
                "totalBytes",
                "speed",
                "target",
                "folder",
                "canPause",
                "canOpenFile",
                "canOpenFolder",
                "fileExt",
            },
        )
        self.assertEqual(tasks[0]["name"], "Episode 01")
        self.assertEqual(tasks[0]["target"], str(fileTarget))
        self.assertEqual(tasks[0]["folder"], str(fileTarget.parent))
        self.assertTrue(tasks[0]["canOpenFile"])
        self.assertTrue(tasks[0]["canOpenFolder"])
        self.assertEqual(tasks[1]["kind"], "multi_file")
        self.assertEqual(tasks[1]["target"], str(folderTarget))
        self.assertEqual(tasks[1]["folder"], str(folderTarget))
        self.assertFalse(tasks[1]["canOpenFile"])
        self.assertTrue(tasks[1]["canOpenFolder"])
        self.assertEqual(tasks[1]["speed"], 8)
        self.assertEqual(tasks[1]["fileExt"], "")

    def testHostBrowserServiceSnapshotUsesV1TaskSnapshotFields(self) -> None:
        task = DemoBrowserTask(
            id="task-v1",
            name="V1 Browser Task",
            state="running",
            progress=12.5,
            doneBytes=128,
            totalBytes=1024,
            target=str(self.tempPath / "downloads" / "v1.bin"),
        )
        harness = _BrowserServiceHarness([task])

        snapshotPayload = loads(
            BrowserService._buildTaskSnapshot(harness)
        )

        self.assertEqual(snapshotPayload["type"], HostBrowserMessageType.TASK_SNAPSHOT)
        tasks = snapshotPayload["tasks"]
        self.assertEqual(tasks[0]["id"], "task-v1")
        self.assertEqual(tasks[0]["name"], "V1 Browser Task")
        self.assertEqual(tasks[0]["state"], "running")
        self.assertNotIn("taskId", tasks[0])
        self.assertNotIn("status", tasks[0])

    def testHostBrowserServiceCreateTaskBuildsTaskInputForCoreService(self) -> None:
        task = DemoBrowserTask(id="browser-created", name="Captured File")
        coreService = _RecordingHostCoreService(task)
        harness = _BrowserServiceHarness()
        session = _BrowserClientSession(socket=cast(object, _FakeBrowserSocket()))

        with patch("app.services.browser_service.coreService", coreService):
            BrowserService._handleCreateTask(
                harness,
                session,
                {
                    "requestId": "request-1",
                    "source": "resource",
                    "title": "captured-title.mp4",
                    "payload": {
                        "url": "https://example.com/video.mp4",
                        "filename": "video.mp4",
                        "headers": {"Referer": "https://example.com"},
                        "size": 4096,
                        "supportsRange": True,
                        "preBlockNum": 12,
                    },
                },
            )

        self.assertEqual(len(coreService.inputs), 1)
        taskInput = cast(TaskInput, coreService.inputs[0])
        self.assertEqual(taskInput.config.source, "https://example.com/video.mp4")
        self.assertEqual(taskInput.config.name, "captured-title.mp4")
        self.assertEqual(taskInput.config.headers, {"Referer": "https://example.com"})
        self.assertEqual(taskInput.config.chunks, 12)
        self.assertEqual(taskInput.size, 4096)
        self.assertEqual(taskInput.hints, ({"supportsRange": True},))
        self.assertEqual(harness.mainWindow.addedTasks, [task])
        self.assertEqual(
            harness.sentPayloads[-1],
            {
                "type": HostBrowserMessageType.CREATE_TASK_RESULT,
                "requestId": "request-1",
                "ok": True,
                "taskId": "browser-created",
            },
        )
        self.assertEqual(harness.broadcasts, 1)

    def testTogglePauseUsesTaskPauseForRunningTask(self) -> None:
        task = DemoBrowserTask(state="running", canPause=True)
        events: list[str] = []
        mapper = BrowserTaskActionMapper(
            startTask=lambda task: events.append(f"start:{task.id}"),
            cancelTask=lambda task: events.append(f"cancel:{task.id}"),
        )

        result = asyncio.run(mapper.execute(task=task, action=BrowserTaskAction.TOGGLE_PAUSE))

        self.assertTrue(result.ok)
        self.assertEqual(result.message, "")
        self.assertEqual(task.pauseCalls, 1)
        self.assertEqual(task.snapshotState, "paused")
        self.assertEqual(events, [])

    def testTogglePauseStartsWaitingTaskAndRejectsUnsupportedStates(self) -> None:
        startedTask = DemoBrowserTask(state="waiting")
        events: list[str] = []
        mapper = BrowserTaskActionMapper(
            startTask=lambda task: events.append(f"start:{task.id}"),
            cancelTask=lambda task: events.append(f"cancel:{task.id}"),
        )

        startedResult = asyncio.run(mapper.execute(task=startedTask, action="toggle_pause"))
        blockedResult = asyncio.run(
            mapper.execute(
                task=DemoBrowserTask(state="running", canPause=False),
                action=BrowserTaskAction.TOGGLE_PAUSE,
            )
        )
        completedResult = asyncio.run(
            mapper.execute(
                task=DemoBrowserTask(state="completed"),
                action=BrowserTaskAction.TOGGLE_PAUSE,
            )
        )

        self.assertTrue(startedResult.ok)
        self.assertEqual(events, ["start:task-1"])
        self.assertFalse(blockedResult.ok)
        self.assertEqual(blockedResult.message, "当前任务不支持暂停")
        self.assertFalse(completedResult.ok)
        self.assertEqual(completedResult.message, "任务已完成")

    def testCancelAndRedownloadUseHostCallbacksAndTaskReset(self) -> None:
        task = DemoBrowserTask(state="failed")
        events: list[str] = []

        async def startTask(task: Task) -> None:
            events.append(f"start:{task.id}")

        async def cancelTask(task: Task) -> None:
            events.append(f"cancel:{task.id}")

        mapper = BrowserTaskActionMapper(startTask=startTask, cancelTask=cancelTask)

        cancelResult = asyncio.run(mapper.execute(task=task, action=BrowserTaskAction.CANCEL))
        redownloadResult = asyncio.run(
            mapper.execute(task=task, action=BrowserTaskAction.REDOWNLOAD)
        )

        self.assertTrue(cancelResult.ok)
        self.assertTrue(redownloadResult.ok)
        self.assertEqual(events, ["cancel:task-1", "cancel:task-1", "start:task-1"])
        self.assertEqual(task.resetCalls, 1)
        self.assertEqual(task.snapshotState, "waiting")

    def testOpenFileAndFolderActionsUseSnapshotTarget(self) -> None:
        target = self.tempPath / "downloads" / "archive.zip"
        target.parent.mkdir(parents=True, exist_ok=True)
        _ = target.write_text("zip", encoding="utf-8")
        fileTargets: list[Path] = []
        folderTargets: list[Path] = []
        mapper = BrowserTaskActionMapper(
            startTask=lambda task: None,
            cancelTask=lambda task: None,
            openFilePath=fileTargets.append,
            openFolderPath=folderTargets.append,
        )
        task = DemoBrowserTask(state="completed", target=str(target))

        openFileResult = asyncio.run(
            mapper.execute(task=task, action=BrowserTaskAction.OPEN_FILE)
        )
        openFolderResult = asyncio.run(
            mapper.execute(task=task, action=BrowserTaskAction.OPEN_FOLDER)
        )

        self.assertTrue(openFileResult.ok)
        self.assertTrue(openFolderResult.ok)
        self.assertEqual(fileTargets, [target])
        self.assertEqual(folderTargets, [target.parent])


if __name__ == "__main__":
    _ = unittest.main()
