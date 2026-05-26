import hashlib
from pathlib import Path, PurePosixPath

from PySide6.QtCore import QFileInfo, QSignalBlocker, Qt, QThread, Signal
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QFileDialog,
    QFileIconProvider,
    QHeaderView,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    Action,
    BodyLabel,
    CheckBox,
    ComboBox,
    DropDownPushButton,
    FluentIcon,
    InfoBar,
    LineEdit,
    MessageBoxBase,
    ProgressBar,
    PrimaryPushButton,
    PushButton,
    RadioButton,
    RoundMenu,
    SubtitleLabel,
    ToolButton,
    ToolTipFilter,
)

from app.services.category_service import UNCATEGORIZED_ID, categoryService
from app.supports.utils import toReadableSize
from app.view.components.tree_view import AutoSizingTreeView


class DeleteTaskDialog(MessageBoxBase):

    def __init__(self, parent=None, showCheckBox=True, deleteOnClose=True):
        super().__init__(parent)
        self.titleLabel = SubtitleLabel(self.tr("删除任务"), self)
        self.contentLabel = BodyLabel(
            self.tr("确定要删除此任务吗？"), self)
        self.deleteFileCheckBox = CheckBox(self.tr("删除文件"), self)

        self.deleteFileCheckBox.setVisible(showCheckBox)

        if deleteOnClose:
            self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

        self.initWidget()

    def initWidget(self):
        self.deleteFileCheckBox.setChecked(True)
        self.widget.setMinimumWidth(330)

        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addSpacing(12)
        self.viewLayout.addWidget(self.contentLabel)
        self.viewLayout.addSpacing(10)
        self.viewLayout.addWidget(self.deleteFileCheckBox)


class PlanTaskDialog(MessageBoxBase):

    SHUTDOWN = 0
    RESTART = 1
    OPEN_FILE = 2

    def __init__(self, parent=None, deleteOnClose=True):
        super().__init__(parent)
        self.titleLabel = SubtitleLabel(self.tr("设置计划任务"), self)
        self.contentLabel = BodyLabel(self.tr("所有任务完成后执行以下操作："), self)
        self.radioButtonGroup = QButtonGroup(self)
        self.powerOffButton = RadioButton(self.tr("关机"), self)
        self.restartButton = RadioButton(self.tr("重启"), self)
        self.openFileButton = RadioButton(self.tr("打开文件"), self)
        self.pathContainer = QWidget(self)
        self.pathLayout = QHBoxLayout(self.pathContainer)
        self.lineEdit = LineEdit(self.pathContainer)
        self.selectFolderButton = ToolButton(FluentIcon.FOLDER, self.pathContainer)

        if deleteOnClose:
            self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

        self.initWidget()
        self.initLayout()
        self.connectSignalToSlot()

    def initWidget(self):
        self.widget.setMinimumWidth(420)
        self.yesButton.setText(self.tr("确认"))
        self.cancelButton.setText(self.tr("取消"))

        self.radioButtonGroup.addButton(self.powerOffButton)
        self.radioButtonGroup.addButton(self.restartButton)
        self.radioButtonGroup.addButton(self.openFileButton)
        self.radioButtonGroup.setExclusive(True)
        self.powerOffButton.setChecked(True)

        self.lineEdit.setPlaceholderText(self.tr("请选择要打开的文件"))
        self.lineEdit.setClearButtonEnabled(True)
        self.selectFolderButton.setToolTip(self.tr("选择文件"))
        self.selectFolderButton.installEventFilter(ToolTipFilter(self.selectFolderButton))

        self.pathLayout.setContentsMargins(0, 0, 0, 0)
        self.pathLayout.setSpacing(8)
        self.pathLayout.addWidget(self.lineEdit, 1)
        self.pathLayout.addWidget(self.selectFolderButton)

        self._syncPathWidgets()

    def initLayout(self):
        optionsLayout = QVBoxLayout()
        optionsLayout.setContentsMargins(0, 0, 0, 0)
        optionsLayout.setSpacing(10)
        optionsLayout.addWidget(self.powerOffButton)
        optionsLayout.addWidget(self.restartButton)
        optionsLayout.addWidget(self.openFileButton)

        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addSpacing(2)
        self.viewLayout.addWidget(self.contentLabel)
        self.viewLayout.addSpacing(4)
        self.viewLayout.addLayout(optionsLayout)
        self.viewLayout.addSpacing(2)
        self.viewLayout.addWidget(self.pathContainer)

    def connectSignalToSlot(self):
        self.openFileButton.toggled.connect(self._syncPathWidgets)
        self.selectFolderButton.clicked.connect(self._chooseFile)

    def _syncPathWidgets(self):
        enabled = self.openFileButton.isChecked()
        self.pathContainer.setVisible(enabled)
        if enabled and not self.lineEdit.text().strip():
            self.lineEdit.setFocus()

    def _chooseFile(self):
        filePath, _ = QFileDialog.getOpenFileName(self, self.tr("选择文件"))
        if filePath:
            self.lineEdit.setText(filePath)

    def selectedAction(self) -> int:
        checkedButton = self.radioButtonGroup.checkedButton()
        if checkedButton is self.restartButton:
            return self.RESTART
        if checkedButton is self.openFileButton:
            return self.OPEN_FILE
        return self.SHUTDOWN

    def selectedFilePath(self) -> str:
        return self.lineEdit.text().strip()

    def validate(self) -> bool:
        if self.selectedAction() == self.OPEN_FILE and not self.selectedFilePath():
            return False

        return True


class FileHashWorker(QThread):
    progressChanged = Signal(int)
    succeeded = Signal(str)
    failed = Signal(str)

    def __init__(self, filePath: str, algorithm: str, parent=None):
        super().__init__(parent)
        self.filePath = filePath
        self.algorithm = algorithm

    def run(self):
        try:
            hasher = hashlib.new(self.algorithm)
            fileSize = Path(self.filePath).stat().st_size
            processed = 0

            with open(self.filePath, "rb") as f:
                while chunk := f.read(1024 * 1024):
                    hasher.update(chunk)
                    processed += 1024 * 1024
                    progress = 100 if fileSize == 0 else min(100, int(processed * 100 / fileSize))
                    self.progressChanged.emit(progress)

            self.progressChanged.emit(100)
            self.succeeded.emit(hasher.hexdigest())
        except Exception as e:
            message = repr(e)
            self.failed.emit(message)


class FileHashDialog(MessageBoxBase):
    hashReady = Signal(str, str)
    hashFailed = Signal(str)

    def __init__(self, filePath: str, parent=None, deleteOnClose=True):
        super().__init__(parent)
        self.filePath = filePath
        self.worker: FileHashWorker | None = None

        self.titleLabel = SubtitleLabel(self.tr("校验下载文件"), self)
        self.contentLabel = BodyLabel(self.tr("请选择要使用的校验算法"), self)
        self.algorithmComboBox = ComboBox(self)
        self.statusLabel = BodyLabel(self.tr("等待开始"), self)
        self.progressBar = ProgressBar(self)

        if deleteOnClose:
            self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

        self.initWidget()

    def initWidget(self):
        self.widget.setMinimumWidth(420)
        self.yesButton.setText(self.tr("开始校验"))
        self.cancelButton.setText(self.tr("取消"))

        algorithms = sorted(hashlib.algorithms_available)
        self.algorithmComboBox.addItems(algorithms)
        if "sha256" in algorithms:
            self.algorithmComboBox.setCurrentText("sha256")

        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addSpacing(8)
        self.viewLayout.addWidget(self.contentLabel)
        self.viewLayout.addSpacing(8)
        self.viewLayout.addWidget(self.algorithmComboBox)
        self.viewLayout.addSpacing(8)
        self.viewLayout.addWidget(self.statusLabel)
        self.viewLayout.addSpacing(4)
        self.viewLayout.addWidget(self.progressBar)

    def selectedAlgorithm(self) -> str:
        return self.algorithmComboBox.currentText().strip()

    def accept(self):
        if self.worker is not None:
            return

        self._startHash()

    def reject(self):
        if self.worker is not None:
            return

        super().reject()

    def _startHash(self):
        algorithm = self.selectedAlgorithm()
        if not algorithm:
            return

        self.algorithmComboBox.setEnabled(False)
        self.yesButton.setEnabled(False)
        self.cancelButton.setEnabled(False)
        self.progressBar.setError(False)
        self.progressBar.setValue(0)
        self.statusLabel.setText(self.tr("正在校验 {0}").format(algorithm))

        self.worker = FileHashWorker(self.filePath, algorithm, self)
        self.worker.progressChanged.connect(self._onProgressChanged)
        self.worker.succeeded.connect(self._onHashSucceeded)
        self.worker.failed.connect(self._onHashFailed)
        self.worker.start()

    def _finishWorker(self):
        worker = self.worker
        self.worker = None
        if worker is None:
            return

        worker.wait()
        worker.deleteLater()

    def _onProgressChanged(self, value: int):
        self.progressBar.setValue(value)
        self.statusLabel.setText(self.tr("正在校验 {0}%").format(value))

    def _onHashSucceeded(self, digest: str):
        algorithm = self.selectedAlgorithm()
        self.progressBar.setValue(100)
        self.statusLabel.setText(self.tr("校验完成"))
        self.hashReady.emit(algorithm, digest)
        self._finishWorker()
        super().accept()

    def _onHashFailed(self, error: str):
        self.progressBar.error()
        self.statusLabel.setText(self.tr("校验失败：{0}").format(error))
        self.hashFailed.emit(error)
        self._finishWorker()
        self.algorithmComboBox.setEnabled(True)
        self.yesButton.setEnabled(True)
        self.cancelButton.setEnabled(True)
        self.yesButton.setText(self.tr("重新校验"))


class FileSelectDialog(MessageBoxBase):

    def __init__(self, task, parent=None):
        super().__init__(parent=parent)
        self.task = task
        self._fileItems: dict[int, QStandardItem] = {}

        self.widget.setMinimumWidth(720)
        self.titleLabel = SubtitleLabel(self.tr("选择下载文件"), self.widget)
        self.summaryLabel = BodyLabel("", self.widget)
        self.treeView = AutoSizingTreeView(self.widget)
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

    def _fileDisplayPath(self, file) -> str:
        raise NotImplementedError

    def _fileTypePath(self, file) -> str:
        return self._fileDisplayPath(file)

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
            path = PurePosixPath(self._fileDisplayPath(file))
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

            name = parts[-1] if parts else self._fileDisplayPath(file)
            item = QStandardItem(name)
            item.setEditable(False)
            item.setCheckable(True)
            item.setCheckState(Qt.CheckState.Checked if file.selected else Qt.CheckState.Unchecked)
            item.setIcon(provider.icon(QFileInfo(name)))
            sizeItem = QStandardItem(toReadableSize(file.size))
            sizeItem.setEditable(False)
            parent.appendRow([item, sizeItem])
            self._fileItems[file.index] = item

        with QSignalBlocker(self.treeModel):
            for i in range(root.rowCount()):
                self._syncBranchCheckState(root.child(i))

        self.treeView.expandAll()
        self.treeView.resizeColumnToContents(0)

    def _initTypeMenu(self):
        categoryCounts = self._availableCategories()
        for categoryId, count in categoryCounts.items():
            if categoryId == UNCATEGORIZED_ID:
                continue
            category = categoryService.categoryById(categoryId)
            if category is None:
                continue
            action = Action(
                category.fluentIcon(),
                self.tr("仅选{0} ({1})").format(category.name, count),
                self,
            )
            action.triggered.connect(lambda _, cid=categoryId: self._selectOnlyCategory(cid))
            self.selectByTypeMenu.addAction(action)

        uncategorizedCount = categoryCounts.get(UNCATEGORIZED_ID, 0)
        if uncategorizedCount > 0:
            action = Action(
                FluentIcon.HELP,
                self.tr("仅选{0} ({1})").format(self.tr("其他"), uncategorizedCount),
                self,
            )
            action.triggered.connect(lambda _: self._selectOnlyCategory(UNCATEGORIZED_ID))
            self.selectByTypeMenu.addAction(action)

        self.selectByTypeButton.setMenu(self.selectByTypeMenu)
        self.selectByTypeButton.setEnabled(bool(self.selectByTypeMenu.actions()))

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

    def _availableCategories(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for file in self.task.files:
            categoryId = categoryService.matchByName(self._fileTypePath(file))
            counts[categoryId] = counts.get(categoryId, 0) + 1
        return counts

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
                state = Qt.CheckState.Checked if file.index in selectedIndexes else Qt.CheckState.Unchecked
                item.setCheckState(state)
                self._syncAncestorCheckStates(item.parent())
        self._updateSummary()

    def _updateSummary(self):
        selectedIndexes = self._collectSelectedIndexes()
        selectedFiles = [file for file in self.task.files if file.index in selectedIndexes]
        self.summaryLabel.setText(
            self.tr("已选择 {0}/{1} 个文件，共 {2}").format(
                len(selectedFiles),
                len(self.task.files),
                toReadableSize(sum(file.size for file in selectedFiles)),
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
        else:
            self._setSelectedIndexes(set())

    def _selectAll(self):
        self._setRootCheckState(Qt.CheckState.Checked)
        self.treeView.viewport().update()

    def _clearAll(self):
        self._setRootCheckState(Qt.CheckState.Unchecked)
        self.treeView.viewport().update()

    def _invertSelection(self):
        currentSelected = self._collectSelectedIndexes()
        self._setSelectedIndexes({
            file.index for file in self.task.files if file.index not in currentSelected
        })
        self.treeView.viewport().update()

    def _selectOnlyCategory(self, categoryId: str):
        self._setSelectedIndexes({
            file.index for file in self.task.files
            if categoryService.matchByName(self._fileTypePath(file)) == categoryId
        })
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
