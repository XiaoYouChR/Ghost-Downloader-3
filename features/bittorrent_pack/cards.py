from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
    QFileIconProvider,
)
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    FluentIcon,
    IconWidget,
    PrimaryPushButton,
    StrongBodyLabel,
    ToolButton,
)

from app.bases.models import TaskStatus
from app.supports.utils import toReadableSize, toReadableTime
from app.view.components.cards import ResultCard, UniversalTaskCard
from app.view.components.dialogs import FileSelectDialog
from app.view.components.labels import IconBodyLabel
from .task import BTFile, BTTask


def _openFileSelection(task: BTTask, parent) -> set[int] | None:
    dialog = TorrentFileSelectDialog(task, parent)
    try:
        if not dialog.exec():
            return None
        selectedIndexes = dialog.selectedIndexes()
        task.setSelection(selectedIndexes)
        return selectedIndexes
    finally:
        dialog.deleteLater()


class TorrentFileSelectDialog(FileSelectDialog):
    def __init__(self, task: BTTask, parent=None):
        super().__init__(task, parent)
        self.task: BTTask = task

    def _fileDisplayPath(self, file: BTFile) -> str:
        return self.task.mapPath(file)

    def _fileTypePath(self, file: BTFile) -> str:
        return file.path


class BitTorrentResultCard(ResultCard):
    def __init__(self, task: BTTask, parent: QWidget = None):
        super().__init__(task, parent)
        # instant widget
        self.iconLabel = IconWidget(self)
        self.titleLabel = StrongBodyLabel(self.task.title, self)
        self.sourceLabel = CaptionLabel(self._sourceText(), self)
        self.summaryLabel = BodyLabel("", self)
        self.selectFilesButton = PrimaryPushButton(self.tr("选择文件"), self)
        # instant layout
        self.mainLayout = QHBoxLayout(self)
        self.textLayout = QVBoxLayout()

        self._initWidget()
        self._initLayout()
        self._bind()
        self._refreshSummary()
        self._renderCategoryButton()

    def _initWidget(self):
        self.setFixedHeight(45)
        self.iconLabel.setFixedSize(20, 20)
        icon = QFileIconProvider.IconType.File if self.task.isSingleFile else QFileIconProvider.IconType.Folder
        self.iconLabel.setIcon(QFileIconProvider().icon(icon))

    def _initLayout(self):
        self.mainLayout.setContentsMargins(10, 6, 10, 6)
        self.mainLayout.setSpacing(12)
        self.textLayout.setContentsMargins(0, 0, 0, 0)
        self.textLayout.setSpacing(2)
        self.textLayout.addWidget(self.titleLabel)
        self.textLayout.addWidget(self.sourceLabel)
        self.mainLayout.addWidget(self.iconLabel, 0, Qt.AlignmentFlag.AlignCenter)
        self.mainLayout.addLayout(self.textLayout)
        self.mainLayout.addStretch(1)
        self.mainLayout.addWidget(self.summaryLabel)
        self.mainLayout.addSpacing(12)
        self.mainLayout.addWidget(self.categoryButton)
        self.mainLayout.addWidget(self.selectFilesButton)

    def _bind(self):
        self.selectFilesButton.clicked.connect(self._onSelectFilesClicked)

    def _sourceText(self) -> str:
        typeText = "Magnet" if self.task.sourceType == "magnet" else "Torrent"
        trackerCount = len(self.task.trackers)
        if trackerCount > 0:
            return self.tr("{0} · {1} 个 Tracker").format(typeText, trackerCount)
        return typeText

    def _refreshSummary(self):
        self.summaryLabel.setText(
            self.tr("{0}/{1} 个文件 · {2}").format(
                self.task.countSelected,
                self.task.countAll,
                toReadableSize(self.task.fileSize),
            )
        )

    def _onSelectFilesClicked(self):
        if _openFileSelection(self.task, self.window()) is not None:
            self._refreshSummary()

    def getTask(self) -> BTTask:
        return self.task


class BTTaskCard(UniversalTaskCard):
    def __init__(self, task: BTTask, parent=None):
        super().__init__(task, parent)
        self.task: BTTask = task
        self.speedLabel.setIcon(FluentIcon.DOWNLOAD)
        self.uploadRateLabel = IconBodyLabel("", FluentIcon.SHARE, self)
        self.infoLayout.insertWidget(self.infoLayout.indexOf(self.leftTimeLabel), self.uploadRateLabel)
        self.metaInfoLabel = IconBodyLabel("", FluentIcon.INFO, self)
        self.infoLayout.insertWidget(self.infoLayout.indexOf(self.infoLabel), self.metaInfoLabel)
        self.selectFilesButton = ToolButton(FluentIcon.LIBRARY, self)
        self.hBoxLayout.insertWidget(self.hBoxLayout.indexOf(self.verifyHashButton), self.selectFilesButton)
        self.selectFilesButton.clicked.connect(self._onSelectFilesClicked)
        self._refreshInfoLayout()

    def _metaText(self) -> str:
        parts: list[str] = []
        if self.task.stateText and self.task.stateText not in {"下载中", "做种中"}:
            parts.append(self.task.stateText)
        if self.task.isSeeding and self.task.shareRatioPercent > 0:
            parts.append(self.tr("分享率 {0:.2f}%").format(self.task.shareRatioPercent))
        if self.task.isSeeding and self.task.seedingTimeSeconds > 0:
            parts.append(self.tr("做种 {0}").format(toReadableTime(self.task.seedingTimeSeconds)))
        if self.task.peerCount or self.task.seedCount:
            parts.append(
                self.tr("Peers {0} / Seeds {1}").format(
                    self.task.peerCount,
                    self.task.seedCount,
                )
            )
        return " · ".join(parts)

    def _refreshInfoLayout(self):
        if self.task.status == TaskStatus.RUNNING:
            self.speedLabel.setText(f"{toReadableSize(self.task.downloadRate)}/s")
            self.uploadRateLabel.setText(f"{toReadableSize(self.task.uploadRate)}/s")
            if self.task.isSeeding:
                self.leftTimeLabel.hide()
            elif self.task.fileSize > 0 and self.task.downloadRate > 0:
                remainingBytes = self.task.fileSize - self.task.stage.receivedBytes
                self.leftTimeLabel.setText(toReadableTime(int(remainingBytes / self.task.downloadRate)))
                self.leftTimeLabel.show()
            else:
                self.leftTimeLabel.setText("--")
                self.leftTimeLabel.show()
            metaText = self._metaText()
            self.metaInfoLabel.setText(metaText)
            self.metaInfoLabel.setVisible(bool(metaText))
            self.speedLabel.show()
            self.uploadRateLabel.show()
            self.progressLabel.show()
            self.infoLabel.hide()
            return

        self.uploadRateLabel.hide()
        self.metaInfoLabel.hide()

    def _onSelectFilesClicked(self):
        previousSelected = {file.index for file in self.task.files if file.selected}
        selectedIndexes = _openFileSelection(self.task, self.window())
        if selectedIndexes is None:
            return

        self._refreshInfoLayout()
        if self.task.status == TaskStatus.COMPLETED and selectedIndexes - previousSelected and self.task.reopen():
            self.resumeTask()

    def refresh(self):
        super().refresh()
        self._refreshInfoLayout()
        self.progressBar.setVisible(self.task.status != TaskStatus.COMPLETED and not self.task.isSeeding)
        self.verifyHashButton.setVisible(
            self.task.isSingleFile
            and self.task.status == TaskStatus.COMPLETED
            and Path(self.task.outputFolder).is_file()
        )
        self.selectFilesButton.setEnabled(self.task.status != TaskStatus.COMPLETED or self.task.hasUnselected)

    def onTaskFinished(self):
        super().onTaskFinished()
        self._refreshInfoLayout()
