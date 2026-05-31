from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget


class BlockQuote(QWidget):
    def __init__(
        self,
        children: list[QWidget],
        kind: str = "quote",
        icon: QPixmap | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._children = children
        self._kind = kind
        self._icon = icon
        # instant widget — alerts (> [!NOTE]) carry an icon + coloured title row; quotes don't.
        self._isAlert = kind != "quote"
        self._iconLabel = QLabel() if self._isAlert else None
        self._titleLabel = QLabel(kind.capitalize()) if self._isAlert else None
        # instant layout
        self._titleLayout = QHBoxLayout() if self._isAlert else None
        self._rootLayout = QVBoxLayout(self)
        self._initWidget()
        self._initLayout()

    def _initWidget(self) -> None:
        self.setObjectName("alert" if self._isAlert else "blockquote")
        self.setProperty("kind", self._kind)
        self.setAttribute(Qt.WA_StyledBackground, True)
        if self._titleLabel is not None:
            self._titleLabel.setObjectName("alert-title")
        if self._iconLabel is not None and self._icon is not None:
            self._iconLabel.setPixmap(self._icon)

    def _initLayout(self) -> None:
        self._rootLayout.setContentsMargins(16, 4, 8, 4)
        self._rootLayout.setSpacing(6)
        if self._titleLayout is not None:
            self._titleLayout.setContentsMargins(0, 0, 0, 0)
            self._titleLayout.setSpacing(8)
            self._titleLayout.addWidget(self._iconLabel)
            self._titleLayout.addWidget(self._titleLabel)
            self._titleLayout.addStretch(1)
            self._rootLayout.addLayout(self._titleLayout)
        for child in self._children:
            self._rootLayout.addWidget(child)
