"""yt-dlp 的设置卡片（View）。config.py 只留配置数据。"""
from __future__ import annotations

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtWidgets import QHBoxLayout
from qfluentwidgets import (
    CaptionLabel, FluentIcon, PushButton, SettingCard, ToolButton, ToolTipFilter,
)

from .config import clearCookies, hasCookieFile, saveCookies


class CookieSettingCard(SettingCard):

    def __init__(self, parent=None):
        super().__init__(
            FluentIcon.CERTIFICATE,
            QCoreApplication.translate("YtDlpConfig", "YouTube Cookie"),
            self._statusText(),
            parent,
        )
        self._importButton = PushButton(
            QCoreApplication.translate("YtDlpConfig", "导入"),
            self,
        )
        self._clearButton = ToolButton(FluentIcon.DELETE, self)
        self._clearButton.setToolTip(
            QCoreApplication.translate("YtDlpConfig", "清除 Cookie")
        )
        self._clearButton.installEventFilter(ToolTipFilter(self._clearButton))
        self._clearButton.setVisible(hasCookieFile())

        buttonLayout = QHBoxLayout()
        buttonLayout.setContentsMargins(0, 0, 0, 0)
        buttonLayout.setSpacing(8)
        buttonLayout.addWidget(self._importButton)
        buttonLayout.addWidget(self._clearButton)
        self.hBoxLayout.addLayout(buttonLayout)
        self.hBoxLayout.addSpacing(16)

        self._importButton.clicked.connect(self._onImportClicked)
        self._clearButton.clicked.connect(self._onClearClicked)

    def _statusText(self) -> str:
        if hasCookieFile():
            return QCoreApplication.translate("YtDlpConfig", "已导入")
        return QCoreApplication.translate(
            "YtDlpConfig", "下载需要登录的内容时需要 Cookie，推荐通过浏览器扩展自动导入"
        )

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._refresh()

    def _refresh(self) -> None:
        self.setContent(self._statusText())
        self._clearButton.setVisible(hasCookieFile())

    def _onImportClicked(self) -> None:
        from qfluentwidgets import MessageBoxBase, SubtitleLabel, PlainTextEdit

        dialog = MessageBoxBase(self.window())
        dialog.widget.setMinimumWidth(500)
        dialog.viewLayout.addWidget(SubtitleLabel(
            QCoreApplication.translate("YtDlpConfig", "导入 YouTube Cookie"),
            dialog,
        ))

        label = CaptionLabel(
            QCoreApplication.translate(
                "YtDlpConfig",
                "安装浏览器扩展后，下载 YouTube 视频时会自动携带登录信息，无需手动操作。\n"
                "如需手动导入：打开 YouTube 并登录，按 F12 打开开发者工具，在 Network 标签中"
                "找到任意请求，复制其 Cookie 请求头的值并粘贴到下方。",
            ),
            dialog,
        )
        label.setWordWrap(True)
        dialog.viewLayout.addWidget(label)

        editor = PlainTextEdit(dialog)
        editor.setPlaceholderText("SID=xxx; HSID=xxx; ...")
        editor.setMinimumHeight(120)
        dialog.viewLayout.addWidget(editor)

        if dialog.exec():
            text = editor.toPlainText().strip()
            if text:
                saveCookies(text)
                self._refresh()

    def _onClearClicked(self) -> None:
        clearCookies()
        self._refresh()
