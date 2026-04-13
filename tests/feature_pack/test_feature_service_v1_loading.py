from __future__ import annotations

# pyright: reportImplicitOverride=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false, reportPrivateUsage=false

import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    _ = sys.path.insert(0, str(ROOT))

from app.feature_pack.api import DefaultFeatureService
from app.feature_pack.api import FeaturePack
from app.feature_pack.api import PackLoadError


class _FakeWindow:
    def __init__(self) -> None:
        self.installed: list[str] = []


class FeatureServiceV1LoadingTests(unittest.TestCase):
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
        entryBody: str | None = None,
        extraFiles: dict[str, str] | None = None,
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

        if entryBody is not None:
            _ = (packDirectory / entry).write_text(textwrap.dedent(entryBody).strip() + "\n", encoding="utf-8")

        if extraFiles is not None:
            for relativePath, content in extraFiles.items():
                targetPath = packDirectory / relativePath
                targetPath.parent.mkdir(parents=True, exist_ok=True)
                _ = targetPath.write_text(textwrap.dedent(content).strip() + "\n", encoding="utf-8")

        return packDirectory

    def testLoadPacksInstantiatesPacksInDependencyOrderAndCachesInstances(self) -> None:
        _ = self.writePack(
            directoryName="base_pack",
            entryBody="""
            from app.feature_pack.api import FeaturePack, Task, TaskInput
            from .helper import installMessage


            class BasePack(FeaturePack):
                def accepts(self, source: str) -> bool:
                    return source.startswith("base:")

                async def createTask(self, data: TaskInput) -> Task | None:
                    return None

                def owns(self, task: Task) -> bool:
                    return False

                def install(self, window) -> None:
                    window.installed.append(installMessage(self.manifest.id))
            """,
            extraFiles={
                "helper.py": """
                def installMessage(packId: str) -> str:
                    return f"{packId}:installed"
                """
            },
        )
        _ = self.writePack(
            directoryName="child_pack",
            dependencies=("base_pack",),
            entryBody="""
            from app.feature_pack.api import FeaturePack, Task, TaskInput


            class ChildPack(FeaturePack):
                def __init__(self) -> None:
                    self.installCount = 0

                def accepts(self, source: str) -> bool:
                    return source.startswith("child:")

                async def createTask(self, data: TaskInput) -> Task | None:
                    return None

                def owns(self, task: Task) -> bool:
                    return False

                def install(self, window) -> None:
                    self.installCount += 1
                    window.installed.append(self.manifest.id)
            """,
        )
        service = self.createService()
        window = _FakeWindow()

        service.loadPacks(window)

        self.assertEqual(window.installed, ["base_pack:installed", "child_pack"])
        self.assertEqual(service._loadedPackOrder, ("base_pack", "child_pack"))
        basePack = service.pack("base_pack")
        childPack = service.pack("child_pack")
        self.assertIsNotNone(basePack)
        self.assertIsNotNone(childPack)
        if basePack is None or childPack is None:
            self.fail("loaded packs must be cached")
        self.assertIsInstance(basePack, FeaturePack)
        self.assertEqual(basePack.manifest.id, "base_pack")
        self.assertEqual(childPack.manifest.id, "child_pack")
        self.assertEqual(getattr(childPack, "installCount"), 1)
        self.assertIsNone(service.pack("missing_pack"))

        service.loadPacks(window)
        self.assertEqual(window.installed, ["base_pack:installed", "child_pack"])

    def testLoadPacksRaisesWhenEntryModuleHasNoNewFeaturePackSubclass(self) -> None:
        _ = self.writePack(
            directoryName="broken_pack",
            entryBody="""
            class NotAPack:
                pass
            """,
        )
        service = self.createService()

        with self.assertRaises(PackLoadError) as context:
            service.loadPacks(_FakeWindow())

        error = context.exception
        self.assertEqual(error.code, "missing-pack-class")
        self.assertEqual(error.packId, "broken_pack")
        self.assertIsNone(service.pack("broken_pack"))
        self.assertNotIn("_ghost_feature_pack_broken_pack", sys.modules)

    def testLoadPacksRaisesWhenManifestDoesNotMatchPackClass(self) -> None:
        _ = self.writePack(
            directoryName="mismatch_pack",
            entryBody="""
            from app.feature_pack.api import FeaturePack, Manifest, Task, TaskInput


            class MismatchPack(FeaturePack):
                manifest = Manifest(
                    id="other_pack",
                    name="Other Pack",
                    version="1.0.0",
                    api=1,
                )

                def accepts(self, source: str) -> bool:
                    return False

                async def createTask(self, data: TaskInput) -> Task | None:
                    return None

                def owns(self, task: Task) -> bool:
                    return False
            """,
        )
        service = self.createService()

        with self.assertRaises(PackLoadError) as context:
            service.loadPacks(_FakeWindow())

        error = context.exception
        self.assertEqual(error.code, "manifest-mismatch")
        self.assertEqual(error.packId, "mismatch_pack")
        self.assertNotIn("_ghost_feature_pack_mismatch_pack", sys.modules)

    def testLoadPacksRaisesWhenEntryModuleImportFails(self) -> None:
        _ = self.writePack(
            directoryName="import_fail_pack",
            entryBody="""
            raise RuntimeError("import exploded")
            """,
        )
        service = self.createService()

        with self.assertRaises(PackLoadError) as context:
            service.loadPacks(_FakeWindow())

        error = context.exception
        self.assertEqual(error.code, "module-load-failed")
        self.assertIn("import exploded", error.reason)
        self.assertEqual(error.packId, "import_fail_pack")
        self.assertNotIn("_ghost_feature_pack_import_fail_pack", sys.modules)

    def testLoadPacksRaisesWhenPackInitializationFails(self) -> None:
        _ = self.writePack(
            directoryName="init_fail_pack",
            entryBody="""
            from app.feature_pack.api import FeaturePack, Task, TaskInput


            class InitFailPack(FeaturePack):
                def __init__(self) -> None:
                    raise RuntimeError("boom during init")

                def accepts(self, source: str) -> bool:
                    return False

                async def createTask(self, data: TaskInput) -> Task | None:
                    return None

                def owns(self, task: Task) -> bool:
                    return False
            """,
        )
        service = self.createService()

        with self.assertRaises(PackLoadError) as context:
            service.loadPacks(_FakeWindow())

        error = context.exception
        self.assertEqual(error.code, "pack-init-failed")
        self.assertIn("boom during init", error.reason)
        self.assertNotIn("_ghost_feature_pack_init_fail_pack", sys.modules)

    def testLoadPacksRaisesWhenInstallFailsAndRollsBackEarlierPacks(self) -> None:
        _ = self.writePack(
            directoryName="first_pack",
            entryBody="""
            from app.feature_pack.api import FeaturePack, Task, TaskInput


            class FirstPack(FeaturePack):
                def accepts(self, source: str) -> bool:
                    return False

                async def createTask(self, data: TaskInput) -> Task | None:
                    return None

                def owns(self, task: Task) -> bool:
                    return False

                def install(self, window) -> None:
                    window.installed.append(self.manifest.id)
            """,
        )
        _ = self.writePack(
            directoryName="broken_pack",
            dependencies=("first_pack",),
            entryBody="""
            from app.feature_pack.api import FeaturePack, Task, TaskInput


            class BrokenPack(FeaturePack):
                def accepts(self, source: str) -> bool:
                    return False

                async def createTask(self, data: TaskInput) -> Task | None:
                    return None

                def owns(self, task: Task) -> bool:
                    return False

                def install(self, window) -> None:
                    raise RuntimeError("install failed")
            """,
        )
        service = self.createService()
        window = _FakeWindow()

        with self.assertRaises(PackLoadError) as context:
            service.loadPacks(window)

        error = context.exception
        self.assertEqual(error.code, "pack-install-failed")
        self.assertEqual(error.packId, "broken_pack")
        self.assertEqual(window.installed, ["first_pack"])
        self.assertEqual(service._loadedPackOrder, ())
        self.assertIsNone(service.pack("first_pack"))
        self.assertNotIn("_ghost_feature_pack_first_pack", sys.modules)
        self.assertNotIn("_ghost_feature_pack_broken_pack", sys.modules)


if __name__ == "__main__":
    _ = unittest.main()
