from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel, FluentIcon, IconWidget,
    PushButton, StrongBodyLabel, ToolButton, ToolTipFilter,
)

from app.view.components.setting_card_group import CollapsibleSettingCard

from app.services.category_service import Category

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.category_service import CategoryService


class CategoryRowWidget(QWidget):
    editRequested = Signal(str)
    removeRequested = Signal(str)

    def __init__(self, category: Category, parent=None):
        super().__init__(parent)
        self._categoryId = category.categoryId

        self.iconWidget = IconWidget(category.toIcon(), self)
        self.nameLabel = StrongBodyLabel(category.name, self)
        self.summaryLabel = BodyLabel(self._toSummary(category), self)
        self.editButton = ToolButton(FluentIcon.EDIT, self)
        self.removeButton = ToolButton(FluentIcon.DELETE, self)

        self._initWidget()
        self._initLayout()
        self._bind()

    def _initWidget(self) -> None:
        self.iconWidget.setFixedSize(16, 16)
        self.editButton.setToolTip(self.tr("编辑"))
        self.editButton.installEventFilter(ToolTipFilter(self.editButton))
        self.removeButton.setToolTip(self.tr("删除"))
        self.removeButton.installEventFilter(ToolTipFilter(self.removeButton))

    def _initLayout(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(48, 8, 24, 8)
        layout.setSpacing(12)
        layout.addWidget(self.iconWidget)
        layout.addWidget(self.nameLabel)
        layout.addStretch(1)
        layout.addWidget(self.summaryLabel)
        layout.addWidget(self.editButton)
        layout.addWidget(self.removeButton)

    def _bind(self) -> None:
        self.editButton.clicked.connect(lambda: self.editRequested.emit(self._categoryId))
        self.removeButton.clicked.connect(lambda: self.removeRequested.emit(self._categoryId))

    def _toSummary(self, category: Category) -> str:
        count = len(category.extensions)
        if count == 0:
            return self.tr("无扩展名")
        head = ", ".join(category.extensions[:4])
        if count > 4:
            return self.tr("{0} 等 {1} 项").format(head, count)
        return head


class CategoryRulesCard(CollapsibleSettingCard):

    def __init__(self, categoryService: CategoryService, parent: QWidget | None = None):
        super().__init__(
            FluentIcon.TAG,
            self.tr("下载分类规则"),
            self.tr("根据扩展名自动归类，可为分类指定下载文件夹"),
            parent,
        )
        self._categoryService = categoryService
        self._rowWidgets: list[CategoryRowWidget] = []
        self.buttonContainer = QWidget(self.view)
        self.buttonLayout = QHBoxLayout(self.buttonContainer)
        self.resetButton = PushButton(FluentIcon.SYNC, self.tr("恢复默认"), self.buttonContainer)
        self.addButton = PushButton(FluentIcon.ADD, self.tr("添加分类"), self.buttonContainer)

        self._initLayout()
        self._reload()
        self._bind()

    def _initLayout(self) -> None:
        self.viewLayout.setContentsMargins(0, 0, 0, 0)
        self.viewLayout.setSpacing(0)
        self.buttonLayout.setContentsMargins(48, 8, 24, 8)
        self.buttonLayout.addStretch(1)
        self.buttonLayout.addWidget(self.resetButton)
        self.buttonLayout.addWidget(self.addButton)

    def _bind(self) -> None:
        self.addButton.clicked.connect(self._onAddClicked)
        self.resetButton.clicked.connect(self._onResetClicked)
        self._categoryService.categoriesChanged.connect(self._reload)

    def _reload(self) -> None:
        for row in self._rowWidgets:
            self.viewLayout.removeWidget(row)
            row.deleteLater()
        self._rowWidgets.clear()
        self.viewLayout.removeWidget(self.buttonContainer)

        for category in self._categoryService.categories():
            row = CategoryRowWidget(category, self.view)
            row.editRequested.connect(self._onEditClicked)
            row.removeRequested.connect(self._onRemoveClicked)
            self.viewLayout.addWidget(row)
            self._rowWidgets.append(row)

        self.viewLayout.addWidget(self.buttonContainer)
        self.card.setContent(self.tr("已配置 {0} 个分类").format(len(self._rowWidgets)))

    def _onAddClicked(self) -> None:
        from app.view.dialogs.category_edit import CategoryEditDialog
        dialog = CategoryEditDialog(self.window())
        if dialog.exec():
            self._categoryService.addCategory(dialog.category())

    def _onEditClicked(self, categoryId: str) -> None:
        category = self._categoryService.categoryById(categoryId)
        if category is None:
            return
        from app.view.dialogs.category_edit import CategoryEditDialog
        dialog = CategoryEditDialog(self.window(), category=category)
        if dialog.exec():
            self._categoryService.updateCategory(dialog.category())

    def _onRemoveClicked(self, categoryId: str) -> None:
        self._categoryService.removeCategory(categoryId)

    def _onResetClicked(self) -> None:
        self._categoryService.reset()
