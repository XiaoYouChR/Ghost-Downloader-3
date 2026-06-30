from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel, ComboBox, FluentIcon, LineEdit, MessageBoxBase,
    SubtitleLabel, ToolButton, ToolTipFilter,
)

from app.services.category_service import Category
from app.view.components.editors import TokenLineEdit


class CategoryEditDialog(MessageBoxBase):
    ICON_CHOICES = [
        "DOCUMENT", "MUSIC", "VIDEO", "ZIP_FOLDER", "APPLICATION",
        "LIBRARY", "ALBUM", "PHOTO", "MOVIE", "MEDIA",
        "GAME", "CODE", "EDUCATION", "LANGUAGE", "BRUSH",
        "FOLDER", "CHAT", "MAIL", "PRINT", "GLOBE",
        "CAMERA", "IMAGE_EXPORT", "MUSIC_FOLDER", "MARKET", "HELP",
    ]
    def __init__(self, parent=None, *, category: Category | None = None):
        super().__init__(parent)
        self._category = category

        self.titleLabel = SubtitleLabel(
            self.tr("编辑分类") if category else self.tr("添加分类"), self
        )
        self.nameEdit = LineEdit(self)
        self.iconCombo = ComboBox(self)
        self.extensionsEdit = TokenLineEdit(self)
        self.folderRow = QWidget(self)
        self.folderRowLayout = QHBoxLayout(self.folderRow)
        self.folderEdit = LineEdit(self.folderRow)
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
        self.extensionsEdit.setPlaceholderText(self.tr("输入扩展名后按回车添加"))
        self.folderEdit.setPlaceholderText(self.tr("留空则使用默认下载路径；可用 {default} 代表默认下载文件夹"))
        self.folderBrowseButton.setToolTip(self.tr("选择文件夹"))
        self.folderBrowseButton.installEventFilter(ToolTipFilter(self.folderBrowseButton))

        for name in self.ICON_CHOICES:
            self.iconCombo.addItem(name, icon=getattr(FluentIcon, name, FluentIcon.DOCUMENT), userData=name)

    def _initLayout(self) -> None:
        self.folderRowLayout.setContentsMargins(0, 0, 0, 0)
        self.folderRowLayout.setSpacing(8)
        self.folderRowLayout.addWidget(self.folderEdit, stretch=1)
        self.folderRowLayout.addWidget(self.folderBrowseButton)

        self.viewLayout.setSpacing(8)
        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addSpacing(8)
        self.viewLayout.addWidget(BodyLabel(self.tr("名称"), self))
        self.viewLayout.addWidget(self.nameEdit)
        self.viewLayout.addWidget(BodyLabel(self.tr("图标"), self))
        self.viewLayout.addWidget(self.iconCombo)
        self.viewLayout.addWidget(BodyLabel(self.tr("扩展名"), self))
        self.viewLayout.addWidget(self.extensionsEdit)
        self.viewLayout.addWidget(BodyLabel(self.tr("下载文件夹"), self))
        self.viewLayout.addWidget(self.folderRow)

    def _bind(self) -> None:
        self.folderBrowseButton.clicked.connect(self._onBrowseClicked)

    def _populate(self) -> None:
        if self._category is None:
            return
        self.nameEdit.setText(self._category.name)
        self.extensionsEdit.setTokens(self._category.extensions)
        self.folderEdit.setText(self._category.folder or "")
        index = self.iconCombo.findData(self._category.icon)
        self.iconCombo.setCurrentIndex(index if index >= 0 else 0)

    def _onBrowseClicked(self) -> None:
        start = self.folderEdit.text() or str(Path.home())
        selected = QFileDialog.getExistingDirectory(self, self.tr("选择下载文件夹"), start)
        if selected:
            self.folderEdit.setText(selected)

    def category(self) -> Category:
        name = self.nameEdit.text().strip() or self.tr("未命名分类")
        extensions = [
            ext for token in self.extensionsEdit.tokens()
            if (ext := token.strip().lstrip(".").lower())
        ]
        folder = self.folderEdit.text().strip() or None
        icon = self.iconCombo.currentData() or "DOCUMENT"

        if self._category is None:
            return Category(name=name, icon=icon, extensions=extensions, folder=folder)
        return Category(
            categoryId=self._category.categoryId,
            name=name, icon=icon, extensions=extensions, folder=folder,
        )
