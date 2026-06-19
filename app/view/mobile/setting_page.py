from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import SettingCard, SwitchButton, isDarkTheme, qconfig

from app.view.components.setting_card_group import CollapsibleSettingCardGroup
from app.view.pages.setting_page import SettingPage

_QWIDGETSIZE_MAX = (1 << 24) - 1

class MobileSettingPage(SettingPage):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setScrollContentOpaque()

    def showEvent(self, event):
        self._updateScrollBackground()
        super().showEvent(event)

    def _setScrollContentOpaque(self):
        self.container.setStyleSheet("")
        self.container.setAutoFillBackground(True)
        self._updateScrollBackground()
        qconfig.themeChanged.connect(self._updateScrollBackground)

    def _updateScrollBackground(self):
        palette = self.container.palette()
        palette.setColor(
            QPalette.ColorRole.Window,
            QColor(32, 32, 32) if isDarkTheme() else QColor(243, 243, 243),
        )
        self.container.setPalette(palette)

    def addSettingGroup(self, group: CollapsibleSettingCardGroup):
        for i in range(group.cardLayout.count()):
            card = group.cardLayout.itemAt(i).widget()
            if isinstance(card, SettingCard):
                self._setCardVerticalLayout(card)
        super().addSettingGroup(group)

    def _setCardVerticalLayout(self, card: SettingCard):
        if getattr(card, "_usesMobileLayout", False):
            return

        controls = self._controlsAfterTitle(card)
        if not controls:
            return
        if len(controls) == 1 and isinstance(controls[0], SwitchButton):
            return

        oldLayout = card.hBoxLayout
        while oldLayout.count():
            oldLayout.takeAt(0)
        QWidget().setLayout(oldLayout)

        outer = QVBoxLayout(card)
        outer.setContentsMargins(16, 10, 16, 10)
        outer.setSpacing(8)

        titleRow = QHBoxLayout()
        titleRow.setSpacing(0)
        titleRow.addWidget(card.iconLabel, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        titleRow.addSpacing(16)
        titleRow.addLayout(card.vBoxLayout, 1)
        outer.addLayout(titleRow)

        controlRow = QHBoxLayout()
        controlRow.setContentsMargins(32, 0, 0, 0)
        controlRow.setSpacing(8)
        for widget in controls:
            controlRow.addWidget(widget)
        controlRow.addStretch(1)
        outer.addLayout(controlRow)

        card.setMinimumHeight(0)
        card.setMaximumHeight(_QWIDGETSIZE_MAX)
        card._usesMobileLayout = True

    def _controlsAfterTitle(self, card: SettingCard) -> list[QWidget]:
        controls = []
        afterTitle = False
        for i in range(card.hBoxLayout.count()):
            item = card.hBoxLayout.itemAt(i)
            if item.layout() is card.vBoxLayout:
                afterTitle = True
            elif afterTitle and item.widget() is not None:
                controls.append(item.widget())
        return controls
