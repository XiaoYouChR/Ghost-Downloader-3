from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import ComboBox, LineEdit, Slider

from app.view.components.add_task_dialog import AddTaskDialog
from app.view.components.cards import ParseSettingCard

_QWIDGETSIZE_MAX = (1 << 24) - 1
_EXPANDING_CONTROLS = (LineEdit, Slider, ComboBox)

class MobileAddTaskDialog(AddTaskDialog):
    def _initWidget(self):
        super()._initWidget()
        for card in self.settingGroup.cards:
            if isinstance(card, ParseSettingCard):
                _setParseCardVerticalLayout(card)

def _setParseCardVerticalLayout(card: ParseSettingCard):
    controls = _controlsAfterTitle(card)
    if not controls:
        return

    oldLayout = card.hBoxLayout
    while oldLayout.count():
        oldLayout.takeAt(0)
    QWidget().setLayout(oldLayout)

    outer = QVBoxLayout(card)
    outer.setContentsMargins(24, 8, 24, 8)
    outer.setSpacing(8)

    titleRow = QHBoxLayout()
    titleRow.setSpacing(12)
    titleRow.addWidget(card.iconWidget)
    titleRow.addWidget(card.titleLabel)
    titleRow.addStretch(1)
    outer.addLayout(titleRow)

    controlRow = QHBoxLayout()
    controlRow.setContentsMargins(28, 0, 0, 0)
    controlRow.setSpacing(8)
    hasExpandingControl = False
    for widget in controls:
        if isinstance(widget, _EXPANDING_CONTROLS):
            widget.setMinimumWidth(0)
            controlRow.addWidget(widget, 1)
            hasExpandingControl = True
        else:
            controlRow.addWidget(widget, 0)
    if not hasExpandingControl:
        controlRow.addStretch(1)
    outer.addLayout(controlRow)

    card.setMinimumHeight(0)
    card.setMaximumHeight(_QWIDGETSIZE_MAX)

def _controlsAfterTitle(card: ParseSettingCard) -> list[QWidget]:
    controls = []
    afterTitle = False
    for i in range(card.hBoxLayout.count()):
        item = card.hBoxLayout.itemAt(i)
        if item.widget() is card.titleLabel:
            afterTitle = True
        elif afterTitle and item.widget() is not None:
            controls.append(item.widget())
    return controls
