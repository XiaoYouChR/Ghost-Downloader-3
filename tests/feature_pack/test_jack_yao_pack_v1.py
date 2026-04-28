# pyright: reportImplicitOverride=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportAny=false, reportCallIssue=false, reportMissingTypeStubs=false, reportUnusedCallResult=false

from __future__ import annotations

import asyncio
import inspect
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from typing import cast
from unittest.mock import patch

_ = os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    _ = sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import QWidget
from qfluentwidgets import FluentIcon

from app.feature_pack.api import DefaultFeatureService
from app.feature_pack.api import FeaturePack
from app.feature_pack.api import Task
from app.feature_pack.api import TaskConfig
from app.feature_pack.api import TaskInput


def ensureApplication() -> QApplication:
    application = QApplication.instance()
    if application is not None:
        return cast(QApplication, application)

    return QApplication([])


class _FakeWindow(QWidget):
    resourceInterface: object | None
    subInterfaces: list[tuple[object, object, str]]

    def __init__(self) -> None:
        super().__init__()
        self.resourceInterface = None
        self.subInterfaces = []

    def addSubInterface(self, widget: object, icon: object, text: str) -> None:
        if isinstance(widget, QWidget):
            widget.setParent(self)
        self.subInterfaces.append((widget, icon, text))


class JackYaoPackV1Tests(unittest.TestCase):
    application: QApplication | None = None
    _temporaryDirectory: tempfile.TemporaryDirectory[str] | None = None
    workspace: Path = ROOT

    @classmethod
    def setUpClass(cls) -> None:
        cls.application = ensureApplication()

    def setUp(self) -> None:
        temporaryDirectory = tempfile.TemporaryDirectory()
        self._temporaryDirectory = temporaryDirectory
        self.addCleanup(temporaryDirectory.cleanup)
        self.workspace = Path(temporaryDirectory.name)
        shutil.copytree(ROOT / "features" / "jack_yao", self.workspace / "jack_yao")
        self.resetJackYaoModule()

    def resetJackYaoModule(self) -> None:
        for moduleName in list(sys.modules):
            if moduleName.startswith("_ghost_feature_pack_jack_yao"):
                del sys.modules[moduleName]

    def buildTaskInput(self, source: str = "jack-yao://resource") -> TaskInput:
        return TaskInput(
            config=TaskConfig(
                source=source,
                folder=self.workspace / "downloads",
                name="resource.bin",
            )
        )

    def loadService(self, window: _FakeWindow) -> DefaultFeatureService:
        def fakeRunCoroutine(coroutine: object, callback: object) -> None:
            if inspect.iscoroutine(coroutine):
                coroutine.close()
            if callable(callback):
                callback([], "")

        service = DefaultFeatureService(featuresPath=self.workspace)
        with patch("app.services.core_service.coreService.runCoroutine", side_effect=fakeRunCoroutine):
            service.loadPacks(window)
        return service

    def testJackYaoPackLoadsThroughV1ServiceAndInstallsResourcePage(self) -> None:
        window = _FakeWindow()
        self.addCleanup(window.close)
        self.addCleanup(window.deleteLater)

        service = self.loadService(window)

        pack = service.pack("jack_yao")
        self.assertIsInstance(pack, FeaturePack)
        self.assertIsNotNone(pack)
        if pack is None:
            raise AssertionError("jack_yao should load through the V1 service")
        self.assertEqual(pack.manifest.id, "jack_yao")
        self.assertEqual(len(window.subInterfaces), 1)

        widget, icon, text = window.subInterfaces[0]
        self.assertIs(widget, window.resourceInterface)
        self.assertEqual(icon, FluentIcon.CLOUD_DOWNLOAD)
        self.assertEqual(text, "资源下载")
        self.assertIsInstance(widget, QWidget)
        self.assertEqual(cast(QWidget, widget).objectName(), "ResourceInterface")

    def testJackYaoPackDoesNotParticipateInTaskRouting(self) -> None:
        window = _FakeWindow()
        self.addCleanup(window.close)
        self.addCleanup(window.deleteLater)
        service = self.loadService(window)

        pack = service.pack("jack_yao")
        self.assertIsNotNone(pack)
        if pack is None:
            raise AssertionError("jack_yao should load through the V1 service")

        taskInput = self.buildTaskInput()
        self.assertFalse(pack.accepts(taskInput.config.source))
        self.assertIsNone(asyncio.run(pack.createTask(taskInput)))
        self.assertFalse(pack.owns(cast(Task, object())))
        self.assertIsNone(service.packForSource(taskInput.config.source))

        with self.assertRaisesRegex(ValueError, "未找到可处理该来源的 FeaturePack"):
            _ = asyncio.run(service.createTask(taskInput))


if __name__ == "__main__":
    _ = unittest.main()
