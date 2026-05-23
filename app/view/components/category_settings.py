from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    ComboBox,
    ExpandSettingCard,
    FluentIcon,
    IconWidget,
    LineEdit,
    MessageBoxBase,
    PushButton,
    StrongBodyLabel,
    SubtitleLabel,
    ToolButton,
    ToolTipFilter,
)

from app.services.category_service import (
    DEFAULT_FOLDER_MACRO,
    Category,
    categoryService,
)

_CATEGORY_ICON_CHOICES: list[str] = [
    "DOCUMENT", "MUSIC", "VIDEO", "ZIP_FOLDER", "APPLICATION",
    "LIBRARY", "ALBUM", "PHOTO", "MOVIE", "MEDIA",
    "GAME", "CODE", "EDUCATION", "LANGUAGE", "BRUSH",
    "FOLDER", "CHAT", "MAIL", "PRINT", "GLOBE",
    "CAMERA", "IMAGE_EXPORT", "MUSIC_FOLDER", "MARKET", "HELP",
]


class CategoryEditDialog(MessageBoxBase):
    def __init__(self, parent=None, *, category: Category | None = None) -> None:
        super().__init__(parent)
        self._category = category

        self.titleLabel = SubtitleLabel(
            self.tr("编辑分类") if category else self.tr("添加分类"), self
        )
        self.nameLabel = BodyLabel(self.tr("名称"), self)
        self.nameEdit = LineEdit(self)
        self.iconLabel = BodyLabel(self.tr("图标"), self)
        self.iconCombo = ComboBox(self)
        self.extensionsLabel = BodyLabel(self.tr("扩展名"), self)
        self.extensionsEdit = LineEdit(self)
        self.folderLabel = BodyLabel(self.tr("下载文件夹"), self)
        self.folderRow = QWidget(self)
        self.folderRowLayout = QHBoxLayout(self.folderRow)
        self.folderEdit = LineEdit(self.folderRow)
        self.useDefaultButton = ToolButton(FluentIcon.HOME, self.folderRow)
        self.folderBrowseButton = ToolButton(FluentIcon.FOLDER, self.folderRow)

        self._initWidget()
        self._initLayout()
        self._bind()
        self._populate()

    def _initWidget(self) -> None:
        self.widget.setMinimumWidth(480)
        self.yesButton.setText(self.tr("确定"))
        self.cancelButton.setText(self.tr("取消"))

        self.nameEdit.setPlaceholderText(self.tr("分类名称"))
        self.extensionsEdit.setPlaceholderText(
            self.tr("以逗号或空格分隔，例如 mp4 mkv avi")
        )
        self.folderEdit.setPlaceholderText(
            self.tr("可选，留空则使用默认下载路径；可用 {default} 代表默认下载文件夹")
        )
        self.useDefaultButton.setToolTip(self.tr("使用默认下载文件夹"))
        self.useDefaultButton.installEventFilter(ToolTipFilter(self.useDefaultButton))
        self.folderBrowseButton.setToolTip(self.tr("选择文件夹"))
        self.folderBrowseButton.installEventFilter(ToolTipFilter(self.folderBrowseButton))

        for name in _CATEGORY_ICON_CHOICES:
            self.iconCombo.addItem(
                name,
                icon=getattr(FluentIcon, name),
                userData=name,
            )

    def _initLayout(self) -> None:
        self.folderRowLayout.setContentsMargins(0, 0, 0, 0)
        self.folderRowLayout.setSpacing(8)
        self.folderRowLayout.addWidget(self.folderEdit, stretch=1)
        self.folderRowLayout.addWidget(self.useDefaultButton)
        self.folderRowLayout.addWidget(self.folderBrowseButton)

        self.viewLayout.setSpacing(8)
        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addSpacing(8)
        self.viewLayout.addWidget(self.nameLabel)
        self.viewLayout.addWidget(self.nameEdit)
        self.viewLayout.addWidget(self.iconLabel)
        self.viewLayout.addWidget(self.iconCombo)
        self.viewLayout.addWidget(self.extensionsLabel)
        self.viewLayout.addWidget(self.extensionsEdit)
        self.viewLayout.addWidget(self.folderLabel)
        self.viewLayout.addWidget(self.folderRow)

    def _bind(self) -> None:
        self.useDefaultButton.clicked.connect(
            lambda: self.folderEdit.setText(DEFAULT_FOLDER_MACRO)
        )
        self.folderBrowseButton.clicked.connect(self._selectFolder)

    def _populate(self) -> None:
        if self._category is None:
            self.iconCombo.setCurrentIndex(0)
            return

        self.nameEdit.setText(self._category.name)
        self.extensionsEdit.setText(" ".join(self._category.extensions))
        self.folderEdit.setText(self._category.folder or "")
        index = self.iconCombo.findData(self._category.icon)
        self.iconCombo.setCurrentIndex(index if index >= 0 else 0)

    def _selectFolder(self) -> None:
        start = self.folderEdit.text() or str(Path.home())
        selected = QFileDialog.getExistingDirectory(
            self, self.tr("选择下载文件夹"), start
        )
        if selected:
            self.folderEdit.setText(selected)

    def category(self) -> Category:
        name = self.nameEdit.text().strip() or self.tr("未命名分类")
        extensions: list[str] = []
        for token in self.extensionsEdit.text().replace(",", " ").split():
            normalized = token.strip().lstrip(".").lower()
            if normalized and normalized not in extensions:
                extensions.append(normalized)
        folder = self.folderEdit.text().strip() or None
        icon: str = self.iconCombo.currentData() or "DOCUMENT"

        if self._category is None:
            return Category(name=name, icon=icon, extensions=extensions, folder=folder)
        return Category(
            categoryId=self._category.categoryId,
            name=name,
            icon=icon,
            extensions=extensions,
            folder=folder,
        )


class _CategoryRowWidget(QWidget):
    editRequested = Signal(str)
    removeRequested = Signal(str)

    def __init__(self, category: Category, parent=None) -> None:
        super().__init__(parent)
        self._categoryId = category.categoryId

        self.iconWidget = IconWidget(category.fluentIcon(), self)
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
        self.editButton.clicked.connect(
            lambda: self.editRequested.emit(self._categoryId)
        )
        self.removeButton.clicked.connect(
            lambda: self.removeRequested.emit(self._categoryId)
        )

    def _toSummary(self, category: Category) -> str:
        count = len(category.extensions)
        if count == 0:
            return self.tr("无扩展名")
        head = ", ".join(category.extensions[:4])
        if count > 4:
            return self.tr("{0} 等 {1} 项").format(head, count)
        return head


class CategoryRulesCard(ExpandSettingCard):
    def __init__(self, parent=None) -> None:
        super().__init__(
            FluentIcon.TAG,
            self.tr("下载分类规则"),
            self.tr("根据扩展名自动归类，可为分类指定下载文件夹"),
            parent,
        )
        self._rowWidgets: list[_CategoryRowWidget] = []
        self.buttonContainer = QWidget(self.view)
        self.buttonLayout = QHBoxLayout(self.buttonContainer)
        self.resetButton = PushButton(
            FluentIcon.SYNC, self.tr("恢复默认"), self.buttonContainer
        )
        self.addButton = PushButton(
            FluentIcon.ADD, self.tr("添加分类"), self.buttonContainer
        )

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
        categoryService.categoriesChanged.connect(self._reload)

    def _reload(self) -> None:
        for row in self._rowWidgets:
            self.viewLayout.removeWidget(row)
            row.deleteLater()
        self._rowWidgets.clear()
        self.viewLayout.removeWidget(self.buttonContainer)

        for category in categoryService.categories():
            row = _CategoryRowWidget(category, self.view)
            row.editRequested.connect(self._onEditClicked)
            row.removeRequested.connect(self._onRemoveClicked)
            self.viewLayout.addWidget(row)
            self._rowWidgets.append(row)

        self.viewLayout.addWidget(self.buttonContainer)
        self.card.setContent(
            self.tr("已配置 {0} 个分类").format(len(self._rowWidgets))
        )
        self._adjustViewSize()

    def _adjustViewSize(self) -> None:
        h = sum(row.sizeHint().height() for row in self._rowWidgets)
        h += self.buttonContainer.sizeHint().height()
        self.spaceWidget.setFixedHeight(h)
        if self.isExpand:
            self.setFixedHeight(self.card.height() + h)

    def _onAddClicked(self) -> None:
        dialog = CategoryEditDialog(self.window())
        if dialog.exec():
            categoryService.addCategory(dialog.category())

    def _onEditClicked(self, categoryId: str) -> None:
        category = categoryService.categoryById(categoryId)
        if category is None:
            return
        dialog = CategoryEditDialog(self.window(), category=category)
        if dialog.exec():
            categoryService.updateCategory(dialog.category())

    def _onRemoveClicked(self, categoryId: str) -> None:
        categoryService.removeCategory(categoryId)

    def _onResetClicked(self) -> None:
        categoryService.resetToDefaults()
