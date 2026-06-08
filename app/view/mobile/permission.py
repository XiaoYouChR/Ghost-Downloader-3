"""存储权限软门横幅 —— Android 11+ 的 MANAGE_EXTERNAL_STORAGE 无运行时弹窗, 只能 Intent 跳设置页, 故未授权时常驻任务页顶部引导授权。"""

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QHBoxLayout, QWidget
from qfluentwidgets import BodyLabel, FluentIcon, IconWidget, PrimaryPushButton, isDarkTheme


class PermissionBanner(QWidget):

    def __init__(self, onGrant: Callable[[], None], parent: QWidget | None = None):
        super().__init__(parent)
        self._onGrant = onGrant
        self.iconWidget = IconWidget(FluentIcon.INFO, self)
        self.label = BodyLabel(self.tr("未授予「所有文件访问」，下载到公共目录将失败"), self)
        self.grantButton = PrimaryPushButton(self.tr("去授权"), self)
        self.hBoxLayout = QHBoxLayout(self)
        self._initWidget()
        self._initLayout()
        self._bind()

    def _initWidget(self):
        self.setFixedHeight(48)
        self.iconWidget.setFixedSize(18, 18)
        self.label.setWordWrap(False)

    def _initLayout(self):
        self.hBoxLayout.setContentsMargins(16, 0, 12, 0)
        self.hBoxLayout.setSpacing(10)
        self.hBoxLayout.addWidget(self.iconWidget)
        self.hBoxLayout.addWidget(self.label, 1)
        self.hBoxLayout.addWidget(self.grantButton)

    def _bind(self):
        self.grantButton.clicked.connect(lambda: self._onGrant())

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(66, 54, 20) if isDarkTheme() else QColor(255, 244, 206))
