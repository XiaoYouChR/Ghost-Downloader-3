from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout
from qfluentwidgets import LineEdit, MessageBoxBase

from app.config.cfg import BASE_HEADERS
from app.view.components.headers_editor import HeadersEditor
from app.view.components.scroll_area import ScrollArea


class HeadersPresetEditDialog(MessageBoxBase):

    def __init__(self, parent=None, *, preset: dict):
        super().__init__(parent)
        self.nameEdit = LineEdit(self)
        self.editor = HeadersEditor(self, defaults=BASE_HEADERS)
        self.scrollArea = ScrollArea(self.widget)
        self.titleRow = QHBoxLayout()

        self._initWidget(preset)
        self._initLayout()

    def _initWidget(self, preset: dict) -> None:
        self.widget.setMinimumWidth(500)
        self.yesButton.setText(self.tr("确定"))
        self.cancelButton.setText(self.tr("取消"))
        self.nameEdit.setPlaceholderText(self.tr("预设名称"))
        self.nameEdit.setText(preset["name"])
        self.editor.setHeaders(preset["headers"])

    def _initLayout(self) -> None:
        self.titleRow.addWidget(self.nameEdit, 1)
        self.titleRow.addSpacing(8)
        self.titleRow.addWidget(self.editor.toolbar)
        self.viewLayout.addLayout(self.titleRow)

        self.scrollArea.setWidget(self.editor)
        self.scrollArea.setWidgetResizable(True)
        self.scrollArea.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scrollArea.enableTransparentBackground()
        self.viewLayout.addWidget(self.scrollArea)

    def preset(self) -> dict:
        return {
            "name": self.nameEdit.text().strip() or self.tr("未命名预设"),
            "headers": self.editor.headers(),
        }
