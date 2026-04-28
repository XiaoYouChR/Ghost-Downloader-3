# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportImplicitOverride=false

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import cast

_ = os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    _ = sys.path.insert(0, str(ROOT))

from app.feature_pack.api import DefaultFeatureService
from app.feature_pack.api import FeaturePack
from app.feature_pack.api import SettingSection
from app.feature_pack.api import TaskConfig
from app.feature_pack.api import TaskInput
from app.feature_pack.api import TaskStage


class _FakeWindow:
    def __init__(self) -> None:
        self.installed: list[str] = []


class CommunitySamplePackTests(unittest.TestCase):
    _temporaryDirectory: tempfile.TemporaryDirectory[str] | None = None
    workspace: Path = ROOT

    def setUp(self) -> None:
        temporaryDirectory = tempfile.TemporaryDirectory()
        self._temporaryDirectory = temporaryDirectory
        self.addCleanup(temporaryDirectory.cleanup)
        self.workspace = Path(temporaryDirectory.name)

    def createService(self) -> DefaultFeatureService:
        service = DefaultFeatureService(featuresPath=ROOT / "examples")
        service.loadPacks(_FakeWindow())
        return service

    def buildInput(
        self,
        *,
        source: str = "sample://hello-world",
        name: str = "hello.txt",
    ) -> TaskInput:
        return TaskInput(
            config=TaskConfig(
                source=source,
                folder=self.workspace / "downloads",
                name=name,
                headers={},
                proxies=None,
                chunks=1,
            ),
        )

    def testCommunitySamplePackLoadsThroughDefaultService(self) -> None:
        service = self.createService()

        pack = service.pack("community_sample_pack")

        self.assertIsInstance(pack, FeaturePack)
        assert pack is not None
        self.assertEqual(pack.manifest.id, "community_sample_pack")
        self.assertEqual(pack.manifest.schemes, ("sample",))
        self.assertEqual(pack.manifest.tasks, ("sample_echo",))
        self.assertEqual(pack.manifest.stages, ("sample_write",))
        self.assertIs(service.packForSource("sample://hello-world"), pack)

    def testCommunitySamplePackExposesSettingSection(self) -> None:
        service = self.createService()
        pack = service.pack("community_sample_pack")
        assert pack is not None

        section = pack.settingSection()

        self.assertIsInstance(section, SettingSection)
        section = cast(SettingSection, section)
        self.assertEqual(section.id, "community_sample_pack")
        self.assertEqual(section.title, "Community Sample Pack")
        self.assertEqual(len(section.items), 1)
        self.assertEqual(section.items[0].key, "status")

    def testCommunitySamplePackCreatesRunnableTaskWithAuthoringContracts(self) -> None:
        service = self.createService()

        task = asyncio.run(service.createTask(self.buildInput()))

        self.assertEqual(task.packId, "community_sample_pack")
        self.assertEqual(task.kind, "sample_echo")
        pack = service.pack("community_sample_pack")
        assert pack is not None
        self.assertTrue(pack.owns(task))
        self.assertEqual(task.config.name, "hello.txt")
        self.assertEqual(task.snapshot().target, str(self.workspace / "downloads" / "hello.txt"))
        self.assertEqual(len(task.stages), 1)
        self.assertIsInstance(task.stages[0], TaskStage)
        self.assertEqual(task.stages[0].kind, "sample_write")

        form = task.editForm("before")

        self.assertIsNotNone(form)
        assert form is not None
        self.assertEqual(form.title, "Edit sample task")
        self.assertEqual(
            [field.key for field in form.fields],
            ["source", "name", "folder"],
        )

        asyncio.run(task.run())

        outputPath = self.workspace / "downloads" / "hello.txt"
        self.assertEqual(outputPath.read_text(encoding="utf-8"), "hello-world\n")
        snapshot = task.snapshot()
        self.assertEqual(snapshot.state, "completed")
        self.assertEqual(snapshot.progress, 100.0)
        self.assertEqual(snapshot.stages[0].state, "completed")

    def testCommunitySamplePackRejectsUnsupportedSources(self) -> None:
        service = self.createService()

        self.assertIsNone(service.packForSource("https://example.com/file.txt"))
        with self.assertRaises(ValueError):
            _ = asyncio.run(
                service.createTask(
                    self.buildInput(source="https://example.com/file.txt")
                )
            )


if __name__ == "__main__":
    _ = unittest.main()
