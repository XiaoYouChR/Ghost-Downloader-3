from __future__ import annotations

# pyright: reportImplicitOverride=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false, reportPrivateUsage=false, reportInconsistentConstructor=false

import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    _ = sys.path.insert(0, str(ROOT))

from app.feature_pack.api import DefaultFeatureService
from app.feature_pack.api import StageSnapshot
from app.feature_pack.api import Task
from app.feature_pack.api import TaskConfig
from app.feature_pack.api import TaskSnapshot
from app.feature_pack.api import TaskStage


class _FakeWindow:
    def __init__(self) -> None:
        self.installed: list[str] = []


class _DemoStage(TaskStage):
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


class _DemoTask(Task):
    def __init__(self, *, packId: str, source: str = "demo:source") -> None:
        super().__init__(
            id=f"{packId}-task",
            packId=packId,
            kind="demo",
            version=1,
            config=TaskConfig(
                source=source,
                folder=Path("downloads"),
                name="demo.bin",
            ),
            stages=[
                _DemoStage(
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


class FeatureServiceV1RoutingTests(unittest.TestCase):
    _temporaryDirectory: tempfile.TemporaryDirectory[str] | None = None
    featuresPath: Path = ROOT

    def setUp(self) -> None:
        temporaryDirectory = tempfile.TemporaryDirectory()
        self._temporaryDirectory = temporaryDirectory
        self.addCleanup(temporaryDirectory.cleanup)
        self.featuresPath = Path(temporaryDirectory.name)

    def createService(self) -> DefaultFeatureService:
        return DefaultFeatureService(featuresPath=self.featuresPath)

    def writePack(
        self,
        *,
        directoryName: str,
        packId: str | None = None,
        dependencies: tuple[str, ...] = (),
        entry: str = "pack.py",
        entryBody: str,
    ) -> Path:
        packDirectory = self.featuresPath / directoryName
        packDirectory.mkdir(parents=True, exist_ok=True)

        manifestBody = textwrap.dedent(
            f"""
            [pack]
            id = "{packId or directoryName}"
            name = "{directoryName}"
            version = "1.0.0"
            api = 1
            entry = "{entry}"
            dependencies = [{", ".join(f'"{dependency}"' for dependency in dependencies)}]
            """
        ).strip()
        _ = (packDirectory / "manifest.toml").write_text(manifestBody + "\n", encoding="utf-8")
        _ = (packDirectory / entry).write_text(textwrap.dedent(entryBody).strip() + "\n", encoding="utf-8")
        return packDirectory

    def loadService(self) -> DefaultFeatureService:
        service = self.createService()
        service.loadPacks(_FakeWindow())
        return service

    def testPackForSourceUsesAcceptsAndDependencyOrderedLoadedPacks(self) -> None:
        _ = self.writePack(
            directoryName="base_pack",
            entryBody="""
            from app.feature_pack.api import FeaturePack, Task, TaskInput


            class BasePack(FeaturePack):
                def accepts(self, source: str) -> bool:
                    return source.startswith("demo:")

                async def createTask(self, data: TaskInput) -> Task | None:
                    return None

                def owns(self, task: Task) -> bool:
                    return False
            """,
        )
        _ = self.writePack(
            directoryName="child_pack",
            dependencies=("base_pack",),
            entryBody="""
            from app.feature_pack.api import FeaturePack, Task, TaskInput


            class ChildPack(FeaturePack):
                def accepts(self, source: str) -> bool:
                    return source.startswith("demo:")

                async def createTask(self, data: TaskInput) -> Task | None:
                    return None

                def owns(self, task: Task) -> bool:
                    return False
            """,
        )
        service = self.loadService()

        pack = service.packForSource("demo:video")

        self.assertIsNotNone(pack)
        if pack is None:
            self.fail("packForSource() should route to the first matching pack")
        self.assertEqual(pack.manifest.id, "base_pack")

    def testPackForSourceReturnsNoneWhenNoPackAcceptsSource(self) -> None:
        _ = self.writePack(
            directoryName="http_pack",
            entryBody="""
            from app.feature_pack.api import FeaturePack, Task, TaskInput


            class HttpPack(FeaturePack):
                def accepts(self, source: str) -> bool:
                    return source.startswith("http:")

                async def createTask(self, data: TaskInput) -> Task | None:
                    return None

                def owns(self, task: Task) -> bool:
                    return False
            """,
        )
        service = self.loadService()

        self.assertIsNone(service.packForSource("demo:video"))

    def testPackForSourceSkipsPackWhenAcceptsRaises(self) -> None:
        _ = self.writePack(
            directoryName="broken_pack",
            entryBody="""
            from app.feature_pack.api import FeaturePack, Task, TaskInput


            class BrokenPack(FeaturePack):
                def accepts(self, source: str) -> bool:
                    raise RuntimeError("accepts exploded")

                async def createTask(self, data: TaskInput) -> Task | None:
                    return None

                def owns(self, task: Task) -> bool:
                    return False
            """,
        )
        _ = self.writePack(
            directoryName="fallback_pack",
            entryBody="""
            from app.feature_pack.api import FeaturePack, Task, TaskInput


            class FallbackPack(FeaturePack):
                def accepts(self, source: str) -> bool:
                    return source.startswith("demo:")

                async def createTask(self, data: TaskInput) -> Task | None:
                    return None

                def owns(self, task: Task) -> bool:
                    return False
            """,
        )
        service = self.loadService()

        pack = service.packForSource("demo:video")

        self.assertIsNotNone(pack)
        if pack is None:
            self.fail("packForSource() should continue after one pack raises")
        self.assertEqual(pack.manifest.id, "fallback_pack")

    def testPackForTaskUsesOwnsSemantics(self) -> None:
        _ = self.writePack(
            directoryName="demo_pack",
            entryBody="""
            from app.feature_pack.api import FeaturePack, Task, TaskInput


            class DemoPack(FeaturePack):
                def accepts(self, source: str) -> bool:
                    return False

                async def createTask(self, data: TaskInput) -> Task | None:
                    return None

                def owns(self, task: Task) -> bool:
                    return task.packId == self.manifest.id
            """,
        )
        service = self.loadService()
        task = _DemoTask(packId="demo_pack")

        pack = service.packForTask(task)

        self.assertIsNotNone(pack)
        if pack is None:
            self.fail("packForTask() should route to the owning pack")
        self.assertEqual(pack.manifest.id, "demo_pack")

    def testPackForTaskReturnsNoneWhenNoPackOwnsTask(self) -> None:
        _ = self.writePack(
            directoryName="demo_pack",
            entryBody="""
            from app.feature_pack.api import FeaturePack, Task, TaskInput


            class DemoPack(FeaturePack):
                def accepts(self, source: str) -> bool:
                    return False

                async def createTask(self, data: TaskInput) -> Task | None:
                    return None

                def owns(self, task: Task) -> bool:
                    return False
            """,
        )
        service = self.loadService()

        self.assertIsNone(service.packForTask(_DemoTask(packId="other_pack")))

    def testPackForTaskSkipsPackWhenOwnsRaises(self) -> None:
        _ = self.writePack(
            directoryName="broken_pack",
            entryBody="""
            from app.feature_pack.api import FeaturePack, Task, TaskInput


            class BrokenPack(FeaturePack):
                def accepts(self, source: str) -> bool:
                    return False

                async def createTask(self, data: TaskInput) -> Task | None:
                    return None

                def owns(self, task: Task) -> bool:
                    raise RuntimeError("owns exploded")
            """,
        )
        _ = self.writePack(
            directoryName="demo_pack",
            entryBody="""
            from app.feature_pack.api import FeaturePack, Task, TaskInput


            class DemoPack(FeaturePack):
                def accepts(self, source: str) -> bool:
                    return False

                async def createTask(self, data: TaskInput) -> Task | None:
                    return None

                def owns(self, task: Task) -> bool:
                    return task.packId == self.manifest.id
            """,
        )
        service = self.loadService()
        task = _DemoTask(packId="demo_pack")

        pack = service.packForTask(task)

        self.assertIsNotNone(pack)
        if pack is None:
            self.fail("packForTask() should continue after one pack raises")
        self.assertEqual(pack.manifest.id, "demo_pack")

    def testPackForSourceAndTaskReturnNoneBeforePacksAreLoaded(self) -> None:
        service = self.createService()

        self.assertIsNone(service.packForSource("demo:video"))
        self.assertIsNone(service.packForTask(_DemoTask(packId="demo_pack")))


if __name__ == "__main__":
    _ = unittest.main()
