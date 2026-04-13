# pyright: reportImplicitOverride=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnannotatedClassAttribute=false, reportUnusedCallResult=false, reportInconsistentConstructor=false, reportUnnecessaryCast=false, reportAny=false

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import cast


ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    _ = sys.path.insert(0, str(ROOT))

from app.feature_pack.api import MultiFileTask
from app.feature_pack.api import StageSnapshot
from app.feature_pack.api import TaskConfig
from app.feature_pack.api import TaskFile
from app.feature_pack.api import TaskSnapshot
from app.feature_pack.api import TaskStage


class DemoMultiFileStage(TaskStage):
    def __init__(self, *, id: str = "stage-1") -> None:
        super().__init__(id=id, kind="download", version=1, name=f"阶段 {id}")
        self.state = "waiting"
        self.progress = 0.0
        self.doneBytes = 0
        self.speed = 0
        self.error = ""
        self.configures: list[TaskConfig] = []
        self.syncedRoots: list[str] = []

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


class MissingMultiFileSnapshotTask(MultiFileTask):
    def syncOutput(self) -> None:
        return None

    def reset(self) -> None:
        return None


class DemoMultiFileTask(MultiFileTask):
    def __init__(
        self,
        *,
        config: TaskConfig,
        stages: list[TaskStage],
        files: list[TaskFile],
    ) -> None:
        self.syncOutputCalls = 0
        self.state = "waiting"
        self.progress = 0.0
        self.doneBytes = 0
        self.totalBytes = sum(file.size for file in files)
        self.lastRoot = ""
        super().__init__(
            id="task-1",
            packId="demo_pack",
            kind="multi_file",
            version=1,
            config=config,
            stages=stages,
            files=files,
        )

    def syncOutput(self) -> None:
        self.syncOutputCalls += 1
        self.lastRoot = str(self.root)
        for stage in self.stages:
            if isinstance(stage, DemoMultiFileStage):
                stage.syncedRoots.append(self.lastRoot)

    def reset(self) -> None:
        self.state = "waiting"
        self.progress = 0.0
        self.doneBytes = 0

    def snapshot(self) -> TaskSnapshot:
        return TaskSnapshot(
            id=self.id,
            packId=self.packId,
            kind=self.kind,
            name=self.config.name,
            state=self.state,
            progress=self.progress,
            doneBytes=self.doneBytes,
            totalBytes=self.totalBytes,
            canPause=self.canPause(),
            target=str(self.root),
            stages=tuple(stage.snapshot() for stage in self.stages),
        )


class MultiFileTaskTests(unittest.TestCase):
    def makeConfig(self) -> TaskConfig:
        return TaskConfig(
            source="magnet:?xt=urn:btih:demo",
            folder=Path("downloads"),
            name="demo-torrent",
            headers={"User-Agent": "Ghost Downloader"},
            proxies={"https": "http://127.0.0.1:7890"},
            chunks=4,
        )

    def makeFiles(self) -> list[TaskFile]:
        return [
            TaskFile(
                id="file-1",
                path="Season 1/episode-01.mkv",
                size=1024,
                selected=True,
            ),
            TaskFile(
                id="file-2",
                path="Season 1/episode-02.mkv",
                size=2048,
                selected=False,
            ),
            TaskFile(
                id="file-3",
                path="Season 1/episode-03.mkv",
                size=4096,
                selected=True,
            ),
        ]

    def testMultiFileTaskKeepsTaskAbstractRequirements(self) -> None:
        self.assertEqual(
            getattr(MultiFileTask, "__abstractmethods__", frozenset()),
            frozenset({"reset", "snapshot", "syncOutput"}),
        )
        self.assertEqual(
            getattr(MissingMultiFileSnapshotTask, "__abstractmethods__", frozenset()),
            frozenset({"snapshot"}),
        )

        with self.assertRaises(TypeError):
            _ = MultiFileTask(
                id="task-1",
                packId="demo_pack",
                kind="multi_file",
                version=1,
                config=self.makeConfig(),
                stages=[],
                files=[],
            )

        with self.assertRaises(TypeError):
            _ = MissingMultiFileSnapshotTask(
                id="task-2",
                packId="demo_pack",
                kind="multi_file",
                version=1,
                config=self.makeConfig(),
                stages=[],
                files=[],
            )

    def testMultiFileTaskExposesFilesRootAndSelectionSummary(self) -> None:
        files = self.makeFiles()
        workflow = DemoMultiFileTask(
            config=self.makeConfig(),
            stages=[DemoMultiFileStage()],
            files=files,
        )

        self.assertIs(workflow.files, files)
        self.assertEqual(workflow.root, Path("downloads") / "demo-torrent")
        self.assertEqual(workflow.fileCount, 3)
        self.assertEqual(workflow.selectedCount, 2)
        self.assertEqual(workflow.selectedIds, {"file-1", "file-3"})
        self.assertEqual(workflow.snapshot().target, str(Path("downloads") / "demo-torrent"))

    def testMultiFileTaskSelectReplacesSelectionByStableIds(self) -> None:
        workflow = DemoMultiFileTask(
            config=self.makeConfig(),
            stages=[DemoMultiFileStage()],
            files=self.makeFiles(),
        )

        workflow.select({"file-2"})

        self.assertEqual(workflow.selectedCount, 1)
        self.assertEqual(workflow.selectedIds, {"file-2"})
        self.assertEqual([file.selected for file in workflow.files], [False, True, False])

    def testMultiFileTaskSelectRejectsUnknownIdsExplicitly(self) -> None:
        workflow = DemoMultiFileTask(
            config=self.makeConfig(),
            stages=[DemoMultiFileStage()],
            files=self.makeFiles(),
        )

        with self.assertRaisesRegex(ValueError, "Unknown task file ids: missing-file"):
            workflow.select({"file-1", "missing-file"})

        self.assertEqual(workflow.selectedIds, {"file-1", "file-3"})

    def testMultiFileTaskConfigureKeepsRootSyncAndSelectionStatisticsSeparate(self) -> None:
        stage = DemoMultiFileStage()
        workflow = DemoMultiFileTask(
            config=self.makeConfig(),
            stages=[stage],
            files=self.makeFiles(),
        )

        workflow.select({"file-2", "file-3"})
        workflow.configure(
            TaskConfig(
                source=workflow.config.source,
                folder=Path("archive"),
                name="season-1",
                headers=workflow.config.headers,
                proxies=workflow.config.proxies,
                chunks=workflow.config.chunks,
            )
        )

        self.assertEqual(workflow.root, Path("archive") / "season-1")
        self.assertEqual(workflow.selectedCount, 2)
        self.assertEqual(workflow.selectedIds, {"file-2", "file-3"})
        self.assertEqual(workflow.syncOutputCalls, 1)
        self.assertEqual(stage.configures[-1].folder, Path("archive"))
        self.assertEqual(stage.configures[-1].name, "season-1")
        self.assertEqual(stage.syncedRoots, [str(Path("archive") / "season-1")])
        snapshot = workflow.snapshot()
        self.assertEqual(snapshot.target, str(Path("archive") / "season-1"))
        stageSnapshots = tuple(cast(StageSnapshot, item) for item in snapshot.stages)
        self.assertEqual(len(stageSnapshots), 1)


if __name__ == "__main__":
    _ = unittest.main()
