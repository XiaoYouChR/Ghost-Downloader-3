import shutil
from pathlib import Path, PurePosixPath

from PySide6.QtCore import Qt, QFileInfo
from PySide6.QtWidgets import (
    QHeaderView,
    QHBoxLayout,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget, QFileIconProvider,
)
from qfluentwidgets import (
    Action,
    BodyLabel,
    CaptionLabel,
    DropDownPushButton,
    FluentIcon,
    IconWidget,
    InfoBar,
    MessageBoxBase,
    PrimaryPushButton,
    PushButton,
    RoundMenu,
    StrongBodyLabel,
    ToolButton,
    SubtitleLabel,
    TreeWidget
)

from app.bases.models import TaskStatus
from app.supports.utils import getReadableSize, getReadableTime
from app.view.components.cards import ResultCard, UniversalTaskCard
from app.view.components.labels import IconBodyLabel

from .task import BitTorrentFile, BitTorrentTask

_TORRENT_FILE_TYPE_RULES = (
    ("video", "视频", FluentIcon.VIDEO, {
        ".avi", ".flv", ".m2ts", ".m4v", ".mkv", ".mov", ".mp4", ".mpeg", ".mpg", ".rmvb", ".ts", ".webm", ".wmv",
    }),
    ("audio", "音频", FluentIcon.MUSIC, {
        ".aac", ".ape", ".flac", ".m4a", ".mp3", ".ogg", ".opus", ".wav", ".wma",
    }),
    ("image", "图片", FluentIcon.PHOTO, {
        ".avif", ".bmp", ".gif", ".jpeg", ".jpg", ".png", ".svg", ".tif", ".tiff", ".webp",
    }),
    ("subtitle", "字幕", FluentIcon.CHAT, {
        ".ass", ".idx", ".lrc", ".psb", ".smi", ".srt", ".ssa", ".sub", ".sup", ".vtt",
    }),
    ("document", "文档", FluentIcon.DOCUMENT, {
        ".chm", ".csv", ".doc", ".docx", ".epub", ".md", ".nfo", ".odt", ".pdf", ".ppt", ".pptx", ".rtf",
        ".txt", ".xls", ".xlsx",
    }),
    ("archive", "压缩包", FluentIcon.ZIP_FOLDER, {
        ".001", ".7z", ".bz2", ".cab", ".gz", ".iso", ".rar", ".tar", ".tbz2", ".tgz", ".xz", ".zip", ".zst",
        ".tar.bz2", ".tar.gz", ".tar.xz", ".tar.zst",
    }),
    ("application", "程序", FluentIcon.APPLICATION, {
        ".apk", ".appimage", ".bat", ".com", ".deb", ".dmg", ".exe", ".iso", ".jar", ".msi", ".pkg", ".rpm", ".sh",
    }),
)

_TORRENT_FILE_TYPE_META = {
    key: (label, icon)
    for key, label, icon, _ in _TORRENT_FILE_TYPE_RULES
}
_TORRENT_FILE_TYPE_SUFFIXES = {
    key: suffixes
    for key, _, _, suffixes in _TORRENT_FILE_TYPE_RULES
}


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


def _torrentFileSuffix(path: str) -> str:
    suffixes = [suffix.lower() for suffix in PurePosixPath(path).suffixes]
    if not suffixes:
        return ""

    if len(suffixes) > 1:
        combined = "".join(suffixes[-2:])
        if combined in _TORRENT_FILE_TYPE_SUFFIXES["archive"]:
            return combined

    return suffixes[-1]


def _torrentFileType(path: str) -> str:
    suffix = _torrentFileSuffix(path)
    for key, _, _, suffixes in _TORRENT_FILE_TYPE_RULES:
        if suffix in suffixes:
            return key
    return "other"


class TorrentFileSelectDialog(MessageBoxBase):
    def __init__(self, task: BitTorrentTask, parent=None):
        super().__init__(parent=parent)
        self.task = task
        self._itemToFile: dict[QTreeWidgetItem, BitTorrentFile] = {}
        self._updatingChecks = False

        self.widget.setMinimumSize(720, 520)
        self.titleLabel = SubtitleLabel(self.tr("选择下载文件"), self.widget)
        self.summaryLabel = BodyLabel("", self.widget)
        self.treeWidget = TreeWidget(self.widget)
        self.actionsWidget = QWidget(self.widget)
        self.actionsLayout = QHBoxLayout(self.actionsWidget)
        self.selectAllButton = PrimaryPushButton(self.tr("全选"), self.actionsWidget)
        self.clearButton = PushButton(self.tr("全不选"), self.actionsWidget)
        self.invertButton = PushButton(self.tr("反选"), self.actionsWidget)
        self.selectByTypeButton = DropDownPushButton(self.tr("按类型选择"), self.actionsWidget)
        self.selectByTypeMenu = RoundMenu(parent=self)

        self.yesButton.setText(self.tr("应用"))
        self.cancelButton.setText(self.tr("取消"))

        self._initWidget()
        self._buildTree()
        self._updateSummary()

    def _initWidget(self):
        self.treeWidget.setColumnCount(2)
        self.treeWidget.setHeaderLabels([self.tr("文件"), self.tr("大小")])
        self.treeWidget.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.treeWidget.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.treeWidget.itemChanged.connect(self._onItemChanged)

        self.actionsLayout.setContentsMargins(0, 0, 0, 0)
        self.actionsLayout.setSpacing(8)
        self.actionsLayout.addWidget(self.selectAllButton)
        self.actionsLayout.addWidget(self.clearButton)
        self.actionsLayout.addWidget(self.invertButton)
        self.actionsLayout.addWidget(self.selectByTypeButton)
        self.actionsLayout.addStretch(1)

        self.selectAllButton.clicked.connect(self._selectAll)
        self.clearButton.clicked.connect(self._clearAll)
        self.invertButton.clicked.connect(self._invertSelection)
        self._initTypeMenu()

        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addWidget(self.summaryLabel)
        self.viewLayout.addSpacing(8)
        self.viewLayout.addWidget(self.treeWidget)
        self.viewLayout.addSpacing(8)
        self.viewLayout.addWidget(self.actionsWidget)

    def _buildTree(self):
        folderItems: dict[tuple[str, ...], QTreeWidgetItem] = {}
        self._updatingChecks = True
        provider = QFileIconProvider()
        try:
            for file in self.task.files:
                path = PurePosixPath(self.task.mappedRelativePath(file))
                parts = path.parts
                parent = self.treeWidget.invisibleRootItem()
                prefix: list[str] = []

                for part in parts[:-1]:
                    prefix.append(part)
                    key = tuple(prefix)
                    item = folderItems.get(key)
                    if item is None:
                        item = QTreeWidgetItem(parent, [part, ""])
                        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsAutoTristate)
                        item.setCheckState(0, Qt.CheckState.Unchecked)
                        item.setIcon(0, provider.icon(QFileIconProvider.IconType.Folder))
                        folderItems[key] = item
                    parent = item

                name = parts[-1]
                item = QTreeWidgetItem(parent, [name, getReadableSize(file.size)])
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(0, Qt.CheckState.Checked if file.selected else Qt.CheckState.Unchecked)
                item.setIcon(0, provider.icon(QFileInfo(name)))
                self._itemToFile[item] = file

            self.treeWidget.expandAll()
            self._refreshParentCheckStates()
        finally:
            self._updatingChecks = False

    def _initTypeMenu(self):
        for typeKey, count in self._availableFileTypes().items():
            label, icon = _TORRENT_FILE_TYPE_META.get(typeKey, (self.tr("其他"), FluentIcon.FOLDER))
            action = Action(icon, self.tr("仅选{0} ({1})").format(self.tr(label), count), self)
            action.triggered.connect(lambda _, key=typeKey: self._selectOnlyFileType(key))
            self.selectByTypeMenu.addAction(action)

        self.selectByTypeButton.setMenu(self.selectByTypeMenu)
        self.selectByTypeButton.setEnabled(bool(self.selectByTypeMenu.actions()))

    def _availableFileTypes(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for file in self.task.files:
            typeKey = _torrentFileType(file.path)
            counts[typeKey] = counts.get(typeKey, 0) + 1
        return counts

    def _refreshParentCheckStates(self):
        root = self.treeWidget.invisibleRootItem()
        for i in range(root.childCount()):
            self._updateBranchState(root.child(i))

    def _updateBranchState(self, item: QTreeWidgetItem):
        if item.childCount() == 0:
            return item.checkState(0)

        states = []
        for i in range(item.childCount()):
            states.append(self._updateBranchState(item.child(i)))

        if all(state == Qt.CheckState.Checked for state in states):
            item.setCheckState(0, Qt.CheckState.Checked)
        elif all(state == Qt.CheckState.Unchecked for state in states):
            item.setCheckState(0, Qt.CheckState.Unchecked)
        else:
            item.setCheckState(0, Qt.CheckState.PartiallyChecked)
        return item.checkState(0)

    def _setChildrenState(self, item: QTreeWidgetItem, state: Qt.CheckState):
        for i in range(item.childCount()):
            child = item.child(i)
            child.setCheckState(0, state)
            self._setChildrenState(child, state)

    def _collectSelectedIndexes(self) -> set[int]:
        return {
            file.index
            for item, file in self._itemToFile.items()
            if item.checkState(0) == Qt.CheckState.Checked
        }

    def _setSelectedIndexes(self, selectedIndexes: set[int]):
        self._updatingChecks = True
        try:
            for item, file in self._itemToFile.items():
                state = Qt.CheckState.Checked if file.index in selectedIndexes else Qt.CheckState.Unchecked
                item.setCheckState(0, state)
            self._refreshParentCheckStates()
            self._updateSummary()
        finally:
            self._updatingChecks = False

    def _updateSummary(self):
        selectedIndexes = self._collectSelectedIndexes()
        selectedFiles = [file for file in self.task.files if file.index in selectedIndexes]

        self.summaryLabel.setText(
            self.tr("已选择 {0}/{1} 个文件，共 {2}").format(
                len(selectedFiles),
                self.task.totalFileCount,
                getReadableSize(sum(file.size for file in selectedFiles)),
            )
        )

    def _onItemChanged(self, item: QTreeWidgetItem, column: int):
        if column != 0 or self._updatingChecks:
            return

        self._updatingChecks = True
        try:
            state = item.checkState(0)
            if item.childCount() > 0 and state != Qt.CheckState.PartiallyChecked:
                self._setChildrenState(item, state)
            self._refreshParentCheckStates()
            self._updateSummary()
        finally:
            self._updatingChecks = False

    def _setRootCheckState(self, state: Qt.CheckState):
        if state == Qt.CheckState.Checked:
            self._setSelectedIndexes({file.index for file in self.task.files})
            return
        self._setSelectedIndexes(set())

    def _selectAll(self):
        self._setRootCheckState(Qt.CheckState.Checked)

    def _clearAll(self):
        self._setRootCheckState(Qt.CheckState.Unchecked)

    def _invertSelection(self):
        currentSelected = self._collectSelectedIndexes()
        self._setSelectedIndexes({
            file.index
            for file in self.task.files
            if file.index not in currentSelected
        })

    def _selectOnlyFileType(self, typeKey: str):
        self._setSelectedIndexes({
            file.index
            for file in self.task.files
            if _torrentFileType(file.path) == typeKey
        })

    def validate(self) -> bool:
        if self._collectSelectedIndexes():
            return True

        InfoBar.warning(
            self.tr("至少选择一个文件"),
            self.tr("当前没有任何文件被勾选"),
            parent=self,
        )
        return False

    def selectedIndexes(self) -> set[int]:
        return self._collectSelectedIndexes()


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
            and Path(self.task.resolvePath).is_file()
        )
        self.selectFilesButton.setEnabled(self.task.status != TaskStatus.COMPLETED or self.task.hasUnselectedFiles)

    def onTaskDeleted(self, completely: bool = False):
        if not completely:
            return
        _removePath(Path(self.task.resolvePath))

    def onTaskFinished(self):
        super().onTaskFinished()
        self._refreshInfoLayout()
