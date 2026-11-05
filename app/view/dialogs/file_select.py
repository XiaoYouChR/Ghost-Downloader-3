from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QFileInfo, QModelIndex, QSignalBlocker, QTimer
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView, QFileIconProvider, QHBoxLayout, QHeaderView, QWidget,
)
from qfluentwidgets import (
    Action, BodyLabel, DropDownPushButton, FluentIcon, InfoBar,
    MessageBoxBase, PrimaryPushButton, PushButton, RoundMenu, SearchLineEdit, SubtitleLabel,
)

from app.format import toReadableSize
from app.view.components.category_settings import toCategoryName
from app.view.components.tree_view import AutoSizingTreeView

if TYPE_CHECKING:
    from app.models.task import Task

FILE_INDEX_ROLE = Qt.ItemDataRole.UserRole


class FileSelectDialog(MessageBoxBase):

    def __init__(self, task: Task, categoryService, parent=None):
        super().__init__(parent)
        self._task = task
        self._categoryService = categoryService
        self._fileItems: dict[int, QStandardItem] = {}
        self._pathByIndex: dict[int, str] = {}
        self._categoryByIndex: dict[int, str] = {}
        self._typeActions: dict[str, Action] = {}
        self._selected = {file.index for file in task.files or [] if file.selected}
        self._shownIndexes: set[int] = set()
        self._query = ""

        self.titleLabel = SubtitleLabel(self.tr("选择下载文件"), self)
        self.summaryLabel = BodyLabel("", self)
        self.searchEdit = SearchLineEdit(self)
        self.treeView = AutoSizingTreeView(self, minimumVisibleRows=3)
        self.treeModel = QStandardItemModel(self.treeView)
        self.emptyLabel = BodyLabel(self.tr("没有匹配的文件"), self.treeView)
        self._searchTimer = QTimer(self)

        self.selectAllButton = PrimaryPushButton(self.tr("全选"), self)
        self.clearButton = PushButton(self.tr("全不选"), self)
        self.invertButton = PushButton(self.tr("反选"), self)
        self.selectByTypeButton = DropDownPushButton(self.tr("按类型选择"), self)
        self.selectByTypeMenu = RoundMenu(parent=self)

        self._initWidget()
        self._initLayout()
        self._buildTree()
        self._buildTypeMenu()
        self._updateRows()
        self._bind()

    def _fileDisplayPath(self, file) -> str:
        return self._task.toDisplayPath(file)

    def _initWidget(self) -> None:
        self.widget.setMinimumWidth(720)
        self.yesButton.setText(self.tr("应用"))
        self.cancelButton.setText(self.tr("取消"))
        self.searchEdit.setPlaceholderText(self.tr("搜索文件"))
        self.emptyLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.emptyLabel.hide()
        self._searchTimer.setSingleShot(True)
        self._searchTimer.setInterval(200)

        self.treeModel.setHorizontalHeaderLabels([self.tr("文件"), self.tr("大小")])
        self.treeView.setModel(self.treeModel)
        self.treeView.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.treeView.setUniformRowHeights(True)
        self.treeView.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.treeView.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)

    def _initLayout(self) -> None:
        actionsLayout = QHBoxLayout()
        actionsLayout.setContentsMargins(0, 0, 0, 0)
        actionsLayout.setSpacing(8)
        actionsLayout.addWidget(self.selectAllButton)
        actionsLayout.addWidget(self.clearButton)
        actionsLayout.addWidget(self.invertButton)
        actionsLayout.addWidget(self.selectByTypeButton)
        actionsLayout.addStretch(1)

        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addWidget(self.summaryLabel)
        self.viewLayout.addSpacing(8)
        self.viewLayout.addWidget(self.searchEdit)
        self.viewLayout.addWidget(self.treeView)
        self.viewLayout.addSpacing(8)
        self.viewLayout.addLayout(actionsLayout)

    def _bind(self) -> None:
        self.treeModel.itemChanged.connect(self._onItemChanged)
        self.searchEdit.textChanged.connect(self._searchTimer.start)
        self._searchTimer.timeout.connect(self._onSearchTimedOut)
        self.selectAllButton.clicked.connect(lambda: self._setShownSelection(self._shownIndexes))
        self.clearButton.clicked.connect(lambda: self._setShownSelection(set()))
        self.invertButton.clicked.connect(lambda: self._setShownSelection(self._shownIndexes - self._selected))

    def _buildTree(self) -> None:
        folderItems: dict[tuple[str, ...], QStandardItem] = {}
        provider = QFileIconProvider()
        root = self.treeModel.invisibleRootItem()

        for file in self._task.files or []:
            path = self._fileDisplayPath(file)
            parts = path.split("/")
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
                    item.setIcon(provider.icon(QFileIconProvider.IconType.Folder))
                    sizeItem = QStandardItem("")
                    sizeItem.setEditable(False)
                    parent.appendRow([item, sizeItem])
                    folderItems[key] = item
                parent = item

            name = parts[-1] if parts else path
            item = QStandardItem(name)
            item.setEditable(False)
            item.setCheckable(True)
            item.setData(file.index, FILE_INDEX_ROLE)
            item.setIcon(provider.icon(QFileInfo(name)))
            sizeItem = QStandardItem(toReadableSize(file.size))
            sizeItem.setEditable(False)
            parent.appendRow([item, sizeItem])
            self._fileItems[file.index] = item
            self._pathByIndex[file.index] = path.lower()

        self.treeView.expandAll()
        self.treeView.resizeColumnToContents(0)

    def _buildTypeMenu(self) -> None:
        for file in self._task.files or []:
            self._categoryByIndex[file.index] = self._categoryService.matchByName(file.relativePath)

        for categoryId in dict.fromkeys(self._categoryByIndex.values()):
            if categoryId:
                category = self._categoryService.categoryById(categoryId)
                if category is None:
                    continue
                icon, name = getattr(FluentIcon, category.icon, FluentIcon.TAG), toCategoryName(category)
            else:
                icon, name = FluentIcon.HELP, self.tr("其他")
            action = Action(icon, name, self)
            action.setData(name)
            action.triggered.connect(lambda _, cid=categoryId: self._selectCategory(cid))
            self._typeActions[categoryId] = action
        for categoryId in sorted(self._typeActions, key=lambda categoryId: not categoryId):
            self.selectByTypeMenu.addAction(self._typeActions[categoryId])
        self.selectByTypeButton.setMenu(self.selectByTypeMenu)

    def _onItemChanged(self, item: QStandardItem) -> None:
        if item.column() != 0:
            return
        fileIndex = item.data(FILE_INDEX_ROLE)
        indexes = {fileIndex} if fileIndex is not None else self._shownIndexesUnder(item)
        if item.checkState() == Qt.CheckState.Checked:
            self._setSelectedIndexes(self._selected | indexes)
        else:
            self._setSelectedIndexes(self._selected - indexes)

    def _onSearchTimedOut(self) -> None:
        self._query = self.searchEdit.text().strip().lower()
        self._updateRows()
        if self._query:
            self.treeView.expandAll()

    def _shownIndexesUnder(self, item: QStandardItem) -> set[int]:
        fileIndex = item.data(FILE_INDEX_ROLE)
        if fileIndex is not None:
            return {fileIndex} & self._shownIndexes
        return set().union(*(self._shownIndexesUnder(item.child(row)) for row in range(item.rowCount())))

    def _setSelectedIndexes(self, selectedIndexes: set[int]) -> None:
        self._selected = set(selectedIndexes)
        self._updateRows()

    def _setShownSelection(self, chosen: set[int]) -> None:
        self._setSelectedIndexes(self._selected - self._shownIndexes | chosen)

    def _selectCategory(self, categoryId: str) -> None:
        self._setShownSelection({index for index in self._shownIndexes if self._categoryByIndex[index] == categoryId})

    def _updateRows(self) -> None:
        self._shownIndexes = {index for index, path in self._pathByIndex.items() if self._query in path}
        root = self.treeModel.invisibleRootItem()
        with QSignalBlocker(self.treeModel):
            for row in range(root.rowCount()):
                self._updateRow(root.child(row))
        self.treeView.viewport().update()

        isAnyShown = bool(self._shownIndexes)
        self.emptyLabel.setGeometry(self.treeView.viewport().geometry())
        self.emptyLabel.setVisible(not isAnyShown)
        for button in (self.selectAllButton, self.clearButton, self.invertButton):
            button.setEnabled(isAnyShown)
        self._updateTypeMenu()
        self._updateSummary()

    def _updateRow(self, item: QStandardItem) -> Qt.CheckState | None:
        fileIndex = item.data(FILE_INDEX_ROLE)
        if fileIndex is not None:
            if fileIndex not in self._shownIndexes:
                state = None
            else:
                state = Qt.CheckState.Checked if fileIndex in self._selected else Qt.CheckState.Unchecked
        else:
            states = {self._updateRow(item.child(row)) for row in range(item.rowCount())} - {None}
            state = states.pop() if len(states) == 1 else Qt.CheckState.PartiallyChecked if states else None
        parent = item.parent()
        parentIndex = parent.index() if parent else QModelIndex()
        if self.treeView.isRowHidden(item.row(), parentIndex) != (state is None):
            self.treeView.setRowHidden(item.row(), parentIndex, state is None)
        if state is not None and item.checkState() != state:
            item.setCheckState(state)
        return state

    def _updateTypeMenu(self) -> None:
        counts = {categoryId: 0 for categoryId in self._typeActions}
        for index in self._shownIndexes:
            if self._categoryByIndex[index] in counts:
                counts[self._categoryByIndex[index]] += 1
        for categoryId, action in self._typeActions.items():
            action.setText(self.tr("仅选{0} ({1})").format(action.data(), counts[categoryId]))
            action.setEnabled(counts[categoryId] > 0)
        self.selectByTypeButton.setEnabled(any(counts.values()))

    def _updateSummary(self) -> None:
        size = sum(file.size for file in self._task.files or [] if file.index in self._selected)
        text = self.tr("已选择 {0}/{1} 个文件，共 {2}").format(
            len(self._selected), len(self._fileItems), toReadableSize(size))
        if self._query:
            text += self.tr("，显示 {0} 个").format(len(self._shownIndexes))
        self.summaryLabel.setText(text)

    def selectedIndexes(self) -> set[int]:
        return set(self._selected)

    def validate(self) -> bool:
        if self._selected:
            return True
        InfoBar.warning(
            self.tr("至少选择一个文件"),
            self.tr("当前没有任何文件被勾选"),
            parent=self,
        )
        return False
