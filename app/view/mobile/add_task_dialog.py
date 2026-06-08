"""移动端添加任务对话框 —— 把 ParseSettingCard 的右侧控件从单行下移到标题行下方整行铺开, 否则路径框、滑块(min 268px)在手机宽度下溢出右缘被裁。"""

from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import ComboBox, LineEdit, Slider

from app.view.components.add_task_dialog import AddTaskDialog
from app.view.components.cards import ParseSettingCard

_QWIDGETSIZE_MAX = (1 << 24) - 1
_STRETCHY = (LineEdit, Slider, ComboBox)  # 输入类控件: 在第二行铺满整行


class MobileAddTaskDialog(AddTaskDialog):

    def _initWidget(self):
        super()._initWidget()
        for card in self.settingGroup.cards:
            if isinstance(card, ParseSettingCard):
                _stackParseCardVertically(card)


def _stackParseCardVertically(card: ParseSettingCard):
    controls = _trailingControls(card)
    if not controls:
        return

    oldLayout = card.hBoxLayout
    while oldLayout.count():
        oldLayout.takeAt(0)
    QWidget().setLayout(oldLayout)  # 腾出 card 以装竖排(一个 widget 同时只能有一个 layout)

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
    controlRow.setContentsMargins(28, 0, 0, 0)  # 与标题文字左缘对齐(图标16 + 间距12)
    controlRow.setSpacing(8)
    hasStretchy = False
    for widget in controls:
        if isinstance(widget, _STRETCHY):
            # 解除自带最小宽(如 Slider 写死 268px)再给伸展因子, 否则撑出横向滚动条
            widget.setMinimumWidth(0)
            controlRow.addWidget(widget, 1)
            hasStretchy = True
        else:
            controlRow.addWidget(widget, 0)
    if not hasStretchy:
        controlRow.addStretch(1)
    outer.addLayout(controlRow)

    card.setMinimumHeight(0)
    card.setMaximumHeight(_QWIDGETSIZE_MAX)  # 解除组件写死的 setFixedHeight(50)


def _trailingControls(card: ParseSettingCard) -> list[QWidget]:
    """卡片标题之后的右侧控件 widget。"""
    controls = []
    afterTitle = False
    for i in range(card.hBoxLayout.count()):
        item = card.hBoxLayout.itemAt(i)
        if item.widget() is card.titleLabel:
            afterTitle = True
        elif afterTitle and item.widget() is not None:
            controls.append(item.widget())
    return controls
