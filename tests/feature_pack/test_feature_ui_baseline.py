from __future__ import annotations
# pyright: reportPrivateUsage=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false, reportUnknownLambdaType=false, reportImplicitOverride=false, reportCallIssue=false, reportMissingTypeStubs=false, reportMissingParameterType=false, reportUnannotatedClassAttribute=false, reportUninitializedInstanceVariable=false, reportExplicitAny=false, reportOptionalMemberAccess=false, reportIncompatibleMethodOverride=false, reportUnusedCallResult=false, reportUnnecessaryCast=false, reportAny=false

import os
import sys
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

_ = os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    _ = sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel, FluentIcon, SettingCardGroup

from app.bases.models import PackConfig, TaskStatus
from app.services.feature_service import FeatureService
from app.supports.utils import getReadableSize
from app.view.components.cards import ParseSettingCard, UniversalResultCard, UniversalTaskCard
from app.view.components.dialogs import FileSelectDialog
from features.http_pack.task import HttpTask, HttpTaskStage


def ensureApplication() -> QApplication:
    application = QApplication.instance()
    if application is not None:
        return cast(QApplication, application)

    return QApplication([])


def createHttpTask(
    tempPath: Path,
    *,
    title: str = "example.mp4",
    fileSize: int = 100,
) -> HttpTask:
    stage = HttpTaskStage(
        stageIndex=1,
        url="https://example.com/example.mp4",
        fileSize=fileSize,
        headers={"referer": "https://example.com"},
        proxies={"http": "http://127.0.0.1:7890"},
        resolvePath="",
        blockNum=4,
    )
    return HttpTask(
        title=title,
        url="https://example.com/example.mp4",
        fileSize=fileSize,
        path=tempPath,
        stages=[stage],
    )


class TrackingUniversalTaskCard(UniversalTaskCard):
    def __init__(self, task: HttpTask, parent=None):
        self.pauseCalls = 0
        self.resumeCalls = 0
        self.finishedCallCount = 0
        super().__init__(task, parent)

    def pauseTask(self):
        self.pauseCalls += 1

    def resumeTask(self):
        self.resumeCalls += 1

    def onTaskFinished(self):
        self.finishedCallCount += 1
        super().onTaskFinished()


@dataclass(kw_only=True)
class FakeSelectableFile:
    index: int
    relativePath: str
    size: int
    selected: bool = True


@dataclass(kw_only=True)
class FakeSelectableTask:
    files: list[FakeSelectableFile]

    @property
    def totalFileCount(self) -> int:
        return len(self.files)


class TestFileSelectDialog(FileSelectDialog):
    def _fileDisplayPath(self, file: FakeSelectableFile) -> str:
        return file.relativePath


class DummyDialogCard(ParseSettingCard):
    def __init__(self, title: str, payloadValue: str, parent=None):
        self._payloadValue = payloadValue
        super().__init__(FluentIcon.TAG, title, parent)

    def initCustomWidget(self):
        self.markerLabel = BodyLabel(self._payloadValue, self)
        self.addWidget(self.markerLabel)

    @property
    def payload(self) -> dict[str, Any]:
        return {"value": self._payloadValue}


class DefaultDialogPackConfig(PackConfig):
    def loadSettingCards(self, settingPage) -> None:
        return None


class RecordingPackConfig(PackConfig):
    def __init__(self, *, sectionTitle: str, dialogCardTitle: str):
        self.sectionTitle = sectionTitle
        self.dialogCardTitle = dialogCardTitle
        self.loadedSettingPage = None
        self.loadedGroup = None

    def loadSettingCards(self, settingPage) -> None:
        self.loadedSettingPage = settingPage
        self.loadedGroup = SettingCardGroup(self.sectionTitle, settingPage.container)
        settingPage.vBoxLayout.addWidget(self.loadedGroup)

    def getDialogCards(self, parent: QWidget):
        return [DummyDialogCard(self.dialogCardTitle, self.sectionTitle, parent)]


class DummyPack:
    def __init__(self, config: PackConfig | None):
        self.config = config


class FakeSettingPage:
    def __init__(self):
        self.container = QWidget()
        self.vBoxLayout = QVBoxLayout(self.container)


class FeatureUiBaselineTests(unittest.TestCase):
    application: QApplication
    _temporaryDirectory: tempfile.TemporaryDirectory[str] | None = None
    tempPath: Path = ROOT

    @classmethod
    def setUpClass(cls) -> None:
        cls.application = ensureApplication()

    def setUp(self) -> None:
        temporaryDirectory = tempfile.TemporaryDirectory()
        self._temporaryDirectory = temporaryDirectory
        self.addCleanup(temporaryDirectory.cleanup)
        self.tempPath = Path(temporaryDirectory.name)

    def showWidget(self, widget: QWidget) -> None:
        widget.show()
        self.application.processEvents()
        self.addCleanup(widget.close)
        self.addCleanup(widget.deleteLater)

    def createDialogParent(self) -> QWidget:
        parent = QWidget()
        parent.resize(900, 700)
        self.showWidget(parent)
        return parent

    def testUniversalTaskCardRefreshKeepsCurrentRenderingBaseline(self) -> None:
        task = createHttpTask(self.tempPath)
        stage = cast(HttpTaskStage, task.stages[0])
        card = TrackingUniversalTaskCard(task)
        self.showWidget(card)

        with patch("app.view.components.cards.taskRecorder.flush") as flushMock:
            stage.receivedBytes = 50
            stage.progress = 50
            stage.speed = 20
            stage.setStatus(TaskStatus.RUNNING)
            card.refresh()

            self.assertEqual(card.progressLabel.text(), "50.00 B/100.00 B")
            self.assertEqual(card.speedLabel.text(), "20.00 B/s")
            self.assertEqual(card.leftTimeLabel.text(), "2s")
            self.assertEqual(flushMock.call_count, 1)

            stage.receivedBytes = 100
            stage.progress = 100
            stage.setStatus(TaskStatus.COMPLETED)
            card.refresh()

            self.assertEqual(card.finishedCallCount, 1)
            self.assertEqual(card.infoLabel.text(), card.tr("任务已经完成"))
            self.assertTrue(card.verifyHashButton.isVisible())
            self.assertEqual(flushMock.call_count, 2)

    def testUniversalCardsKeepCurrentActionEntries(self) -> None:
        task = createHttpTask(self.tempPath)
        stage = cast(HttpTaskStage, task.stages[0])
        taskCard = TrackingUniversalTaskCard(task)
        resultCard = UniversalResultCard(task)
        self.showWidget(taskCard)
        self.showWidget(resultCard)

        stage.setStatus(TaskStatus.RUNNING)
        QTest.mouseClick(taskCard.toggleRunningStatusButton, Qt.MouseButton.LeftButton)
        self.application.processEvents()
        self.assertEqual(taskCard.pauseCalls, 1)

        stage.setStatus(TaskStatus.PAUSED)
        QTest.mouseClick(taskCard.toggleRunningStatusButton, Qt.MouseButton.LeftButton)
        self.application.processEvents()
        self.assertEqual(taskCard.resumeCalls, 1)

        QTest.mouseDClick(resultCard.filenameLabel, Qt.MouseButton.LeftButton)
        self.application.processEvents()
        self.assertTrue(resultCard.filenameEdit.isVisible())

        resultCard.filenameEdit.setText("renamed-video.mkv")
        resultCard._onEditingFinished()

        self.assertEqual(task.title, "renamed-video.mkv")
        self.assertEqual(resultCard.filenameLabel.text(), "renamed-video.mkv")
        self.assertIs(resultCard.getTask(), task)

    def testFileSelectDialogBuildsCurrentTreeAndSummary(self) -> None:
        task = FakeSelectableTask(
            files=[
                FakeSelectableFile(index=0, relativePath="Season 1/episode-1.mp4", size=100, selected=True),
                FakeSelectableFile(index=1, relativePath="Season 1/episode-2.srt", size=20, selected=False),
                FakeSelectableFile(index=2, relativePath="cover.jpg", size=30, selected=True),
            ]
        )
        dialogParent = self.createDialogParent()
        dialog = TestFileSelectDialog(task, dialogParent)
        self.showWidget(dialog)

        folderItem = cast(QStandardItem, dialog.treeModel.item(0, 0))
        self.assertEqual(folderItem.text(), "Season 1")
        self.assertEqual(folderItem.rowCount(), 2)
        self.assertEqual(cast(QStandardItem, folderItem.child(0, 0)).text(), "episode-1.mp4")
        self.assertEqual(cast(QStandardItem, folderItem.child(1, 0)).text(), "episode-2.srt")
        self.assertEqual(cast(QStandardItem, dialog.treeModel.item(1, 0)).text(), "cover.jpg")
        self.assertEqual(
            dialog.summaryLabel.text(),
            dialog.tr("已选择 {0}/{1} 个文件，共 {2}").format(2, 3, getReadableSize(130)),
        )
        self.assertEqual(dialog.selectedIndexes(), {0, 2})

    def testFileSelectDialogSelectionActionsKeepCurrentResults(self) -> None:
        task = FakeSelectableTask(
            files=[
                FakeSelectableFile(index=0, relativePath="Season 1/episode-1.mp4", size=100, selected=True),
                FakeSelectableFile(index=1, relativePath="Season 1/episode-2.srt", size=20, selected=False),
                FakeSelectableFile(index=2, relativePath="cover.jpg", size=30, selected=True),
            ]
        )
        dialogParent = self.createDialogParent()
        dialog = TestFileSelectDialog(task, dialogParent)
        self.showWidget(dialog)

        dialog._clearAll()
        self.assertEqual(dialog.selectedIndexes(), set())

        dialog._invertSelection()
        self.assertEqual(dialog.selectedIndexes(), {0, 1, 2})

        dialog._selectOnlyFileType("subtitle")
        self.assertEqual(dialog.selectedIndexes(), {1})
        self.assertEqual(
            dialog.summaryLabel.text(),
            dialog.tr("已选择 {0}/{1} 个文件，共 {2}").format(1, 3, getReadableSize(20)),
        )

    def testPackConfigDefaultGetDialogCardsRemainsEmpty(self) -> None:
        config = DefaultDialogPackConfig()
        parent = QWidget()
        self.showWidget(parent)

        self.assertEqual(list(config.getDialogCards(parent)), [])

    def testFeatureServiceKeepsCurrentSettingAndDialogInjectionPaths(self) -> None:
        service = FeatureService()
        firstConfig = RecordingPackConfig(sectionTitle="基础设置", dialogCardTitle="主卡片")
        secondConfig = RecordingPackConfig(sectionTitle="扩展设置", dialogCardTitle="副卡片")
        settingPage = FakeSettingPage()
        mainWindow = type("FakeMainWindow", (), {"settingPage": settingPage})()
        parent = QWidget()
        self.showWidget(settingPage.container)
        self.showWidget(parent)

        service._loadPackConfig(cast(Any, DummyPack(firstConfig)), cast(Any, mainWindow))

        self.assertIs(firstConfig.loadedSettingPage, settingPage)
        self.assertEqual(settingPage.vBoxLayout.count(), 1)
        loadedGroupItem = settingPage.vBoxLayout.itemAt(0)
        self.assertIsNotNone(loadedGroupItem)
        loadedGroup = cast(QWidget, loadedGroupItem.widget())
        self.assertIs(loadedGroup, firstConfig.loadedGroup)

        service.sortedPacksCache = [
            ("alpha", cast(Any, DummyPack(firstConfig))),
            ("beta", cast(Any, DummyPack(secondConfig))),
            ("empty", cast(Any, DummyPack(None))),
        ]

        cards = service.getDialogCards(parent)

        self.assertEqual([card.titleLabel.text() for card in cards], ["主卡片", "副卡片"])
        self.assertEqual([card.payload["value"] for card in cards], ["基础设置", "扩展设置"])


if __name__ == "__main__":
    _ = unittest.main()
