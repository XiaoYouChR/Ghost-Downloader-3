# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false, reportUnknownVariableType=false, reportAttributeAccessIssue=false, reportCallIssue=false, reportAny=false, reportInconsistentConstructor=false, reportImplicitOverride=false, reportMissingTypeStubs=false

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from typing import cast

_ = os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    _ = sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import QWidget

from app.feature_pack.api import MultiFileSelectDialog
from app.feature_pack.api import MultiFileTask
from app.feature_pack.api import StageSnapshot
from app.feature_pack.api import TaskConfig
from app.feature_pack.api import TaskFile
from app.feature_pack.api import TaskSnapshot
from app.feature_pack.api import TaskStage
from app.supports.utils import getReadableSize


def ensureApplication() -> QApplication:
    application = QApplication.instance()
    if application is not None:
        return cast(QApplication, application)

    return QApplication([])


class DemoDialogStage(TaskStage):
    def __init__(self, *, id: str = "stage-1") -> None:
        super().__init__(id=id, kind="download", version=1, name=f"阶段 {id}")

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
            error="",
        )


class DemoMultiFileDialogTask(MultiFileTask):
    target: str

    def __init__(self, *, config: TaskConfig, files: list[TaskFile]) -> None:
        self.target = ""
        super().__init__(
            id="task-1",
            packId="demo_pack",
            kind="multi_file",
            version=1,
            config=config,
            stages=[DemoDialogStage()],
            files=files,
        )

    def syncOutput(self) -> None:
        self.target = str(self.root)

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
            totalBytes=sum(file.size for file in self.files),
            canPause=self.canPause(),
            target=self.target,
            stages=tuple(stage.snapshot() for stage in self.stages),
        )


class MultiFileSelectDialogTests(unittest.TestCase):
    application: QApplication | None = None

    @classmethod
    def setUpClass(cls) -> None:
        cls.application = ensureApplication()

    def showWidget(self, widget: QWidget) -> None:
        widget.show()
        application = self.application
        assert application is not None
        application.processEvents()
        self.addCleanup(widget.close)
        self.addCleanup(widget.deleteLater)

    def createDialogParent(self) -> QWidget:
        parent = QWidget()
        parent.resize(900, 700)
        self.showWidget(parent)
        return parent

    def makeConfig(self) -> TaskConfig:
        return TaskConfig(
            source="magnet:?xt=urn:btih:demo",
            folder=Path("downloads"),
            name="season-1",
            headers={"User-Agent": "Ghost Downloader"},
            proxies={"https": "http://127.0.0.1:7890"},
            chunks=4,
        )

    def makeTask(self) -> DemoMultiFileDialogTask:
        return DemoMultiFileDialogTask(
            config=self.makeConfig(),
            files=[
                TaskFile(
                    id="episode-1",
                    path="Season 1/episode-1.mp4",
                    size=100,
                    selected=True,
                    note="1080p",
                ),
                TaskFile(
                    id="subtitle-1",
                    path="Season 1/episode-1.srt",
                    size=20,
                    selected=False,
                ),
                TaskFile(
                    id="cover-1",
                    path="cover.jpg",
                    size=30,
                    selected=True,
                    note="封面",
                ),
            ],
        )

    def testMultiFileSelectDialogBuildsTreeFromTaskFilesAndShowsNotes(self) -> None:
        dialog = MultiFileSelectDialog(
            task=self.makeTask(),
            parent=self.createDialogParent(),
        )
        self.showWidget(dialog)

        folderItem = dialog.treeModel.item(0, 0)
        noteItem = dialog.treeModel.item(1, 2)
        assert folderItem is not None
        assert noteItem is not None

        self.assertEqual(dialog.titleLabel.text(), "选择内容")
        self.assertEqual(folderItem.text(), "Season 1")
        self.assertEqual(folderItem.rowCount(), 2)
        firstChild = folderItem.child(0, 0)
        secondChild = folderItem.child(1, 0)
        coverItem = dialog.treeModel.item(1, 0)
        assert firstChild is not None
        assert secondChild is not None
        assert coverItem is not None
        self.assertEqual(firstChild.text(), "episode-1.mp4")
        self.assertEqual(secondChild.text(), "episode-1.srt")
        self.assertEqual(coverItem.text(), "cover.jpg")
        self.assertEqual(noteItem.text(), "封面")
        self.assertEqual(
            dialog.summaryLabel.text(),
            dialog.tr("已选择 {0}/{1} 项，共 {2}").format(2, 3, getReadableSize(130)),
        )
        self.assertEqual(dialog.selectedIds(), {"episode-1", "cover-1"})

    def testMultiFileSelectDialogSelectionActionsUseStableIds(self) -> None:
        dialog = MultiFileSelectDialog(
            task=self.makeTask(),
            parent=self.createDialogParent(),
        )
        self.showWidget(dialog)

        dialog.clearButton.click()
        self.assertEqual(dialog.selectedIds(), set())
        self.assertFalse(dialog.validate())

        dialog.invertButton.click()
        self.assertEqual(dialog.selectedIds(), {"episode-1", "subtitle-1", "cover-1"})

        subtitleAction = next(
            action
            for action in dialog.selectByTypeMenu.actions()
            if "字幕" in action.text()
        )
        subtitleAction.trigger()
        self.assertEqual(dialog.selectedIds(), {"subtitle-1"})
        self.assertEqual(
            dialog.summaryLabel.text(),
            dialog.tr("已选择 {0}/{1} 项，共 {2}").format(1, 3, getReadableSize(20)),
        )
        self.assertTrue(dialog.validate())

    def testMultiFileSelectDialogSelectAllReturnsAllStableIds(self) -> None:
        dialog = MultiFileSelectDialog(
            task=self.makeTask(),
            title="保留内容",
            parent=self.createDialogParent(),
        )
        self.showWidget(dialog)

        dialog.selectAllButton.click()
        self.assertEqual(dialog.selectedIds(), {"episode-1", "subtitle-1", "cover-1"})

    def testMultiFileSelectDialogTracksBranchCheckStateWhenLeafChanges(self) -> None:
        dialog = MultiFileSelectDialog(
            task=self.makeTask(),
            parent=self.createDialogParent(),
        )
        self.showWidget(dialog)

        folderItem = dialog.treeModel.item(0, 0)
        assert folderItem is not None
        subtitleItem = folderItem.child(1, 0)
        assert subtitleItem is not None
        subtitleItem.setCheckState(Qt.CheckState.Checked)

        application = self.application
        assert application is not None
        application.processEvents()

        self.assertEqual(folderItem.checkState(), Qt.CheckState.Checked)
        self.assertEqual(dialog.selectedIds(), {"episode-1", "subtitle-1", "cover-1"})


if __name__ == "__main__":
    _ = unittest.main()
