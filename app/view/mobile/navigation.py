from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout
from qfluentwidgets import CaptionLabel, FluentIcon, IconWidget, isDarkTheme, qconfig, themeColor

NAV_BAR_HEIGHT = 58
NAV_ICON_SIZE = 24

class NavigationButton(QWidget):
    clicked = Signal()

    def __init__(self, icon: FluentIcon, text: str, parent: QWidget | None = None):
        super().__init__(parent)
        self._icon = icon
        self._isSelected = False
        self.iconWidget = IconWidget(icon, self)
        self.label = CaptionLabel(text, self)
        self.vBoxLayout = QVBoxLayout(self)
        self._initWidget()
        self._initLayout()
        self._bind()

    def _initWidget(self):
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.iconWidget.setFixedSize(NAV_ICON_SIZE, NAV_ICON_SIZE)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._updateColors()

    def _initLayout(self):
        self.vBoxLayout.setContentsMargins(0, 8, 0, 6)
        self.vBoxLayout.setSpacing(3)
        self.vBoxLayout.addWidget(self.iconWidget, 0, Qt.AlignmentFlag.AlignHCenter)
        self.vBoxLayout.addWidget(self.label, 0, Qt.AlignmentFlag.AlignHCenter)

    def _bind(self):
        qconfig.themeChanged.connect(self._updateColors)

    def setSelected(self, isSelected: bool):
        if self._isSelected == isSelected:
            return
        self._isSelected = isSelected
        self._updateColors()

    def _updateColors(self):
        if self._isSelected:
            color = themeColor()
            self.iconWidget.setIcon(self._icon.colored(color, color))
            self.label.setTextColor(color, color)
        else:
            self.iconWidget.setIcon(self._icon)
            self.label.setTextColor(QColor(96, 96, 96), QColor(206, 206, 206))

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()

class BottomNavigationBar(QWidget):
    currentChanged = Signal(int)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._buttons: list[NavigationButton] = []
        self._currentIndex = -1
        self.hBoxLayout = QHBoxLayout(self)
        self._initWidget()
        self._initLayout()

    def _initWidget(self):
        self.setFixedHeight(NAV_BAR_HEIGHT)

    def _initLayout(self):
        self.hBoxLayout.setContentsMargins(0, 0, 0, 0)
        self.hBoxLayout.setSpacing(0)

    def addItem(self, icon: FluentIcon, text: str) -> int:
        index = len(self._buttons)
        button = NavigationButton(icon, text, self)
        button.clicked.connect(lambda checked=False, i=index: self.setCurrentIndex(i))
        self._buttons.append(button)
        self.hBoxLayout.addWidget(button, 1)
        if index == 0:
            self._currentIndex = 0
            button.setSelected(True)
        return index

    def setCurrentIndex(self, index: int):
        if index == self._currentIndex or not 0 <= index < len(self._buttons):
            return
        self._currentIndex = index
        for i, button in enumerate(self._buttons):
            button.setSelected(i == index)
        self.currentChanged.emit(index)

    def paintEvent(self, event):
        painter = QPainter(self)
        if isDarkTheme():
            background = QColor(39, 39, 39)
            divider = QColor(255, 255, 255, 18)
        else:
            background = QColor(243, 243, 243)
            divider = QColor(0, 0, 0, 18)
        painter.fillRect(self.rect(), background)
        painter.setPen(divider)
        painter.drawLine(0, 0, self.width(), 0)
