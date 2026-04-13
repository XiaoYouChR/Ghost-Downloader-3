# pyright: reportImplicitOverride=false, reportInconsistentConstructor=false

from __future__ import annotations

import asyncio
import sys
import unittest
from abc import ABC
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    _ = sys.path.insert(0, str(ROOT))

from app.feature_pack.api import FeaturePack
from app.feature_pack.api import Manifest
from app.feature_pack.api import StageSnapshot
from app.feature_pack.api import Task
from app.feature_pack.api import TaskConfig
from app.feature_pack.api import TaskInput
from app.feature_pack.api import TaskSnapshot
from app.feature_pack.api import TaskStage


class DemoTaskStage(TaskStage):
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
    def __init__(self, *, config: TaskConfig) -> None:
        super().__init__(
            id="task-1",
            packId="demo_pack",
            kind="demo",
            version=1,
            config=config,
            stages=[
                DemoTaskStage(
                    id="stage-1",
                    kind="download",
                    version=1,
                    name="下载阶段",
                )
            ],
        )

    def syncOutput(self) -> None:
        return None

    def reset(self) -> None:
        return None

    def snapshot(self) -> TaskSnapshot:
        return TaskSnapshot(
            id=self.id,
            packId=self.packId,
            kind=self.kind,
            name=self.config.name,
            state="waiting",
            progress=0.0,
            doneBytes=0,
            totalBytes=0,
            canPause=self.canPause(),
            target=str(self.config.folder / self.config.name),
        )


class MinimalFeaturePack(FeaturePack):
    manifest: Manifest = Manifest(
        id="demo_pack",
        name="Demo Pack",
        version="1.0.0",
        api=1,
    )

    def accepts(self, source: str) -> bool:
        return source.startswith("demo:")

    async def createTask(self, data: TaskInput) -> Task | None:
        if not data.config.source:
            return None
        return DemoTask(config=data.config)

    def owns(self, task: Task) -> bool:
        if not isinstance(task, DemoTask):
            return False
        return task.packId == self.manifest.id


class MissingOwnsPack(FeaturePack, ABC):
    manifest: Manifest = Manifest(
        id="broken_pack",
        name="Broken Pack",
        version="1.0.0",
        api=1,
    )

    def accepts(self, source: str) -> bool:
        return bool(source)

    async def createTask(self, data: TaskInput) -> Task | None:
        return DemoTask(config=data.config)


class FeaturePackInterfaceTests(unittest.TestCase):
    def testOnlyCoreMethodsAreAbstract(self) -> None:
        self.assertEqual(
            FeaturePack.__abstractmethods__,
            frozenset({"accepts", "createTask", "owns"}),
        )

    def testMinimalImplementationUsesOptionalUiHooks(self) -> None:
        packInstance = MinimalFeaturePack()
        taskInput = TaskInput(
            config=TaskConfig(
                source="demo:source",
                folder=Path("downloads"),
                name="demo.bin",
            )
        )

        self.assertTrue(packInstance.accepts("demo:source"))
        self.assertFalse(packInstance.accepts("http://example.com"))
        createdTask = asyncio.run(packInstance.createTask(taskInput))
        self.assertIsNotNone(createdTask)
        self.assertIsInstance(createdTask, DemoTask)
        if createdTask is None:
            self.fail("createTask() returned None for a supported source")

        self.assertEqual(createdTask.packId, "demo_pack")
        self.assertEqual(createdTask.config.source, "demo:source")
        self.assertTrue(packInstance.owns(createdTask))
        otherTask = DemoTask(
            config=TaskConfig(
                source="demo:other",
                folder=Path("downloads"),
                name="other.bin",
            )
        )
        otherTask.packId = "other_pack"
        self.assertFalse(packInstance.owns(otherTask))
        self.assertIsNone(packInstance.settingSection())
        self.assertIsNone(packInstance.createTaskCard(createdTask))
        self.assertIsNone(packInstance.createResultCard(createdTask))
        self.assertIsNone(packInstance.install(object()))

    def testMissingCoreMethodKeepsSubclassAbstract(self) -> None:
        self.assertEqual(MissingOwnsPack.__abstractmethods__, frozenset({"owns"}))


if __name__ == "__main__":
    _ = unittest.main()
