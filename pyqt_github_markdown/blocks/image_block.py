from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

_MAX_WIDTH = 760


def _loadLocalPixmap(src: str) -> QPixmap | None:
    # v1 renders only local images synchronously; remote URLs become a placeholder box.
    url = QUrl(src)
    if url.scheme() in ("http", "https"):
        return None
    path = url.toLocalFile() if url.isLocalFile() else src
    pixmap = QPixmap(path)
    return pixmap if not pixmap.isNull() else None


class ImagePlaceholder(QWidget):
    def __init__(self, alt: str, src: str, parent: QWidget | None = None):
        super().__init__(parent)
        self._alt = alt
        self._src = src
        # instant widget
        self._label = QLabel()
        # instant layout
        self._rootLayout = QVBoxLayout(self)
        self._initWidget()
        self._initLayout()

    def _initWidget(self) -> None:
        pixmap = _loadLocalPixmap(self._src)
        if pixmap is not None:
            if pixmap.width() > _MAX_WIDTH:
                pixmap = pixmap.scaledToWidth(_MAX_WIDTH, Qt.SmoothTransformation)
            self._label.setPixmap(pixmap)
        else:
            self.setObjectName("image-placeholder")
            self._label.setText(f"\U0001f5bc  {self._alt or self._src}")
            self._label.setObjectName("paragraph")

    def _initLayout(self) -> None:
        self._rootLayout.setContentsMargins(0, 0, 0, 0)
        self._rootLayout.addWidget(self._label, 0, Qt.AlignLeft)
