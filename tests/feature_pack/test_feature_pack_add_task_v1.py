# pyright: reportImplicitOverride=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false, reportPrivateUsage=false, reportAny=false, reportInconsistentConstructor=false

from __future__ import annotations

import asyncio
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from typing import cast
from typing import Callable
from typing import final


ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    _ = sys.path.insert(0, str(ROOT))

from app.feature_pack.api import DefaultFeatureService
from app.feature_pack.api import FeatureService
from app.feature_pack.api import Task
from app.feature_pack.api import TaskInput
from app.feature_pack.internal import AddTaskDialogSession
from app.feature_pack.internal import AddTaskInputOverride
from app.feature_pack.internal import buildAddTaskInput
from app.view.components.add_task_dialog_session import AddTaskParseSession


class _FakeWindow:
    def __init__(self) -> None:
        self.installed: list[str] = []


@final
class _ControlledTaskRunner:
    featureService: FeatureService

    def __init__(self, *, featureService: FeatureService) -> None:
        self.featureService = featureService
        self.requestInputs: list[tuple[str, TaskInput]] = []
        self.pendingCallbacks: dict[str, tuple[TaskInput, Callable[[Task | None, str | None], None]]] = {}
        self.cancelledRequests: list[str] = []

    def createTask(
        self,
        data: TaskInput,
        callback: Callable[[Task | None, str | None], None],
    ) -> str:
        requestId = f"request-{len(self.requestInputs) + 1}"
        self.requestInputs.append((requestId, data))
        self.pendingCallbacks[requestId] = (data, callback)
        return requestId

    def cancel(self, requestId: str) -> bool:
        self.cancelledRequests.append(requestId)
        return self.pendingCallbacks.pop(requestId, None) is not None

    def complete(self, requestId: str, *, error: str | None = None) -> bool:
        pending = self.pendingCallbacks.pop(requestId, None)
        if pending is None:
            return False

        data, callback = pending
        if error is not None:
            callback(None, error)
            return True

        task = asyncio.run(self.featureService.createTask(data))
        callback(task, None)
        return True


class FeaturePackAddTaskV1Tests(unittest.TestCase):
    _temporaryDirectory: tempfile.TemporaryDirectory[str] | None = None
    featuresPath: Path = ROOT

    def setUp(self) -> None:
        temporaryDirectory = tempfile.TemporaryDirectory()
        self._temporaryDirectory = temporaryDirectory
        self.addCleanup(temporaryDirectory.cleanup)
        self.featuresPath = Path(temporaryDirectory.name) / "features"

    def createService(self) -> DefaultFeatureService:
        return DefaultFeatureService(featuresPath=self.featuresPath)

    def writePack(self) -> None:
        packDirectory = self.featuresPath / "demo_pack"
        packDirectory.mkdir(parents=True, exist_ok=True)
        manifestBody = textwrap.dedent(
            """
            [pack]
            id = "demo_pack"
            name = "demo_pack"
            version = "1.0.0"
            api = 1
            entry = "pack.py"
            dependencies = []
            """
        ).strip()
        _ = (packDirectory / "manifest.toml").write_text(
            manifestBody + "\n",
            encoding="utf-8",
        )
        _ = (packDirectory / "pack.py").write_text(
            textwrap.dedent(
                """
                from app.feature_pack.api import FeaturePack, StageSnapshot, Task, TaskConfig, TaskInput, TaskSnapshot, TaskStage


                class DemoStage(TaskStage):
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
                        )


                class DemoTask(Task):
                    def __init__(self, *, config: TaskConfig, size: int, hintCount: int) -> None:
                        self.state = "waiting"
                        self.progress = 0.0
                        self.doneBytes = 0
                        self.totalBytes = size
                        self.target = ""
                        self.hintCount = hintCount
                        super().__init__(
                            id=f"task-{config.source.replace(':', '-')}",
                            packId="demo_pack",
                            kind="demo",
                            version=1,
                            config=config,
                            stages=[
                                DemoStage(
                                    id="stage-1",
                                    kind="download",
                                    version=1,
                                    name="下载阶段",
                                )
                            ],
                        )
                        self.syncOutput()

                    def _displayName(self) -> str:
                        if self.config.name:
                            return self.config.name
                        return self.config.source.split(":", 1)[-1] + ".bin"

                    def syncOutput(self) -> None:
                        self.target = str(self.config.folder / self._displayName())

                    def reset(self) -> None:
                        self.state = "waiting"

                    def snapshot(self) -> TaskSnapshot:
                        return TaskSnapshot(
                            id=self.id,
                            packId=self.packId,
                            kind=self.kind,
                            name=self._displayName(),
                            state=self.state,
                            progress=self.progress,
                            doneBytes=self.doneBytes,
                            totalBytes=self.totalBytes,
                            canPause=self.canPause(),
                            target=self.target,
                            stages=tuple(stage.snapshot() for stage in self.stages),
                        )


                class DemoPack(FeaturePack):
                    def accepts(self, source: str) -> bool:
                        return source.startswith("demo:")

                    async def createTask(self, data: TaskInput) -> Task | None:
                        return DemoTask(
                            config=data.config,
                            size=data.size,
                            hintCount=len(data.hints),
                        )

                    def owns(self, task: Task) -> bool:
                        return task.packId == self.manifest.id

                    def createResultCard(self, task: Task, parent=None):
                        snapshot = task.snapshot()
                        return {
                            "kind": "result",
                            "taskId": task.id,
                            "name": snapshot.name,
                            "target": snapshot.target,
                            "parentType": type(parent).__name__ if parent is not None else None,
                        }
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )

    def loadService(self) -> DefaultFeatureService:
        self.writePack()
        service = self.createService()
        service.loadPacks(_FakeWindow())
        return service

    def testBuildAddTaskInputUsesSharedConfigAndSourceOverride(self) -> None:
        taskInput = buildAddTaskInput(
            source="demo:episode-1",
            folder=Path("downloads"),
            headers={"User-Agent": "Ghost Downloader"},
            proxies={"https": "http://127.0.0.1:7890"},
            chunks=8,
            override=AddTaskInputOverride(
                folder=Path("archive"),
                name="episode-1.mp4",
                headers={"Referer": "https://example.com"},
                chunks=16,
                size=4096,
                hints=({"origin": "browser"},),
            ),
        )

        self.assertEqual(taskInput.config.source, "demo:episode-1")
        self.assertEqual(taskInput.config.folder, Path("archive"))
        self.assertEqual(taskInput.config.name, "episode-1.mp4")
        self.assertEqual(taskInput.config.headers, {"Referer": "https://example.com"})
        self.assertEqual(taskInput.config.proxies, {"https": "http://127.0.0.1:7890"})
        self.assertEqual(taskInput.config.chunks, 16)
        self.assertEqual(taskInput.size, 4096)
        self.assertEqual(taskInput.hints, ({"origin": "browser"},))

    def testHistoricalAddTaskSessionImportPointsToV1Session(self) -> None:
        self.assertIs(AddTaskParseSession, AddTaskDialogSession)

    def testAddTaskDialogSessionRestartsPendingRequestsAndAppliesConfigThroughFeatureService(self) -> None:
        service = self.loadService()
        runner = _ControlledTaskRunner(featureService=service)
        session = AddTaskDialogSession(
            featureService=service,
            taskRunner=runner,
        )
        busyStates: list[bool] = []
        parseErrors: list[tuple[str, str]] = []
        _ = session.parsingBusyChanged.connect(busyStates.append)
        def recordParseError(source: str, error: str) -> None:
            parseErrors.append((source, error))

        _ = session.parseErrorOccurred.connect(recordParseError)

        session.setBaseConfig(
            folder=Path("downloads"),
            headers={"User-Agent": "Ghost Downloader"},
            proxies={"https": "http://127.0.0.1:7890"},
            chunks=4,
        )
        session.setSourceOverride(
            "demo:video-1",
            AddTaskInputOverride(
                size=2048,
                hints=({"source": "browser"},),
            ),
        )
        session.updateSources(["demo:video-1"])

        self.assertEqual(len(runner.requestInputs), 1)
        firstRequestId, firstInput = runner.requestInputs[0]
        self.assertEqual(firstInput.config.folder, Path("downloads"))
        self.assertEqual(firstInput.config.headers, {"User-Agent": "Ghost Downloader"})
        self.assertEqual(firstInput.config.chunks, 4)
        self.assertEqual(firstInput.size, 2048)
        self.assertEqual(firstInput.hints, ({"source": "browser"},))
        self.assertTrue(session.canAccept())

        session.setBaseConfig(
            folder=Path("archive"),
            headers={"User-Agent": "Ghost Downloader"},
            proxies={"https": "http://127.0.0.1:7890"},
            chunks=6,
        )

        self.assertEqual(runner.cancelledRequests, [firstRequestId])
        self.assertEqual(len(runner.requestInputs), 2)
        secondRequestId, secondInput = runner.requestInputs[1]
        self.assertEqual(secondInput.config.folder, Path("archive"))
        self.assertEqual(secondInput.config.chunks, 6)
        self.assertNotEqual(firstRequestId, secondRequestId)
        self.assertFalse(runner.complete(firstRequestId))
        self.assertTrue(runner.complete(secondRequestId))
        self.assertFalse(parseErrors)

        previewTasks = session.previewTasks()
        self.assertEqual(len(previewTasks), 1)
        task = previewTasks[0]
        self.assertEqual(task.config.folder, Path("archive"))
        self.assertEqual(task.config.chunks, 6)
        self.assertEqual(task.snapshot().target, str(Path("archive") / "video-1.bin"))
        self.assertEqual(
            session.resultCards(),
            [
                {
                    "kind": "result",
                    "taskId": "task-demo-video-1",
                    "name": "video-1.bin",
                    "target": str(Path("archive") / "video-1.bin"),
                    "parentType": None,
                }
            ],
        )
        self.assertIn(True, busyStates)
        self.assertFalse(busyStates[-1])

        acceptedTasks = session.accept()

        self.assertEqual(acceptedTasks, [task])
        self.assertEqual(session.previewTasks(), [])
        self.assertEqual(session.resultCards(), [])

    def testAddTaskDialogSessionEmitsConfirmedTaskWhenAcceptedRequestFinishesLater(self) -> None:
        service = self.loadService()
        runner = _ControlledTaskRunner(featureService=service)
        session = AddTaskDialogSession(
            featureService=service,
            taskRunner=runner,
        )
        confirmedTasks: list[Task] = []

        def recordConfirmedTask(task: object) -> None:
            confirmedTasks.append(cast(Task, task))

        _ = session.taskConfirmed.connect(recordConfirmedTask)

        session.setBaseConfig(
            folder=Path("downloads"),
            headers={"User-Agent": "Ghost Downloader"},
            chunks=2,
        )
        session.setSourceOverride(
            "demo:video-2",
            AddTaskInputOverride(name="video-2.mp4"),
        )
        session.updateSources(["demo:video-2"])

        requestId, _taskInput = runner.requestInputs[0]
        acceptedTasks = session.accept()

        self.assertEqual(acceptedTasks, [])
        self.assertTrue(runner.complete(requestId))
        self.assertEqual(len(confirmedTasks), 1)
        self.assertEqual(confirmedTasks[0].config.name, "video-2.mp4")
        self.assertEqual(
            confirmedTasks[0].snapshot().target,
            str(Path("downloads") / "video-2.mp4"),
        )


if __name__ == "__main__":
    _ = unittest.main()
