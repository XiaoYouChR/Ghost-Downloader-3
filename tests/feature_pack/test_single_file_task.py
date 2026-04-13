# pyright: reportImplicitOverride=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnannotatedClassAttribute=false, reportUnusedCallResult=false, reportInconsistentConstructor=false, reportUnnecessaryCast=false, reportAny=false

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import cast


ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    _ = sys.path.insert(0, str(ROOT))

from app.feature_pack.api import SingleFileTask
from app.feature_pack.api import StageSnapshot
from app.feature_pack.api import TaskConfig
from app.feature_pack.api import TaskSnapshot
from app.feature_pack.api import TaskStage


class DemoSingleFileStage(TaskStage):
    def __init__(self, *, id: str = "stage-1") -> None:
        super().__init__(id=id, kind="download", version=1, name=f"阶段 {id}")
        self.state = "waiting"
        self.progress = 0.0
        self.doneBytes = 0
        self.speed = 0
        self.error = ""
        self.configures: list[TaskConfig] = []
        self.syncedTargets: list[str] = []

    async def run(self) -> None:
        return None

    def reset(self) -> None:
        self.state = "waiting"
        self.progress = 0.0
        self.doneBytes = 0
        self.speed = 0
        self.error = ""

    def configure(self, config: TaskConfig) -> None:
        self.configures.append(config)

    def snapshot(self) -> StageSnapshot:
        return StageSnapshot(
            id=self.id,
            kind=self.kind,
            name=self.name,
            state=self.state,
            progress=self.progress,
            doneBytes=self.doneBytes,
            speed=self.speed,
            error=self.error,
        )


class MissingSingleFileSnapshotTask(SingleFileTask):
    def syncOutput(self) -> None:
        return None

    def reset(self) -> None:
        return None


class DemoSingleFileTask(SingleFileTask):
    def __init__(self, *, config: TaskConfig, stages: list[TaskStage]) -> None:
        self.syncOutputCalls = 0
        self.state = "waiting"
        self.progress = 0.0
        self.doneBytes = 0
        self.totalBytes = 1024
        self.lastTarget = ""
        super().__init__(
            id="task-1",
            packId="demo_pack",
            kind="single_file",
            version=1,
            config=config,
            stages=stages,
        )

    def syncOutput(self) -> None:
        self.syncOutputCalls += 1
        self.lastTarget = str(self.path)
        for stage in self.stages:
            if isinstance(stage, DemoSingleFileStage):
                stage.syncedTargets.append(self.lastTarget)

    def reset(self) -> None:
        self.state = "waiting"
        self.progress = 0.0
        self.doneBytes = 0

    def snapshot(self) -> TaskSnapshot:
        return TaskSnapshot(
            id=self.id,
            packId=self.packId,
            kind=self.kind,
            name=self.filename,
            state=self.state,
            progress=self.progress,
            doneBytes=self.doneBytes,
            totalBytes=self.totalBytes,
            canPause=self.canPause(),
            target=str(self.path),
            stages=tuple(stage.snapshot() for stage in self.stages),
        )


class SingleFileTaskTests(unittest.TestCase):
    def makeConfig(self) -> TaskConfig:
        return TaskConfig(
            source="https://example.com/archive.zip",
            folder=Path("downloads"),
            name="archive.zip",
            headers={"User-Agent": "Ghost Downloader"},
            proxies={"https": "http://127.0.0.1:7890"},
            chunks=4,
        )

    def testSingleFileTaskKeepsSyncOutputAsAbstractHook(self) -> None:
        self.assertEqual(
            getattr(SingleFileTask, "__abstractmethods__", frozenset()),
            frozenset({"reset", "snapshot", "syncOutput"}),
        )
        self.assertEqual(
            getattr(MissingSingleFileSnapshotTask, "__abstractmethods__", frozenset()),
            frozenset({"snapshot"}),
        )

        with self.assertRaises(TypeError):
            _ = SingleFileTask(
                id="task-1",
                packId="demo_pack",
                kind="single_file",
                version=1,
                config=self.makeConfig(),
                stages=[],
            )

        with self.assertRaises(TypeError):
            _ = MissingSingleFileSnapshotTask(
                id="task-2",
                packId="demo_pack",
                kind="single_file",
                version=1,
                config=self.makeConfig(),
                stages=[],
            )

    def testSingleFileTaskExposesFolderFilenameAndPath(self) -> None:
        workflow = DemoSingleFileTask(
            config=self.makeConfig(),
            stages=[DemoSingleFileStage()],
        )

        self.assertEqual(workflow.folder, Path("downloads"))
        self.assertEqual(workflow.filename, "archive.zip")
        self.assertEqual(workflow.path, Path("downloads") / "archive.zip")
        self.assertEqual(workflow.snapshot().target, str(Path("downloads") / "archive.zip"))

    def testSingleFileTaskRenameUsesConfigureAndSyncOutput(self) -> None:
        stage = DemoSingleFileStage()
        workflow = DemoSingleFileTask(config=self.makeConfig(), stages=[stage])

        workflow.rename("renamed.zip")

        self.assertEqual(workflow.filename, "renamed.zip")
        self.assertEqual(workflow.path, Path("downloads") / "renamed.zip")
        self.assertEqual(workflow.syncOutputCalls, 1)
        self.assertEqual(len(stage.configures), 1)
        self.assertEqual(stage.configures[0].name, "renamed.zip")
        self.assertEqual(stage.syncedTargets, [str(Path("downloads") / "renamed.zip")])

    def testSingleFileTaskMoveUsesConfigureAndSyncOutput(self) -> None:
        stage = DemoSingleFileStage()
        workflow = DemoSingleFileTask(config=self.makeConfig(), stages=[stage])

        workflow.move(Path("archive"))

        self.assertEqual(workflow.folder, Path("archive"))
        self.assertEqual(workflow.path, Path("archive") / "archive.zip")
        self.assertEqual(workflow.syncOutputCalls, 1)
        self.assertEqual(len(stage.configures), 1)
        self.assertEqual(stage.configures[0].folder, Path("archive"))
        self.assertEqual(stage.syncedTargets, [str(Path("archive") / "archive.zip")])

    def testSingleFileTaskCanCombineRenameAndMoveWithoutExtraGlue(self) -> None:
        stage = DemoSingleFileStage()
        workflow = DemoSingleFileTask(config=self.makeConfig(), stages=[stage])

        workflow.rename("episode-01.mp4")
        workflow.move(Path("videos"))

        self.assertEqual(workflow.folder, Path("videos"))
        self.assertEqual(workflow.filename, "episode-01.mp4")
        self.assertEqual(workflow.path, Path("videos") / "episode-01.mp4")
        self.assertEqual(workflow.lastTarget, str(Path("videos") / "episode-01.mp4"))
        self.assertEqual(workflow.syncOutputCalls, 2)
        configuredNames = [config.name for config in stage.configures]
        configuredFolders = [config.folder for config in stage.configures]
        self.assertEqual(configuredNames, ["episode-01.mp4", "episode-01.mp4"])
        self.assertEqual(configuredFolders, [Path("downloads"), Path("videos")])
        self.assertEqual(
            stage.syncedTargets,
            [
                str(Path("downloads") / "episode-01.mp4"),
                str(Path("videos") / "episode-01.mp4"),
            ],
        )
        snapshot = workflow.snapshot()
        self.assertEqual(snapshot.name, "episode-01.mp4")
        self.assertEqual(snapshot.target, str(Path("videos") / "episode-01.mp4"))
        stageSnapshots = tuple(cast(StageSnapshot, item) for item in snapshot.stages)
        self.assertEqual(len(stageSnapshots), 1)


if __name__ == "__main__":
    _ = unittest.main()
