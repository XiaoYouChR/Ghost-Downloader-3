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

from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import QWidget
from qfluentwidgets import BodyLabel
from qfluentwidgets import ComboBox
from qfluentwidgets import LineEdit
from qfluentwidgets import SpinBox

from app.feature_pack.api import FormChoice
from app.feature_pack.api import FormField
from app.feature_pack.api import MultiFileTask
from app.feature_pack.api import SingleFileTask
from app.feature_pack.api import StageSnapshot
from app.feature_pack.api import TaskConfig
from app.feature_pack.api import TaskConfigDialog
from app.feature_pack.api import TaskFile
from app.feature_pack.api import TaskForm
from app.feature_pack.api import TaskSnapshot
from app.feature_pack.api import TaskStage
from app.view.components.editors import AutoSizingEdit


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


class DemoSingleFileDialogTask(SingleFileTask):
    target: str

    def __init__(self, *, config: TaskConfig) -> None:
        self.target = ""
        super().__init__(
            id="task-1",
            packId="demo_pack",
            kind="single_file",
            version=1,
            config=config,
            stages=[DemoDialogStage()],
        )

    def syncOutput(self) -> None:
        self.target = str(self.path)

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
            target=self.target,
            stages=tuple(stage.snapshot() for stage in self.stages),
        )


class DemoMultiFileDialogTask(MultiFileTask):
    target: str

    def __init__(self, *, config: TaskConfig, files: list[TaskFile]) -> None:
        self.target = ""
        super().__init__(
            id="task-2",
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


class TaskConfigDialogTests(unittest.TestCase):
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
            source="https://example.com/video.mkv",
            folder=Path("downloads"),
            name="video.mkv",
            headers={
                "User-Agent": "Ghost Downloader",
                "Referer": "https://example.com",
            },
            proxies={"https": "http://127.0.0.1:7890"},
            chunks=8,
        )

    def testTaskConfigDialogRendersModeFilteredStandardFieldsAndCollectsConfig(self) -> None:
        task = DemoSingleFileDialogTask(config=self.makeConfig())
        form = TaskForm(
            title="编辑下载任务",
            fields=(
                FormField(key="source", label="来源", kind="text", placeholder="输入下载链接"),
                FormField(
                    key="name",
                    label="文件名",
                    kind="text",
                    modes=frozenset({"before"}),
                ),
                FormField(key="folder", label="下载目录", kind="folder"),
                FormField(key="headers", label="请求头", kind="headers"),
                FormField(key="proxies", label="代理", kind="proxy"),
                FormField(key="chunks", label="分块数", kind="int", min=1, max=16, step=2),
            ),
        )

        dialog = TaskConfigDialog(
            task=task,
            form=form,
            mode="running",
            parent=self.createDialogParent(),
        )
        self.showWidget(dialog)

        sourceInput = dialog.findChild(LineEdit, "taskConfigInput:source")
        folderInput = dialog.findChild(LineEdit, "taskConfigInput:folder")
        headersInput = dialog.findChild(AutoSizingEdit, "taskConfigInput:headers")
        proxiesInput = dialog.findChild(AutoSizingEdit, "taskConfigInput:proxies")
        chunksInput = dialog.findChild(SpinBox, "taskConfigInput:chunks")
        hiddenNameInput = dialog.findChild(LineEdit, "taskConfigInput:name")

        self.assertIsNotNone(sourceInput)
        self.assertIsNotNone(folderInput)
        self.assertIsNotNone(headersInput)
        self.assertIsNotNone(proxiesInput)
        self.assertIsNotNone(chunksInput)
        self.assertIsNone(hiddenNameInput)

        sourceInput = cast(LineEdit, sourceInput)
        folderInput = cast(LineEdit, folderInput)
        headersInput = cast(AutoSizingEdit, headersInput)
        proxiesInput = cast(AutoSizingEdit, proxiesInput)
        chunksInput = cast(SpinBox, chunksInput)

        self.assertEqual(sourceInput.text(), "https://example.com/video.mkv")
        self.assertEqual(folderInput.text(), "downloads")
        self.assertEqual(
            headersInput.toPlainText(),
            "User-Agent: Ghost Downloader\nReferer: https://example.com",
        )
        self.assertEqual(
            proxiesInput.toPlainText(),
            "https: http://127.0.0.1:7890",
        )
        self.assertEqual(chunksInput.value(), 8)

        sourceInput.setText("https://mirror.example.com/video.mkv")
        folderInput.setText("archive")
        headersInput.setPlainText("Authorization: Bearer token\nX-Test: yes")
        proxiesInput.setPlainText("https = socks5://127.0.0.1:1080")
        chunksInput.setValue(12)

        config = dialog.config()

        self.assertEqual(config.source, "https://mirror.example.com/video.mkv")
        self.assertEqual(config.folder, Path("archive"))
        self.assertEqual(config.name, "video.mkv")
        self.assertEqual(
            config.headers,
            {
                "Authorization": "Bearer token",
                "X-Test": "yes",
            },
        )
        self.assertEqual(
            config.proxies,
            {"https": "socks5://127.0.0.1:1080"},
        )
        self.assertEqual(config.chunks, 12)
        self.assertEqual(dialog.selectedIds(), set())
        self.assertTrue(dialog.validate())

    def testTaskConfigDialogCollectsChoiceValueAndKeepsCurrentFileSelection(self) -> None:
        task = DemoMultiFileDialogTask(
            config=self.makeConfig(),
            files=[
                TaskFile(id="episode-1", path="Season 1/episode-1.mp4", size=100, selected=True),
                TaskFile(id="episode-2", path="Season 1/episode-2.mp4", size=120, selected=False),
                TaskFile(id="episode-3", path="Season 1/episode-3.mp4", size=140, selected=True),
            ],
        )
        form = TaskForm(
            title="编辑多文件任务",
            fields=(
                FormField(
                    key="source",
                    label="来源",
                    kind="choice",
                    choices=(
                        FormChoice(
                            value="https://example.com/video.mkv",
                            label="主线路",
                        ),
                        FormChoice(
                            value="https://mirror.example.com/video.mkv",
                            label="镜像线路",
                        ),
                    ),
                ),
                FormField(
                    key="files",
                    label="保留内容",
                    kind="files",
                    note="当前轮次先显示并回收现有选择，正式多文件选择对话框在下一任务接入。",
                ),
            ),
        )

        dialog = TaskConfigDialog(
            task=task,
            form=form,
            mode="before",
            parent=self.createDialogParent(),
        )
        self.showWidget(dialog)

        sourceInput = dialog.findChild(ComboBox, "taskConfigInput:source")
        filesLabel = dialog.findChild(BodyLabel, "taskConfigInput:files")

        self.assertIsNotNone(sourceInput)
        self.assertIsNotNone(filesLabel)

        sourceInput = cast(ComboBox, sourceInput)
        filesLabel = cast(BodyLabel, filesLabel)

        self.assertEqual(sourceInput.currentData(), "https://example.com/video.mkv")
        self.assertEqual(filesLabel.text(), "已保留 2/3 项选择")

        sourceInput.setCurrentIndex(1)
        config = dialog.config()

        self.assertEqual(config.source, "https://mirror.example.com/video.mkv")
        self.assertEqual(dialog.selectedIds(), {"episode-1", "episode-3"})
        self.assertTrue(dialog.validate())


if __name__ == "__main__":
    _ = unittest.main()
