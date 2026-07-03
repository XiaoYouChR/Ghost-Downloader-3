from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QFileInfo, Signal, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QFileIconProvider, QHBoxLayout, QWidget
from qfluentwidgets import (
    Action, BodyLabel, FluentIcon, ImageLabel, LineEdit, RoundMenu,
    TransparentToolButton, ToolTipFilter, isDarkTheme,
)

from app.config.cfg import cfg
from app.format import toReadableSize
from app.view.components.labels import EditableLabel

if TYPE_CHECKING:
    from app.models.task import Task


class DraftCard(QWidget):
    categoryPicked = Signal(str)
    editRequested = Signal()

    def __init__(self, task: Task, parent=None):
        super().__init__(parent)
        self._task = task

        self.iconLabel = ImageLabel(self)
        self.iconLabel.setImage(QFileIconProvider().icon(QFileInfo(task.name)).pixmap(16, 16))
        self.iconLabel.setFixedSize(16, 16)
        self.nameLabel = EditableLabel(task.name, self)
        self.nameEdit = LineEdit(self)
        self.sizeLabel = BodyLabel(toReadableSize(task.fileSize) if task.fileSize > 0 else "", self)
        self.categoryButton = TransparentToolButton(self)
        self.editButton = TransparentToolButton(FluentIcon.EDIT, self)

        self._initWidget()
        self._initLayout()
        self.layout().addWidget(self.editButton)
        self.layout().addWidget(self.categoryButton)
        self._bind()

    def _initWidget(self) -> None:
        from PySide6.QtWidgets import QSizePolicy
        self.setFixedHeight(35)
        self.nameLabel.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.nameEdit.setText(self._task.name)
        self.nameEdit.hide()
        self.categoryButton.setFixedSize(28, 28)
        self.categoryButton.installEventFilter(ToolTipFilter(self.categoryButton))
        self.editButton.setFixedSize(28, 28)
        self.editButton.setToolTip(self.tr("编辑任务参数"))
        self.editButton.installEventFilter(ToolTipFilter(self.editButton))
        self.editButton.setVisible(self._task.canEdit)
        self._refreshCategoryButton()

    def _initLayout(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 2, 10, 2)
        layout.setSpacing(12)
        layout.addWidget(self.iconLabel)
        layout.addWidget(self.nameLabel, 1)
        layout.addWidget(self.nameEdit, 1)
        layout.addWidget(self.sizeLabel)

    def _bind(self) -> None:
        self.nameLabel.editRequested.connect(self._onNameEditRequested)
        self.nameEdit.editingFinished.connect(self._onNameEdited)
        self.editButton.clicked.connect(self.editRequested.emit)
        self.categoryButton.clicked.connect(self._showCategoryMenu)
        cfg.isCategoryEnabled.valueChanged.connect(self._refreshCategoryButton)

    def _refreshFileIcon(self) -> None:
        self.iconLabel.setImage(QFileIconProvider().icon(QFileInfo(self._task.name)).pixmap(16, 16))

    def _onNameEditRequested(self) -> None:
        self.nameLabel.hide()
        self.nameEdit.show()
        self.nameEdit.setFocus()
        self.nameEdit.selectAll()

    def _onNameEdited(self) -> None:
        newName = self.nameEdit.text().strip()
        if newName and newName != self._task.name:
            self._task.setName(newName)
            self.nameLabel.setText(self._task.name)
            self.nameEdit.setText(self._task.name)
            self._refreshFileIcon()
        self.nameEdit.hide()
        self.nameLabel.show()

    def _refreshCategoryButton(self) -> None:
        if not cfg.isCategoryEnabled.value:
            self.categoryButton.hide()
            return
        from app.services.category_service import categoryService
        category = categoryService.categoryById(self._task.category)
        if category:
            self.categoryButton.setIcon(category.toIcon())
            self.categoryButton.setToolTip(category.name)
        else:
            self.categoryButton.setIcon(FluentIcon.TAG)
            self.categoryButton.setToolTip(self.tr("未分类"))
        self.categoryButton.show()

    def _showCategoryMenu(self) -> None:
        from app.services.category_service import categoryService
        menu = RoundMenu(parent=self)
        uncategorized = Action(FluentIcon.TAG, self.tr("未分类"), self)
        uncategorized.triggered.connect(lambda: self._onCategoryPicked(""))
        menu.addAction(uncategorized)
        menu.addSeparator()
        for category in categoryService.categories():
            cid = category.categoryId
            icon = category.toIcon()
            action = Action(icon, category.name, self)
            action.triggered.connect(lambda _=False, c=cid: self._onCategoryPicked(c))
            menu.addAction(action)
        menu.exec(self.categoryButton.mapToGlobal(self.categoryButton.rect().bottomLeft()))

    def _onCategoryPicked(self, categoryId: str) -> None:
        self._task.category = categoryId
        self._refreshCategoryButton()
        self.categoryPicked.emit(categoryId)

    @property
    def task(self) -> Task:
        return self._task

    def paintEvent(self, e) -> None:
        painter = QPainter(self)
        painter.fillRect(0, 0, self.width(), 1, QColor(0, 0, 0, 96 if isDarkTheme() else 24))


class UniversalDraftCard(DraftCard):
    pass
