from collections.abc import Callable

from PySide6.QtWidgets import QHBoxLayout, QWidget
from qfluentwidgets import BodyLabel, FluentIcon, IconWidget, PrimaryPushButton

from app.view.components.banners import WarningBanner


class PermissionBanner(WarningBanner):
    def __init__(self, onGrant: Callable[[], None], text: str = "",
                 parent: QWidget | None = None):
        super().__init__(parent, radius=0)
        self._onGrant = onGrant
        self.iconWidget = IconWidget(FluentIcon.INFO, self)
        self.label = BodyLabel(text or self.tr("未授予存储权限，下载到公共目录将失败"), self)
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
