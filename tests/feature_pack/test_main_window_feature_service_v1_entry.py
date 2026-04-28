# pyright: reportImplicitOverride=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportPrivateUsage=false, reportAny=false, reportUnannotatedClassAttribute=false, reportInconsistentConstructor=false, reportArgumentType=false, reportOptionalMemberAccess=false, reportInvalidCast=false, reportAttributeAccessIssue=false

from __future__ import annotations

import os
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from typing import cast
from unittest.mock import patch

_ = os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    _ = sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import QVBoxLayout
from PySide6.QtWidgets import QWidget

from app.feature_pack.api import DefaultFeatureService
from app.feature_pack.api import StageSnapshot
from app.feature_pack.api import Task
from app.feature_pack.api import TaskConfig
from app.feature_pack.api import TaskSnapshot
from app.feature_pack.api import TaskStage
from app.services.feature_service import HostFeatureService
from app.services.feature_service import featureService
from app.view.windows.main_window import MainWindow


def ensureApplication() -> QApplication:
    application = QApplication.instance()
    if application is not None:
        return cast(QApplication, application)

    return QApplication([])


class _FakeSettingPage:
    def __init__(self) -> None:
        self.container = QWidget()
        self.vBoxLayout = QVBoxLayout(self.container)


class _FakeWindow:
    def __init__(self) -> None:
        self.installed: list[str] = []
        self.settingPage = _FakeSettingPage()


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
    def __init__(self) -> None:
        self.state = "waiting"
        self.progress = 0.0
        self.doneBytes = 0
        self.totalBytes = 0
        self.target = ""
        super().__init__(
            id="demo-task",
            packId="demo_pack",
            kind="demo",
            version=1,
            config=TaskConfig(
                source="demo:source",
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
        self.syncOutput()

    @property
    def title(self) -> str:
        return self.config.name

    def syncOutput(self) -> None:
        self.target = str(self.config.folder / self.config.name)

    def reset(self) -> None:
        self.state = "waiting"

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
            target=self.target,
            stages=tuple(stage.snapshot() for stage in self.stages),
        )


class _RecordingCard:
    def __init__(self) -> None:
        self.resumeCalls = 0

    def resumeTask(self) -> None:
        self.resumeCalls += 1


class _RecordingFeatureService:
    def __init__(self, card: _RecordingCard) -> None:
        self.card = card
        self.calls: list[tuple[Task, object]] = []

    def createTaskCard(self, task: Task, parent: object) -> _RecordingCard:
        self.calls.append((task, parent))
        return self.card


class _RecordingTaskRecorder:
    def __init__(self) -> None:
        self.addCalls: list[tuple[Task, bool]] = []
        self.flushCalls = 0

    def add(self, task: Task, flush: bool = True) -> None:
        self.addCalls.append((task, flush))

    def flush(self) -> None:
        self.flushCalls += 1


class _RecordingTaskPage:
    def __init__(self) -> None:
        self.cards: list[object] = []

    def addCard(self, card: object) -> None:
        self.cards.append(card)


class FeatureServiceV1EntryTests(unittest.TestCase):
    application: QApplication | None = None
    _temporaryDirectory: tempfile.TemporaryDirectory[str] | None = None
    featuresPath: Path = ROOT

    @classmethod
    def setUpClass(cls) -> None:
        cls.application = ensureApplication()

    def setUp(self) -> None:
        temporaryDirectory = tempfile.TemporaryDirectory()
        self._temporaryDirectory = temporaryDirectory
        self.addCleanup(temporaryDirectory.cleanup)
        self.featuresPath = Path(temporaryDirectory.name)

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
        _ = (packDirectory / "manifest.toml").write_text(manifestBody + "\n", encoding="utf-8")
        _ = (packDirectory / "pack.py").write_text(
            textwrap.dedent(
                """
                from app.feature_pack.api import FeaturePack, SettingItem, SettingSection, Task, TaskInput


                class DemoPack(FeaturePack):
                    def accepts(self, source: str) -> bool:
                        return source.startswith("demo:")

                    async def createTask(self, data: TaskInput) -> Task | None:
                        return None

                    def owns(self, task: Task) -> bool:
                        return False

                    def install(self, window) -> None:
                        window.installed.append(self.manifest.id)

                    def settingSection(self) -> SettingSection:
                        return SettingSection(
                            id="demo-settings",
                            title="Demo Settings",
                            items=(
                                SettingItem(
                                    key="enabled",
                                    label="Enabled",
                                    kind="toggle",
                                ),
                            ),
                        )
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )

    def testHistoricalFeatureServiceSingletonIsV1Backed(self) -> None:
        self.assertIsInstance(featureService, HostFeatureService)
        self.assertIsInstance(featureService, DefaultFeatureService)

    def testLoadPacksAndInstallSettingsUseV1Entry(self) -> None:
        self.writePack()
        service = HostFeatureService(featuresPath=self.featuresPath)
        window = _FakeWindow()

        service.loadPacks(cast(object, window))
        service.installSettings(window.settingPage)

        self.assertEqual(window.installed, ["demo_pack"])
        self.assertIsNotNone(service.pack("demo_pack"))
        self.assertEqual(window.settingPage.vBoxLayout.count(), 1)
        group = window.settingPage.vBoxLayout.itemAt(0).widget()
        self.assertIsNotNone(group)
        self.assertEqual(cast(QWidget, group).objectName(), "featurePackSection:demo-settings")

    def testMainWindowAddTaskCreatesCardsThroughFeatureServiceEntry(self) -> None:
        task = _DemoTask()
        card = _RecordingCard()
        service = _RecordingFeatureService(card)
        recorder = _RecordingTaskRecorder()
        window = type("FakeMainWindow", (), {"taskPage": _RecordingTaskPage()})()

        with patch("app.view.windows.main_window.featureService", service), patch(
            "app.view.windows.main_window.taskRecorder",
            recorder,
        ), patch("app.view.windows.main_window.ensureUniqueTaskTarget", return_value=False):
            result = MainWindow.addTask(cast(MainWindow, window), task)

        self.assertTrue(result)
        self.assertEqual(service.calls, [(task, window)])
        self.assertEqual(recorder.addCalls, [(task, False)])
        self.assertEqual(recorder.flushCalls, 1)
        self.assertEqual(window.taskPage.cards, [card])
        self.assertEqual(card.resumeCalls, 1)


if __name__ == "__main__":
    _ = unittest.main()
