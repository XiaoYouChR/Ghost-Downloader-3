import shutil
from pathlib import Path, PurePosixPath

from PySide6.QtCore import Qt, QFileInfo
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
from app.supports.utils import getReadableSize, getReadableTime
from app.view.components.cards import ResultCard, UniversalTaskCard
from app.view.components.dialogs import FileSelectDialog
from app.view.components.labels import IconBodyLabel

from .task import BitTorrentFile, BitTorrentTask


def _removePath(path: Path):
    if not path.exists():
        return
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
        return
    path.unlink(missing_ok=True)


def _openFileSelection(task: BitTorrentTask, parent) -> set[int] | None:
    dialog = TorrentFileSelectDialog(task, parent)
    try:
        if not dialog.exec():
            return None
        selectedIndexes = dialog.selectedIndexes()
        task.updateSelectedFiles(selectedIndexes)
        return selectedIndexes
    finally:
        dialog.deleteLater()


class TorrentFileSelectDialog(FileSelectDialog):
    def __init__(self, task: BitTorrentTask, parent=None):
        super().__init__(task, parent)
        self.task: BitTorrentTask = task

    def _fileDisplayPath(self, file: BitTorrentFile) -> str:
        return self.task.mappedRelativePath(file)

    def _fileTypePath(self, file: BitTorrentFile) -> str:
        return file.path


class BitTorrentResultCard(ResultCard):
    def __init__(self, task: BitTorrentTask, parent: QWidget = None):
        super().__init__(task, parent)
        self.task = task

        self.mainLayout = QHBoxLayout(self)
        self.textLayout = QVBoxLayout()
        self.iconLabel = IconWidget(self)
        self.titleLabel = StrongBodyLabel(self.task.title, self)
        self.sourceLabel = CaptionLabel(self._sourceText(), self)
        self.summaryLabel = BodyLabel("", self)
        self.selectFilesButton = PrimaryPushButton(self.tr("选择文件"), self)

        self._initWidget()
        self._initLayout()
        self._refreshSummary()

    def _initWidget(self):
        self.setFixedHeight(45)
        self.iconLabel.setFixedSize(20, 20)
        icon = QFileIconProvider.IconType.File if self.task.isSingleFileTorrent else QFileIconProvider.IconType.Folder
        self.iconLabel.setIcon(QFileIconProvider().icon(icon))
        self.selectFilesButton.clicked.connect(self._onSelectFilesClicked)

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
        self.mainLayout.addWidget(self.selectFilesButton)

    def _sourceText(self) -> str:
        typeText = "Magnet" if self.task.sourceType == "magnet" else "Torrent"
        trackerCount = len(self.task.trackers)
        if trackerCount > 0:
            return self.tr("{0} · {1} 个 Tracker").format(typeText, trackerCount)
        return typeText

    def _refreshSummary(self):
        self.summaryLabel.setText(
            self.tr("{0}/{1} 个文件 · {2}").format(
                self.task.selectedFileCount,
                self.task.totalFileCount,
                getReadableSize(self.task.fileSize),
            )
        )

    def _onSelectFilesClicked(self):
        if _openFileSelection(self.task, self.window()) is not None:
            self._refreshSummary()

    def getTask(self) -> BitTorrentTask:
        return self.task


class BitTorrentTaskCard(UniversalTaskCard):
    def __init__(self, task: BitTorrentTask, parent=None):
        super().__init__(task, parent)
        self.task: BitTorrentTask = task
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
        if self.task.stage.stateText and self.task.stage.stateText not in {"下载中", "做种中"}:
            parts.append(self.task.stage.stateText)
        if self.task.isSeeding and self.task.shareRatioPercent > 0:
            parts.append(self.tr("分享率 {0:.2f}%").format(self.task.shareRatioPercent))
        if self.task.isSeeding and self.task.seedingTimeSeconds > 0:
            parts.append(self.tr("做种 {0}").format(getReadableTime(self.task.seedingTimeSeconds)))
        if self.task.stage.peerCount or self.task.stage.seedCount:
            parts.append(
                self.tr("Peers {0} / Seeds {1}").format(
                    self.task.stage.peerCount,
                    self.task.stage.seedCount,
                )
            )
        return " · ".join(parts)

    def _refreshInfoLayout(self):
        if self.task.status == TaskStatus.RUNNING:
            self.speedLabel.setText(f"{getReadableSize(self.task.stage.downloadRate)}/s")
            self.uploadRateLabel.setText(f"{getReadableSize(self.task.stage.uploadRate)}/s")
            if self.task.isSeeding:
                self.leftTimeLabel.hide()
            elif self.task.fileSize > 0 and self.task.stage.downloadRate > 0:
                remainingBytes = self.task.fileSize - self.task.stage.receivedBytes
                self.leftTimeLabel.setText(getReadableTime(int(remainingBytes / self.task.stage.downloadRate)))
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
            if not metaText:
                self.metaInfoLabel.hide()
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
        if self.task.status == TaskStatus.COMPLETED and selectedIndexes - previousSelected and self.task.reopenForAdditionalFiles():
            self.resumeTask()

    def refresh(self):
        super().refresh()
        self._refreshInfoLayout()
        self.progressBar.setVisible(self.task.status != TaskStatus.COMPLETED and not self.task.isSeeding)
        self.verifyHashButton.setVisible(
            self.task.isSingleFileTorrent
            and self.task.status == TaskStatus.COMPLETED
            and Path(self.task.outputFolder).is_file()
        )
        self.selectFilesButton.setEnabled(self.task.status != TaskStatus.COMPLETED or self.task.hasUnselectedFiles)

    def onTaskDeleted(self, completely: bool = False):
        if not completely:
            return
        _removePath(Path(self.task.outputFolder))
        if self.task.magnetTorrentPath is not None:
            _removePath(self.task.magnetTorrentPath)

    def onTaskFinished(self):
        super().onTaskFinished()
        self._refreshInfoLayout()
