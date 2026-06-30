from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QFileInfo, QSignalBlocker
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView, QFileIconProvider, QHBoxLayout, QHeaderView, QWidget,
)
from qfluentwidgets import (
    Action, BodyLabel, DropDownPushButton, FluentIcon, InfoBar,
    MessageBoxBase, PrimaryPushButton, PushButton, RoundMenu, SubtitleLabel,
)

from app.format import toReadableSize
from app.services.category_service import categoryService
from app.view.components.tree_view import AutoSizingTreeView

if TYPE_CHECKING:
    from app.models.task import Task


class FileSelectDialog(MessageBoxBase):

    def __init__(self, task: Task, parent=None):
        super().__init__(parent)
        self._task = task
        self._fileItems: dict[int, QStandardItem] = {}

        self.titleLabel = SubtitleLabel(self.tr("选择下载文件"), self)
        self.summaryLabel = BodyLabel("", self)
        self.treeView = AutoSizingTreeView(self, minimumVisibleRows=3, maximumVisibleRows=16)
        self.treeModel = QStandardItemModel(self.treeView)

        self.selectAllButton = PrimaryPushButton(self.tr("全选"), self)
        self.clearButton = PushButton(self.tr("全不选"), self)
        self.invertButton = PushButton(self.tr("反选"), self)
        self.selectByTypeButton = DropDownPushButton(self.tr("按类型选择"), self)
        self.selectByTypeMenu = RoundMenu(parent=self)

        self._initWidget()
        self._initLayout()
        self._buildTree()
        self._buildTypeMenu()
        self._updateSummary()
        self._bind()

    def _fileDisplayPath(self, file) -> str:
        return file.relativePath

    def _initWidget(self) -> None:
        self.widget.setMinimumWidth(720)
        self.yesButton.setText(self.tr("应用"))
        self.cancelButton.setText(self.tr("取消"))

        self.treeModel.setHorizontalHeaderLabels([self.tr("文件"), self.tr("大小")])
        self.treeView.setModel(self.treeModel)
        self.treeView.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
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
        self.viewLayout.addWidget(self.treeView)
        self.viewLayout.addSpacing(8)
        self.viewLayout.addLayout(actionsLayout)

    def _bind(self) -> None:
        self.treeModel.itemChanged.connect(self._onItemChanged)
        self.selectAllButton.clicked.connect(lambda: self._setAll(True))
        self.clearButton.clicked.connect(lambda: self._setAll(False))
        self.invertButton.clicked.connect(self._invertSelection)

    def _buildTree(self) -> None:
        folderItems: dict[tuple[str, ...], QStandardItem] = {}
        provider = QFileIconProvider()
        root = self.treeModel.invisibleRootItem()

        for file in self._task.files or []:
            parts = self._fileDisplayPath(file).split("/")
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

        for i in range(root.rowCount()):
            self._updateBranchCheckState(root.child(i))

        self.treeView.expandAll()
        self.treeView.resizeColumnToContents(0)

    def _buildTypeMenu(self) -> None:
        counts: dict[str, int] = {}
        for file in self._task.files or []:
            categoryId = categoryService.matchByName(file.relativePath)
            if categoryId:
                counts[categoryId] = counts.get(categoryId, 0) + 1

        for categoryId, count in counts.items():
            category = categoryService.categoryById(categoryId)
            if category is None:
                continue
            action = Action(
                category.toIcon(),
                self.tr("仅选{0} ({1})").format(category.name, count),
                self,
            )
            action.triggered.connect(lambda _, cid=categoryId: self._selectCategory(cid))
            self.selectByTypeMenu.addAction(action)

        uncategorized = sum(
            1 for f in self._task.files or []
            if not categoryService.matchByName(f.relativePath)
        )
        if uncategorized > 0:
            action = Action(
                FluentIcon.HELP,
                self.tr("仅选{0} ({1})").format(self.tr("其他"), uncategorized),
                self,
            )
            action.triggered.connect(lambda _: self._selectCategory(""))
            self.selectByTypeMenu.addAction(action)

        self.selectByTypeButton.setMenu(self.selectByTypeMenu)
        self.selectByTypeButton.setEnabled(bool(self.selectByTypeMenu.actions()))

    def _onItemChanged(self, item: QStandardItem) -> None:
        if item.column() != 0:
            return
        with QSignalBlocker(self.treeModel):
            if item.rowCount() > 0 and item.checkState() != Qt.CheckState.PartiallyChecked:
                self._setChildrenCheckState(item, item.checkState())
            self._updateAncestorCheckStates(item.parent())
        self._updateSummary()
        self.treeView.viewport().update()

    def _setChildrenCheckState(self, item: QStandardItem, state: Qt.CheckState) -> None:
        for i in range(item.rowCount()):
            child = item.child(i)
            child.setCheckState(state)
            self._setChildrenCheckState(child, state)

    def _updateBranchCheckState(self, item: QStandardItem) -> Qt.CheckState:
        if item.rowCount() == 0:
            return item.checkState()
        states = [self._updateBranchCheckState(item.child(i)) for i in range(item.rowCount())]
        if all(s == Qt.CheckState.Checked for s in states):
            item.setCheckState(Qt.CheckState.Checked)
        elif all(s == Qt.CheckState.Unchecked for s in states):
            item.setCheckState(Qt.CheckState.Unchecked)
        else:
            item.setCheckState(Qt.CheckState.PartiallyChecked)
        return item.checkState()

    def _updateAncestorCheckStates(self, item: QStandardItem | None) -> None:
        while item is not None:
            states = [item.child(i).checkState() for i in range(item.rowCount())]
            if all(s == Qt.CheckState.Checked for s in states):
                item.setCheckState(Qt.CheckState.Checked)
            elif all(s == Qt.CheckState.Unchecked for s in states):
                item.setCheckState(Qt.CheckState.Unchecked)
            else:
                item.setCheckState(Qt.CheckState.PartiallyChecked)
            item = item.parent()

    def _setSelectedIndexes(self, selectedIndexes: set[int]) -> None:
        with QSignalBlocker(self.treeModel):
            for file in self._task.files or []:
                self._fileItems[file.index].setCheckState(
                    Qt.CheckState.Checked if file.index in selectedIndexes else Qt.CheckState.Unchecked
                )
            root = self.treeModel.invisibleRootItem()
            for i in range(root.rowCount()):
                self._updateBranchCheckState(root.child(i))
        self._updateSummary()

    def _setAll(self, checked: bool) -> None:
        if checked:
            self._setSelectedIndexes({f.index for f in self._task.files or []})
        else:
            self._setSelectedIndexes(set())
        self.treeView.viewport().update()

    def _invertSelection(self) -> None:
        current = self.selectedIndexes()
        self._setSelectedIndexes({f.index for f in self._task.files or [] if f.index not in current})
        self.treeView.viewport().update()

    def _selectCategory(self, categoryId: str) -> None:
        self._setSelectedIndexes({
            f.index for f in self._task.files or []
            if categoryService.matchByName(f.relativePath) == categoryId
        })
        self.treeView.viewport().update()

    def _updateSummary(self) -> None:
        selected = self.selectedIndexes()
        total = len(self._fileItems)
        size = sum(f.size for f in (self._task.files or []) if f.index in selected)
        self.summaryLabel.setText(
            self.tr("已选择 {0}/{1} 个文件，共 {2}").format(len(selected), total, toReadableSize(size))
        )

    def selectedIndexes(self) -> set[int]:
        return {idx for idx, item in self._fileItems.items() if item.checkState() == Qt.CheckState.Checked}

    def validate(self) -> bool:
        if self.selectedIndexes():
            return True
        InfoBar.warning(
            self.tr("至少选择一个文件"),
            self.tr("当前没有任何文件被勾选"),
            parent=self,
        )
        return False
