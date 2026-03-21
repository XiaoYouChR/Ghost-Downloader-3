import shutil
from pathlib import Path, PurePosixPath

from PySide6.QtCore import QEvent, QFileInfo, QSignalBlocker, Qt
from PySide6.QtGui import QMouseEvent, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileIconProvider,
    QHeaderView,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    Action,
    BodyLabel,
    CaptionLabel,
    DropDownPushButton,
    FluentIcon,
    IconWidget,
    InfoBar,
    LineEdit,
    MessageBoxBase,
    PrimaryPushButton,
    PushButton,
    RoundMenu,
    StrongBodyLabel,
    ToolButton,
    TreeView,
)

from app.bases.models import TaskStatus
from app.supports.utils import getReadableSize, getReadableTime, openFile, openFolder
from app.view.components.cards import ResultCard, UniversalTaskCard

from .task import FtpTask

_FILE_TYPE_RULES = (
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

_FILE_TYPE_META = {
    key: (label, icon)
    for key, label, icon, _ in _FILE_TYPE_RULES
}
_FILE_TYPE_SUFFIXES = {
    key: suffixes
    for key, _, _, suffixes in _FILE_TYPE_RULES
}


def _removePath(path: Path):
    if not path.exists():
        return
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
        return
    path.unlink(missing_ok=True)


def _ftpFileSuffix(path: str) -> str:
    suffixes = [suffix.lower() for suffix in PurePosixPath(path).suffixes]
    if not suffixes:
        return ""

    if len(suffixes) > 1:
        combined = "".join(suffixes[-2:])
        if combined in _FILE_TYPE_SUFFIXES["archive"]:
            return combined
    return suffixes[-1]


def _ftpFileType(path: str) -> str:
    suffix = _ftpFileSuffix(path)
    for key, _, _, suffixes in _FILE_TYPE_RULES:
        if suffix in suffixes:
            return key
    return "other"


def _openFileSelection(task: FtpTask, parent) -> set[int] | None:
    dialog = FtpFileSelectDialog(task, parent)
    try:
        if not dialog.exec():
            return None
        selectedIndexes = dialog.selectedIndexes()
        task.updateSelectedFiles(selectedIndexes)
        return selectedIndexes
    finally:
        dialog.deleteLater()


class FtpFileSelectDialog(MessageBoxBase):
    def __init__(self, task: FtpTask, parent=None):
        super().__init__(parent=parent)
        self.task = task
        self._fileItems: dict[int, QStandardItem] = {}

        self.widget.setMinimumSize(720, 520)
        self.titleLabel = StrongBodyLabel(self.tr("选择下载文件"), self.widget)
        self.summaryLabel = BodyLabel("", self.widget)
        self.treeView = TreeView(self.widget)
        self.treeModel = QStandardItemModel(self.treeView)
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
        self.treeModel.setHorizontalHeaderLabels([self.tr("文件"), self.tr("大小")])
        self.treeView.setModel(self.treeModel)
        self.treeView.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.treeView.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.treeView.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.treeModel.itemChanged.connect(self._onItemChanged)

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
        self.viewLayout.addWidget(self.treeView)
        self.viewLayout.addSpacing(8)
        self.viewLayout.addWidget(self.actionsWidget)

    def _buildTree(self):
        folderItems: dict[tuple[str, ...], QStandardItem] = {}
        provider = QFileIconProvider()
        root = self.treeModel.invisibleRootItem()

        for file in self.task.files:
            path = PurePosixPath(file.relativePath)
            parts = path.parts
            parent = root
            prefix: list[str] = []

            for part in parts[:-1]:
                prefix.append(part)
                key = tuple(prefix)
                item = folderItems.get(key)
                if item is None:
                    item = QStandardItem(part)
                    item.setEditable(False)
                    item.setCheckable(True)
                    item.setCheckState(Qt.CheckState.Unchecked)
                    item.setIcon(provider.icon(QFileIconProvider.IconType.Folder))
                    sizeItem = QStandardItem("")
                    sizeItem.setEditable(False)
                    parent.appendRow([item, sizeItem])
                    folderItems[key] = item
                parent = item

            item = QStandardItem(parts[-1] if parts else file.relativePath)
            item.setEditable(False)
            item.setCheckable(True)
            item.setCheckState(
                Qt.CheckState.Checked if file.selected else Qt.CheckState.Unchecked
            )
            item.setIcon(provider.icon(QFileInfo(item.text())))
            sizeItem = QStandardItem(getReadableSize(file.size))
            sizeItem.setEditable(False)
            parent.appendRow([item, sizeItem])
            self._fileItems[file.index] = item

        with QSignalBlocker(self.treeModel):
            for i in range(root.rowCount()):
                self._syncBranchCheckState(root.child(i))

        self.treeView.expandAll()
        self.treeView.resizeColumnToContents(0)

    def _initTypeMenu(self):
        for typeKey, count in self._availableFileTypes().items():
            label, icon = _FILE_TYPE_META.get(typeKey, (self.tr("其他"), FluentIcon.FOLDER))
            action = Action(
                icon,
                self.tr("仅选{0} ({1})").format(self.tr(label), count),
                self,
            )
            action.triggered.connect(lambda _, key=typeKey: self._selectOnlyFileType(key))
            self.selectByTypeMenu.addAction(action)

        self.selectByTypeButton.setMenu(self.selectByTypeMenu)
        self.selectByTypeButton.setEnabled(bool(self.selectByTypeMenu.actions()))

    def _availableFileTypes(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for file in self.task.files:
            typeKey = _ftpFileType(file.relativePath)
            counts[typeKey] = counts.get(typeKey, 0) + 1
        return counts

    def _syncBranchCheckState(self, item: QStandardItem):
        if item.rowCount() == 0:
            return item.checkState()

        states = [self._syncBranchCheckState(item.child(i)) for i in range(item.rowCount())]
        if all(state == Qt.CheckState.Checked for state in states):
            item.setCheckState(Qt.CheckState.Checked)
        elif all(state == Qt.CheckState.Unchecked for state in states):
            item.setCheckState(Qt.CheckState.Unchecked)
        else:
            item.setCheckState(Qt.CheckState.PartiallyChecked)
        return item.checkState()

    def _syncAncestorCheckStates(self, item: QStandardItem | None):
        while item is not None:
            states = [item.child(i).checkState() for i in range(item.rowCount())]
            if all(state == Qt.CheckState.Checked for state in states):
                item.setCheckState(Qt.CheckState.Checked)
            elif all(state == Qt.CheckState.Unchecked for state in states):
                item.setCheckState(Qt.CheckState.Unchecked)
            else:
                item.setCheckState(Qt.CheckState.PartiallyChecked)
            item = item.parent()

    def _setChildrenCheckState(self, item: QStandardItem, state: Qt.CheckState):
        for i in range(item.rowCount()):
            child = item.child(i)
            child.setCheckState(state)
            self._setChildrenCheckState(child, state)

    def _collectSelectedIndexes(self) -> set[int]:
        return {
            file.index
            for file in self.task.files
            if self._fileItems[file.index].checkState() == Qt.CheckState.Checked
        }

    def _setSelectedIndexes(self, selectedIndexes: set[int]):
        with QSignalBlocker(self.treeModel):
            for file in self.task.files:
                item = self._fileItems[file.index]
                state = (
                    Qt.CheckState.Checked
                    if file.index in selectedIndexes
                    else Qt.CheckState.Unchecked
                )
                item.setCheckState(state)
                self._syncAncestorCheckStates(item.parent())
        self._updateSummary()

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

    def _onItemChanged(self, item: QStandardItem):
        if item.column() != 0:
            return

        with QSignalBlocker(self.treeModel):
            if item.rowCount() > 0 and item.checkState() != Qt.CheckState.PartiallyChecked:
                self._setChildrenCheckState(item, item.checkState())
            self._syncAncestorCheckStates(item.parent())
        self._updateSummary()
        self.treeView.viewport().update()

    def _setRootCheckState(self, state: Qt.CheckState):
        if state == Qt.CheckState.Checked:
            self._setSelectedIndexes({file.index for file in self.task.files})
            return
        self._setSelectedIndexes(set())

    def _selectAll(self):
        self._setRootCheckState(Qt.CheckState.Checked)
        self.treeView.viewport().update()

    def _clearAll(self):
        self._setRootCheckState(Qt.CheckState.Unchecked)
        self.treeView.viewport().update()

    def _invertSelection(self):
        currentSelected = self._collectSelectedIndexes()
        self._setSelectedIndexes(
            {
                file.index
                for file in self.task.files
                if file.index not in currentSelected
            }
        )
        self.treeView.viewport().update()

    def _selectOnlyFileType(self, typeKey: str):
        self._setSelectedIndexes(
            {
                file.index
                for file in self.task.files
                if _ftpFileType(file.relativePath) == typeKey
            }
        )
        self.treeView.viewport().update()

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


class FtpResultCard(ResultCard):
    def __init__(self, task: FtpTask, parent: QWidget = None):
        super().__init__(task, parent)
        self.task = task

        self.mainLayout = QHBoxLayout(self)
        self.textLayout = QVBoxLayout()
        self.iconLabel = IconWidget(self)
        self.titleLabel = StrongBodyLabel(self.task.title, self)
        self.titleEdit = LineEdit(self)
        self.sourceLabel = CaptionLabel(self._sourceText(), self)
        self.summaryLabel = BodyLabel("", self)
        self.selectFilesButton = PrimaryPushButton(self.tr("选择文件"), self)

        self._initWidget()
        self._initLayout()
        self._refreshSummary()

    def _initWidget(self):
        self.setFixedHeight(50)
        icon = (
            QFileIconProvider().icon(QFileIconProvider.IconType.Folder)
            if self.task.isDirectorySource
            else QFileIconProvider().icon(QFileInfo(self.task.resolvePath))
        )
        self.iconLabel.setIcon(icon)
        self.iconLabel.setFixedSize(20, 20)
        self.titleLabel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.titleLabel.installEventFilter(self)
        self.titleEdit.setText(self.task.title)
        self.titleEdit.editingFinished.connect(self._onEditingFinished)
        self.titleEdit.hide()
        self.selectFilesButton.setVisible(self.task.totalFileCount > 1)
        self.selectFilesButton.clicked.connect(self._onSelectFilesClicked)

    def _initLayout(self):
        self.mainLayout.setContentsMargins(10, 6, 10, 6)
        self.mainLayout.setSpacing(12)
        self.textLayout.setContentsMargins(0, 0, 0, 0)
        self.textLayout.setSpacing(2)
        self.textLayout.addWidget(self.titleLabel)
        self.textLayout.addWidget(self.titleEdit)
        self.textLayout.addWidget(self.sourceLabel)
        self.mainLayout.addWidget(self.iconLabel, 0, Qt.AlignmentFlag.AlignCenter)
        self.mainLayout.addLayout(self.textLayout)
        self.mainLayout.addStretch(1)
        self.mainLayout.addWidget(self.summaryLabel)
        self.mainLayout.addSpacing(12)
        self.mainLayout.addWidget(self.selectFilesButton)

    def eventFilter(self, obj, event: QEvent):
        if obj is self.titleLabel:
            if event.type() == QEvent.Type.MouseButtonDblClick and isinstance(event, QMouseEvent):
                if event.button() == Qt.MouseButton.LeftButton:
                    self._enterEditMode()
                    return True
        return super().eventFilter(obj, event)

    def _enterEditMode(self):
        self.titleLabel.hide()
        self.titleEdit.show()
        self.titleEdit.setFocus()
        self.titleEdit.selectAll()

    def _onEditingFinished(self):
        newTitle = self.titleEdit.text().strip()
        if newTitle and newTitle != self.task.title:
            self.task.setTitle(newTitle)
            self.titleLabel.setText(self.task.title)
            self.titleEdit.setText(self.task.title)

        self.titleEdit.hide()
        self.titleLabel.show()
        self.titleLabel.setFocus()

    def _sourceText(self) -> str:
        sourceType = self.tr("FTP 目录") if self.task.isDirectorySource else self.tr("FTP 文件")
        return self.tr("{0} · {1}").format(
            sourceType,
            self.task.connectionInfo.host,
        )

    def _refreshSummary(self):
        if self.task.totalFileCount > 1 or self.task.isDirectorySource:
            self.summaryLabel.setText(
                self.tr("{0}/{1} 个文件 · {2}").format(
                    self.task.selectedFileCount,
                    self.task.totalFileCount,
                    getReadableSize(self.task.fileSize),
                )
            )
            return

        self.summaryLabel.setText(getReadableSize(self.task.fileSize))

    def _onSelectFilesClicked(self):
        if _openFileSelection(self.task, self.window()) is not None:
            self._refreshSummary()

    def getTask(self) -> FtpTask:
        return self.task


class FtpTaskCard(UniversalTaskCard):
    def __init__(self, task: FtpTask, parent=None):
        super().__init__(task, parent)
        self.task = task
        self.selectFilesButton = ToolButton(FluentIcon.LIBRARY, self)
        self.hBoxLayout.insertWidget(
            self.hBoxLayout.indexOf(self.verifyHashButton),
            self.selectFilesButton,
        )
        self.selectFilesButton.clicked.connect(self._onSelectFilesClicked)
        self.openFileButton.clicked.disconnect()
        self.openFolderButton.clicked.disconnect()
        self.openFileButton.clicked.connect(self._openPrimaryTarget)
        self.openFolderButton.clicked.connect(self._openTaskFolder)
        self._refreshIconLabel()

    def _refreshIconLabel(self):
        if self.task.isDirectorySource:
            icon = QFileIconProvider().icon(QFileIconProvider.IconType.Folder)
        else:
            icon = QFileIconProvider().icon(QFileInfo(self.task.resolvePath))
        self.iconLabel.setPixmap(icon.pixmap(48, 48))
        self.iconLabel.setFixedSize(48, 48)

    def _selectedStageStats(self) -> tuple[int, int]:
        receivedBytes = 0
        speed = 0
        for stage in self.task.selectedStages:
            receivedBytes += stage.receivedBytes
            speed += stage.speed
        return receivedBytes, speed

    def _openPrimaryTarget(self):
        openFile(self.task.resolvePath)

    def _openTaskFolder(self):
        target = Path(self.task.resolvePath)
        if target.exists():
            openFolder(str(target))
            return
        openFolder(str(target.parent))

    def _renderTaskState(self):
        super()._renderTaskState()

        receivedBytes, speed = self._selectedStageStats()
        if self.task.fileSize > 0:
            self.progressBar.setValue(receivedBytes / self.task.fileSize * 100)
            self.progressLabel.setText(
                f"{getReadableSize(receivedBytes)}/{getReadableSize(self.task.fileSize)}"
            )
        else:
            self.progressLabel.setText(f"{getReadableSize(receivedBytes)}/--")

        if self.task.status == TaskStatus.RUNNING:
            self.speedLabel.setText(f"{getReadableSize(speed)}/s")
            if self.task.fileSize > 0 and speed > 0:
                remaining = max(0, self.task.fileSize - receivedBytes)
                self.leftTimeLabel.setText(getReadableTime(int(remaining / speed)))
            elif self.task.fileSize > 0:
                self.leftTimeLabel.setText("--")

        if self.task.status in {TaskStatus.WAITING, TaskStatus.PAUSED, TaskStatus.COMPLETED}:
            if self.task.totalFileCount > 1 or self.task.isDirectorySource:
                self.showStatusInfo(
                    self.tr("{0}/{1} 个文件").format(
                        self.task.selectedFileCount,
                        self.task.totalFileCount,
                    )
                )

    def _onSelectFilesClicked(self):
        if self.task.status == TaskStatus.RUNNING:
            return

        previousSelected = {
            file.index for file in self.task.files if file.selected
        }
        selectedIndexes = _openFileSelection(self.task, self.window())
        if selectedIndexes is None:
            return

        if (
            self.task.status == TaskStatus.COMPLETED
            and selectedIndexes - previousSelected
            and self.task.reopenForAdditionalFiles()
        ):
            self.resumeTask()
            return

        self.cardStatus = self.task.status
        self._renderTaskState()

    def refresh(self):
        super().refresh()
        self.verifyHashButton.setVisible(
            not self.task.isDirectorySource
            and self.task.selectedFileCount == 1
            and self.task.status == TaskStatus.COMPLETED
            and Path(self.task.resolvePath).is_file()
        )
        self.selectFilesButton.setVisible(self.task.totalFileCount > 1)
        self.selectFilesButton.setEnabled(self.task.status != TaskStatus.RUNNING)

    def onTaskDeleted(self, completely: bool = False):
        if not completely:
            return

        if self.task.isDirectorySource:
            _removePath(Path(self.task.resolvePath))
            return

        for stage in self.task.stages:
            resolvePath = stage.resolvePath.strip()
            if not resolvePath:
                continue
            target = Path(resolvePath)
            _removePath(target)
            _removePath(Path(str(target) + ".ghd"))
