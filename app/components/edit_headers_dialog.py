from PySide6.QtCore import Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QVBoxLayout
from qfluentwidgets import FluentStyleSheet, InfoBar, InfoBarPosition, PrimaryPushButton, \
    SubtitleLabel

from app.components.disabled_rich_text_edit import DisabledRichTextEdit
from app.components.fixed_mask_dialog_base import MaskDialogBase


class EditHeadersDialog(MaskDialogBase):
    headersUpdated = Signal(dict)

    def __init__(self, parent=None, initialHeaders=None):
        super().__init__(parent=parent)
        FluentStyleSheet.DIALOG.apply(self.widget)
        self.widget.setContentsMargins(11, 11, 11, 11)

        self.setShadowEffect(60, (0, 10), QColor(0, 0, 0, 50))
        self.setMaskColor(QColor(0, 0, 0, 76))
        self.setClosableOnMaskClicked(True)

        self.widget.setFixedSize(400, 500)

        self.layout = QVBoxLayout(self)

        self.titleLabel = SubtitleLabel("编辑请求标头", self.widget)
        self.layout.addWidget(self.titleLabel)

        self.headersTextEdit = DisabledRichTextEdit(self.widget)
        self.headersTextEdit.setPlaceholderText('请输入请求标头，每行一个键值对，格式为 "key: value"')
        if initialHeaders:
            self.headersTextEdit.setPlainText("\n".join([f"{k}: {v}" for k, v in initialHeaders.items()]))
        self.layout.addWidget(self.headersTextEdit)

        self.saveButton = PrimaryPushButton("保存", self.widget)
        self.saveButton.clicked.connect(self.__onSaveButtonClicked)
        self.layout.addWidget(self.saveButton)

        self.widget.setLayout(self.layout)

    def __onSaveButtonClicked(self):
        headers_text = self.headersTextEdit.toPlainText()
        headersDict = self.__parseHeaders(headers_text)
        if headersDict is not None:
            self.headersUpdated.emit(headersDict)
            self.accept()
        else:
            InfoBar.error(
                title="错误",
                content='请输入格式正确的请求标头, 格式为 "key: value"',
                position=InfoBarPosition.TOP,
                parent=self.parent(),
                duration=3000,
            )

    def __parseHeaders(self, headers_text):
        headersDict = {}
        lines = headers_text.strip().split('\n')
        for line in lines:
            if line.strip():
                parts = line.split(':', 1)
                if len(parts) != 2:
                    return None
                key, value = parts
                headersDict[key.strip()] = value.strip()
        return headersDict