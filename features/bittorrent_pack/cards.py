import shutil
from pathlib import Path, PurePosixPath

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHeaderView,
    QHBoxLayout,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    FluentIcon,
    ImageLabel,
    InfoBar,
    MessageBoxBase,
    PrimaryPushButton,
    PushButton,
    StrongBodyLabel,
    ToolButton,
)

from app.bases.models import TaskStatus
from app.supports.utils import getReadableSize, getReadableTime
from app.view.components.cards import ResultCard, UniversalTaskCard
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


def _setIcon(label: IconBodyLabel, icon: FluentIcon):
    label.icon = icon
    label.cachedIconKey = label.preCacheIcon()
    label.update()


class TorrentFileSelectDialog(MessageBoxBase):
    def __init__(self, task: BitTorrentTask, parent=None):
        super().__init__(parent=parent)
        self.task = task
        self._itemToFile: dict[QTreeWidgetItem, BitTorrentFile] = {}
        self._updatingChecks = False

        self.widget.setMinimumSize(720, 520)
        self.titleLabel = StrongBodyLabel(self.tr("选择下载文件"), self.widget)
        self.summaryLabel = CaptionLabel("", self.widget)
        self.treeWidget = QTreeWidget(self.widget)
        self.actionsWidget = QWidget(self.widget)
        self.actionsLayout = QHBoxLayout(self.actionsWidget)
        self.selectAllButton = PushButton(self.tr("全选"), self.actionsWidget)
        self.clearButton = PushButton(self.tr("全不选"), self.actionsWidget)

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
        self.actionsLayout.addStretch(1)

        self.selectAllButton.clicked.connect(self._selectAll)
        self.clearButton.clicked.connect(self._clearAll)

        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addWidget(self.summaryLabel)
        self.viewLayout.addSpacing(8)
        self.viewLayout.addWidget(self.treeWidget)
        self.viewLayout.addSpacing(8)
        self.viewLayout.addWidget(self.actionsWidget)

    def _buildTree(self):
        folderItems: dict[tuple[str, ...], QTreeWidgetItem] = {}
        self._updatingChecks = True
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
                        folderItems[key] = item
                    parent = item

                item = QTreeWidgetItem(parent, [parts[-1], getReadableSize(file.size)])
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(0, Qt.CheckState.Checked if file.selected else Qt.CheckState.Unchecked)
                self._itemToFile[item] = file

            self.treeWidget.expandAll()
            self._refreshParentCheckStates()
        finally:
            self._updatingChecks = False

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
        self._updatingChecks = True
        try:
            root = self.treeWidget.invisibleRootItem()
            for i in range(root.childCount()):
                item = root.child(i)
                item.setCheckState(0, state)
                self._setChildrenState(item, state)
            self._refreshParentCheckStates()
            self._updateSummary()
        finally:
            self._updatingChecks = False

    def _selectAll(self):
        self._setRootCheckState(Qt.CheckState.Checked)

    def _clearAll(self):
        self._setRootCheckState(Qt.CheckState.Unchecked)

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
        self.iconLabel = ImageLabel(self)
        self.titleLabel = StrongBodyLabel(self.task.title, self)
        self.sourceLabel = CaptionLabel(self._sourceText(), self)
        self.summaryLabel = BodyLabel("", self)
        self.selectFilesButton = PrimaryPushButton(self.tr("选择文件"), self)

        self._initWidget()
        self._initLayout()
        self._refreshSummary()

    def _initWidget(self):
        self.setFixedHeight(56)
        self.iconLabel.setFixedSize(18, 18)
        icon = FluentIcon.DOCUMENT if self.task.isSingleFileTorrent else FluentIcon.FOLDER
        self.iconLabel.setImage(icon.icon().pixmap(18, 18))
        self.selectFilesButton.clicked.connect(self._onSelectFilesClicked)

    def _initLayout(self):
        self.mainLayout.setContentsMargins(10, 6, 10, 6)
        self.mainLayout.setSpacing(12)
        self.textLayout.setContentsMargins(0, 0, 0, 0)
        self.textLayout.setSpacing(2)
        self.textLayout.addWidget(self.titleLabel)
        self.textLayout.addWidget(self.sourceLabel)
        self.mainLayout.addWidget(self.iconLabel, 0, Qt.AlignmentFlag.AlignTop)
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
        self.metaInfoLabel = None
        self.selectFilesButton = None
        super().__init__(task, parent)
        self.task: BitTorrentTask = task
        _setIcon(self.speedLabel, FluentIcon.DOWNLOAD)
        _setIcon(self.leftTimeLabel, FluentIcon.SHARE)
        self.metaInfoLabel = IconBodyLabel("", FluentIcon.INFO, self)
        self.infoLayout.insertWidget(self.infoLayout.count() - 2, self.metaInfoLabel)
        self.selectFilesButton = ToolButton(FluentIcon.LIBRARY, self)
        self.hBoxLayout.insertWidget(self.hBoxLayout.count() - 3, self.selectFilesButton)
        self.selectFilesButton.clicked.connect(self._onSelectFilesClicked)
        self._refreshInfoLayout()

    def _metaText(self) -> str:
        stage = self.task.stage
        if stage is None:
            return ""

        parts: list[str] = []
        if stage.stateText and stage.stateText not in {"下载中", "做种中"}:
            parts.append(stage.stateText)
        if stage.isSeeding and stage.shareRatioPercent > 0:
            parts.append(self.tr("分享率 {0:.2f}%").format(stage.shareRatioPercent))
        if stage.isSeeding and stage.seedingTimeSeconds > 0:
            parts.append(self.tr("做种 {0}").format(getReadableTime(stage.seedingTimeSeconds)))
        if stage.peerCount or stage.seedCount:
            parts.append(
                self.tr("Peers {0} / Seeds {1}").format(
                    stage.peerCount,
                    stage.seedCount,
                )
            )
        return " · ".join(parts)

    def _refreshInfoLayout(self):
        stage = self.task.stage
        if self.task.status == TaskStatus.RUNNING and stage is not None:
            self.speedLabel.setText(f"{getReadableSize(stage.downloadRate)}/s")
            self.leftTimeLabel.setText(f"{getReadableSize(stage.uploadRate)}/s")
            metaText = self._metaText()
            self.metaInfoLabel.setText(metaText)
            self.metaInfoLabel.setVisible(bool(metaText))
            self.speedLabel.show()
            self.leftTimeLabel.show()
            self.progressLabel.show()
            if not metaText:
                self.metaInfoLabel.hide()
            self.infoLabel.hide()
            return

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
