from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QLabel, QScrollArea, QVBoxLayout, QWidget

from pyqt_github_markdown.markdown_service import markdownService
from pyqt_github_markdown.renderer import markdownRenderer
from pyqt_github_markdown.theme import LIGHT, Theme


class MarkdownWidget(QWidget):
    linkClicked = Signal(str)

    def __init__(self, theme: Theme = LIGHT, parent: QWidget | None = None):
        super().__init__(parent)
        self._theme = theme
        self._tree = None  # cached SyntaxTreeNode so setTheme can rebuild (code colours are baked in)
        # instant widget
        self._scroll = QScrollArea(self)
        self._content = QWidget()
        # instant layout
        self._rootLayout = QVBoxLayout(self)
        self._contentLayout = QVBoxLayout(self._content)
        self._initWidget()
        self._initLayout()

    def _initWidget(self) -> None:
        self.setObjectName("markdown")
        self.setStyleSheet(self._theme.qss)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setWidget(self._content)

    def _initLayout(self) -> None:
        self._rootLayout.setContentsMargins(0, 0, 0, 0)
        self._rootLayout.addWidget(self._scroll)
        self._contentLayout.setContentsMargins(16, 16, 16, 16)
        self._contentLayout.setSpacing(12)
        self._contentLayout.addStretch(1)

    def setMarkdown(self, text: str) -> None:
        self._tree = markdownService.toTree(text)
        self._rebuild()

    def setTheme(self, theme: Theme) -> None:
        self._theme = theme
        self.setStyleSheet(theme.qss)
        self._rebuild()  # re-highlight code with the new Pygments style

    def onLinkActivated(self, url: str) -> None:
        self.linkClicked.emit(url)

    def _rebuild(self) -> None:
        while self._contentLayout.count():
            item = self._contentLayout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        if self._tree is None:
            return
        for widget in markdownRenderer.buildDocument(self._tree, self._theme):
            self._contentLayout.addWidget(widget)
        self._contentLayout.addStretch(1)
        for label in self._content.findChildren(QLabel):
            label.linkActivated.connect(self.onLinkActivated)
