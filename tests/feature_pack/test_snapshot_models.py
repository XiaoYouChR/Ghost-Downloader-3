from __future__ import annotations

import sys
import unittest
from dataclasses import FrozenInstanceError
from dataclasses import fields
from typing import Callable
from typing import cast


from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    _ = sys.path.insert(0, str(ROOT))

from app.feature_pack.api import StageSnapshot
from app.feature_pack.api import TaskSnapshot


class SnapshotModelTests(unittest.TestCase):
    def testStageSnapshotUsesContractFieldOrderAndDefaults(self) -> None:
        stageSnapshot = StageSnapshot(
            id="stage-1",
            kind="download",
            name="下载阶段",
            state="running",
            progress=25.5,
            doneBytes=1024,
            speed=512,
        )

        self.assertEqual(
            [field.name for field in fields(StageSnapshot)],
            [
                "id",
                "kind",
                "name",
                "state",
                "progress",
                "doneBytes",
                "speed",
                "error",
            ],
        )
        self.assertEqual(stageSnapshot.id, "stage-1")
        self.assertEqual(stageSnapshot.kind, "download")
        self.assertEqual(stageSnapshot.name, "下载阶段")
        self.assertEqual(stageSnapshot.state, "running")
        self.assertEqual(stageSnapshot.progress, 25.5)
        self.assertEqual(stageSnapshot.doneBytes, 1024)
        self.assertEqual(stageSnapshot.speed, 512)
        self.assertEqual(stageSnapshot.error, "")

    def testStageSnapshotRequiresKeywordArguments(self) -> None:
        stageSnapshotFactory = cast(Callable[..., object], StageSnapshot)

        with self.assertRaises(TypeError):
            _ = stageSnapshotFactory(
                "stage-1",
                "download",
                "下载阶段",
                "running",
                25.5,
                1024,
                512,
            )

    def testStageSnapshotIsFrozen(self) -> None:
        stageSnapshot = StageSnapshot(
            id="stage-1",
            kind="download",
            name="下载阶段",
            state="running",
            progress=25.5,
            doneBytes=1024,
            speed=512,
        )

        with self.assertRaises(FrozenInstanceError):
            stageSnapshot.__setattr__("state", "completed")

    def testTaskSnapshotUsesContractFieldOrderAndDefaults(self) -> None:
        taskSnapshot = TaskSnapshot(
            id="task-1",
            packId="http_pack",
            kind="single_file",
            name="video.mp4",
            state="running",
            progress=50.0,
            doneBytes=2048,
            totalBytes=4096,
            canPause=True,
            target="downloads/video.mp4",
        )

        self.assertEqual(
            [field.name for field in fields(TaskSnapshot)],
            [
                "id",
                "packId",
                "kind",
                "name",
                "state",
                "progress",
                "doneBytes",
                "totalBytes",
                "canPause",
                "target",
                "stages",
            ],
        )
        self.assertEqual(taskSnapshot.id, "task-1")
        self.assertEqual(taskSnapshot.packId, "http_pack")
        self.assertEqual(taskSnapshot.kind, "single_file")
        self.assertEqual(taskSnapshot.name, "video.mp4")
        self.assertEqual(taskSnapshot.state, "running")
        self.assertEqual(taskSnapshot.progress, 50.0)
        self.assertEqual(taskSnapshot.doneBytes, 2048)
        self.assertEqual(taskSnapshot.totalBytes, 4096)
        self.assertTrue(taskSnapshot.canPause)
        self.assertEqual(taskSnapshot.target, "downloads/video.mp4")
        self.assertEqual(taskSnapshot.stages, ())

    def testTaskSnapshotRequiresKeywordArguments(self) -> None:
        taskSnapshotFactory = cast(Callable[..., object], TaskSnapshot)

        with self.assertRaises(TypeError):
            _ = taskSnapshotFactory(
                "task-1",
                "http_pack",
                "single_file",
                "video.mp4",
                "running",
                50.0,
                2048,
                4096,
                True,
                "downloads/video.mp4",
            )

    def testTaskSnapshotIsFrozen(self) -> None:
        taskSnapshot = TaskSnapshot(
            id="task-1",
            packId="http_pack",
            kind="single_file",
            name="video.mp4",
            state="running",
            progress=50.0,
            doneBytes=2048,
            totalBytes=4096,
            canPause=True,
            target="downloads/video.mp4",
        )

        with self.assertRaises(FrozenInstanceError):
            taskSnapshot.__setattr__("progress", 100.0)

    def testTaskSnapshotAcceptsStageSnapshotTuple(self) -> None:
        stageSnapshots = (
            StageSnapshot(
                id="stage-1",
                kind="resolve",
                name="解析",
                state="completed",
                progress=100.0,
                doneBytes=0,
                speed=0,
            ),
            StageSnapshot(
                id="stage-2",
                kind="download",
                name="下载",
                state="running",
                progress=40.0,
                doneBytes=4096,
                speed=1024,
            ),
        )

        taskSnapshot = TaskSnapshot(
            id="task-2",
            packId="m3u8_pack",
            kind="single_file",
            name="episode.ts",
            state="running",
            progress=70.0,
            doneBytes=4096,
            totalBytes=8192,
            canPause=False,
            target="downloads/episode.ts",
            stages=stageSnapshots,
        )

        self.assertEqual(taskSnapshot.stages, stageSnapshots)
        self.assertEqual(taskSnapshot.stages[0].state, "completed")
        self.assertEqual(taskSnapshot.stages[1].doneBytes, 4096)


if __name__ == "__main__":
    _ = unittest.main()
