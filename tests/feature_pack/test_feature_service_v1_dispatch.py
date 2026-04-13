# pyright: reportImplicitOverride=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false, reportPrivateUsage=false, reportInconsistentConstructor=false, reportMissingTypeStubs=false

from __future__ import annotations

import os
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from typing import cast

_ = os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    _ = sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import QWidget
from qfluentwidgets import SettingCardGroup

from app.feature_pack.api import DefaultFeatureService
from app.feature_pack.api import DefaultResultCard
from app.feature_pack.api import DefaultTaskCard
from app.feature_pack.api import SettingsInstaller
from app.feature_pack.api import StageSnapshot
from app.feature_pack.api import Task
from app.feature_pack.api import TaskConfig
from app.feature_pack.api import TaskEditor
from app.feature_pack.api import TaskSnapshot
from app.feature_pack.api import TaskStage


def ensureApplication() -> QApplication:
    application = QApplication.instance()
    if application is not None:
        return cast(QApplication, application)

    return QApplication([])


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
    def __init__(self, *, packId: str) -> None:
        super().__init__(
            id=f"{packId}-task",
            packId=packId,
            kind="demo",
            version=1,
            config=TaskConfig(
                source=f"{packId}:source",
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
            stages=tuple(stage.snapshot() for stage in self.stages),
        )


class RecordingSettingsInstaller(SettingsInstaller):
    def __init__(self) -> None:
        self.calls: list[tuple[object, str | None]] = []

    def install(
        self,
        page: object,
        pack: object | None = None,
    ) -> SettingCardGroup | None:
        packId = getattr(getattr(pack, "manifest", None), "id", None)
        self.calls.append((page, cast(str | None, packId)))
        return None


class RecordingTaskEditor(TaskEditor):
    result: bool

    def __init__(self, *, result: bool = True) -> None:
        self.result = result
        self.calls: list[tuple[Task, str, QWidget | None]] = []

    def editTask(
        self,
        task: Task,
        mode: str,
        parent: QWidget | None = None,
    ) -> bool:
        self.calls.append((task, mode, parent))
        return self.result


class FeatureServiceV1DispatchTests(unittest.TestCase):
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

    def showWidget(self, widget: QWidget) -> None:
        widget.show()
        application = self.application
        assert application is not None
        application.processEvents()
        self.addCleanup(widget.close)
        self.addCleanup(widget.deleteLater)

    def createParent(self) -> QWidget:
        parent = QWidget()
        parent.resize(960, 720)
        self.showWidget(parent)
        return parent

    def createService(
        self,
        *,
        settingsInstaller: SettingsInstaller | None = None,
        taskEditor: TaskEditor | None = None,
    ) -> DefaultFeatureService:
        return DefaultFeatureService(
            featuresPath=self.featuresPath,
            settingsInstaller=settingsInstaller,
            taskEditor=taskEditor,
        )

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

    def loadService(
        self,
        *,
        settingsInstaller: SettingsInstaller | None = None,
        taskEditor: TaskEditor | None = None,
    ) -> DefaultFeatureService:
        service = self.createService(
            settingsInstaller=settingsInstaller,
            taskEditor=taskEditor,
        )
        service.loadPacks(_FakeWindow())
        return service

    def testCreateTaskCardAndResultCardPreferPackProvidedCards(self) -> None:
        _ = self.writePack(
            directoryName="custom_pack",
            entryBody="""
            from app.feature_pack.api import FeaturePack, Task, TaskInput


            class CustomPack(FeaturePack):
                def __init__(self) -> None:
                    self.taskCardCalls = 0
                    self.resultCardCalls = 0

                def accepts(self, source: str) -> bool:
                    return False

                async def createTask(self, data: TaskInput) -> Task | None:
                    return None

                def owns(self, task: Task) -> bool:
                    return task.packId == self.manifest.id

                def createTaskCard(self, task: Task, parent=None):
                    self.taskCardCalls += 1
                    return {
                        "kind": "task",
                        "packId": self.manifest.id,
                        "taskId": task.id,
                        "parentType": type(parent).__name__ if parent is not None else None,
                    }

                def createResultCard(self, task: Task, parent=None):
                    self.resultCardCalls += 1
                    return {
                        "kind": "result",
                        "packId": self.manifest.id,
                        "taskId": task.id,
                        "parentType": type(parent).__name__ if parent is not None else None,
                    }
            """,
        )
        service = self.loadService()
        parent = self.createParent()
        task = _DemoTask(packId="custom_pack")

        taskCard = service.createTaskCard(task, parent)
        resultCard = service.createResultCard(task, parent)

        self.assertEqual(
            taskCard,
            {
                "kind": "task",
                "packId": "custom_pack",
                "taskId": "custom_pack-task",
                "parentType": "QWidget",
            },
        )
        self.assertEqual(
            resultCard,
            {
                "kind": "result",
                "packId": "custom_pack",
                "taskId": "custom_pack-task",
                "parentType": "QWidget",
            },
        )
        loadedPack = service.pack("custom_pack")
        self.assertIsNotNone(loadedPack)
        self.assertEqual(getattr(loadedPack, "taskCardCalls"), 1)
        self.assertEqual(getattr(loadedPack, "resultCardCalls"), 1)

    def testCreateTaskCardFallsBackToDefaultCardAndRoutesEditThroughService(self) -> None:
        editor = RecordingTaskEditor()
        _ = self.writePack(
            directoryName="default_pack",
            entryBody="""
            from app.feature_pack.api import FeaturePack, Task, TaskInput


            class DefaultPack(FeaturePack):
                def __init__(self) -> None:
                    self.taskCardCalls = 0

                def accepts(self, source: str) -> bool:
                    return False

                async def createTask(self, data: TaskInput) -> Task | None:
                    return None

                def owns(self, task: Task) -> bool:
                    return task.packId == self.manifest.id

                def createTaskCard(self, task: Task, parent=None):
                    self.taskCardCalls += 1
                    return None
            """,
        )
        service = self.loadService(taskEditor=editor)
        task = _DemoTask(packId="default_pack")
        card = cast(DefaultTaskCard, service.createTaskCard(task, self.createParent()))
        self.showWidget(card)

        self.assertIsInstance(card, DefaultTaskCard)

        QTest.mouseClick(card.editButton, Qt.MouseButton.LeftButton)

        loadedPack = service.pack("default_pack")
        self.assertIsNotNone(loadedPack)
        self.assertEqual(getattr(loadedPack, "taskCardCalls"), 1)
        self.assertEqual(len(editor.calls), 1)
        self.assertIs(editor.calls[0][0], task)
        self.assertEqual(editor.calls[0][1], "running")
        self.assertIs(editor.calls[0][2], card)

    def testCreateResultCardFallsBackToDefaultResultCardWhenPackReturnsNone(self) -> None:
        _ = self.writePack(
            directoryName="default_pack",
            entryBody="""
            from app.feature_pack.api import FeaturePack, Task, TaskInput


            class DefaultPack(FeaturePack):
                def __init__(self) -> None:
                    self.resultCardCalls = 0

                def accepts(self, source: str) -> bool:
                    return False

                async def createTask(self, data: TaskInput) -> Task | None:
                    return None

                def owns(self, task: Task) -> bool:
                    return task.packId == self.manifest.id

                def createResultCard(self, task: Task, parent=None):
                    self.resultCardCalls += 1
                    return None
            """,
        )
        service = self.loadService()
        parent = self.createParent()
        task = _DemoTask(packId="default_pack")

        card = service.createResultCard(task, parent)

        self.assertIsInstance(card, DefaultResultCard)
        resultCard = cast(DefaultResultCard, card)
        self.assertIs(resultCard.task, task)
        self.assertIs(resultCard.parent(), parent)
        loadedPack = service.pack("default_pack")
        self.assertIsNotNone(loadedPack)
        self.assertEqual(getattr(loadedPack, "resultCardCalls"), 1)

    def testInstallSettingsDelegatesLoadedPacksToInstallerInDependencyOrder(self) -> None:
        settingsInstaller = RecordingSettingsInstaller()
        _ = self.writePack(
            directoryName="base_pack",
            entryBody="""
            from app.feature_pack.api import FeaturePack, Task, TaskInput


            class BasePack(FeaturePack):
                def accepts(self, source: str) -> bool:
                    return False

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
                    return False

                async def createTask(self, data: TaskInput) -> Task | None:
                    return None

                def owns(self, task: Task) -> bool:
                    return False
            """,
        )
        service = self.loadService(settingsInstaller=settingsInstaller)
        page = object()

        service.installSettings(page)

        self.assertEqual(
            settingsInstaller.calls,
            [(page, "base_pack"), (page, "child_pack")],
        )

    def testEditTaskDelegatesToConfiguredTaskEditor(self) -> None:
        taskEditor = RecordingTaskEditor(result=False)
        service = self.createService(taskEditor=taskEditor)
        task = _DemoTask(packId="demo_pack")
        parent = self.createParent()

        accepted = service.editTask(task, "before", parent)

        self.assertFalse(accepted)
        self.assertEqual(taskEditor.calls, [(task, "before", parent)])


if __name__ == "__main__":
    _ = unittest.main()
