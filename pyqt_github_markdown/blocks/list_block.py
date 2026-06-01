from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget


class ListItem(QWidget):
    def __init__(self, marker: QWidget, children: list[QWidget], parent: QWidget | None = None):
        super().__init__(parent)
        self._marker = marker
        self._children = children
        # instant layout
        self._rootLayout = QHBoxLayout(self)
        self._contentLayout = QVBoxLayout()
        self._initWidget()
        self._initLayout()

    def _initWidget(self) -> None:
        self._marker.setFixedWidth(26)

    def _initLayout(self) -> None:
        self._rootLayout.setContentsMargins(0, 0, 0, 0)
        self._rootLayout.setSpacing(4)
        self._rootLayout.addWidget(self._marker, 0, Qt.AlignTop)
        self._contentLayout.setContentsMargins(0, 0, 0, 0)
        self._contentLayout.setSpacing(4)
        for child in self._children:
            self._contentLayout.addWidget(child)
        self._rootLayout.addLayout(self._contentLayout, 1)


class ListBlock(QWidget):
    def __init__(self, items: list[ListItem], parent: QWidget | None = None):
        super().__init__(parent)
        self._items = items
        # instant layout
        self._rootLayout = QVBoxLayout(self)
        self._initLayout()

    def _initLayout(self) -> None:
        # Left margin gives nested lists their visual indentation.
        self._rootLayout.setContentsMargins(8, 0, 0, 0)
        self._rootLayout.setSpacing(2)
        for item in self._items:
            self._rootLayout.addWidget(item)
