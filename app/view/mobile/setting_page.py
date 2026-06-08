"""移动端设置页 —— 子类化 SettingPage, 把桌面横排设置卡改成窄屏竖排。

桌面卡的右侧控件自带最小宽不缩, 手机宽度下会把卡撑爆、控件被裁到屏外; 在 addSettingGroup 统一把右侧控件下移到第二行整行铺开。
只动扁平 SettingCard, ExpandSettingCard 与单开关卡不动。
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import SettingCard, SwitchButton, isDarkTheme, qconfig

from app.view.components.setting_card_group import CollapsibleSettingCardGroup
from app.view.pages.setting_page import SettingPage

_QWIDGETSIZE_MAX = (1 << 24) - 1  # 解除组件 setFixedHeight 后用作高度上限


class MobileSettingPage(SettingPage):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._makeScrollContentOpaque()

    def showEvent(self, event):
        self._applyOpaqueBackground()  # 每次显示按当前主题重刷: 兜住 Android 启动时序下容器底漏刷为浅色
        super().showEvent(event)

    def _makeScrollContentOpaque(self):
        """容器改不透明(autoFillBackground+palette), 否则半透明容器滚动时无法 blit、Qt 每帧全量重绘致卡顿。

        不走 stylesheet+WA_OpaquePaintEvent: 普通 QWidget 不设 WA_StyledBackground 时 stylesheet 底不绘制, 会留黑底。
        """
        self.container.setStyleSheet("")  # 去掉 qfluentwidgets 的 QWidget{transparent}: 它会盖过 autofill
        self.container.setAutoFillBackground(True)
        self._applyOpaqueBackground()
        qconfig.themeChanged.connect(self._applyOpaqueBackground)

    def _applyOpaqueBackground(self):
        palette = self.container.palette()
        palette.setColor(  # 与主窗 paintEvent 同色, 衔接无缝
            QPalette.ColorRole.Window,
            QColor(32, 32, 32) if isDarkTheme() else QColor(243, 243, 243),
        )
        self.container.setPalette(palette)

    def addSettingGroup(self, group: CollapsibleSettingCardGroup):
        for i in range(group.cardLayout.count()):
            card = group.cardLayout.itemAt(i).widget()
            if isinstance(card, SettingCard):
                self._stackCardVertically(card)
        super().addSettingGroup(group)

    def _stackCardVertically(self, card: SettingCard):
        if getattr(card, "_mobileStacked", False):
            return

        controls = self._trailingControls(card)
        if not controls:
            return  # 纯标题卡(如分组占位), 无右侧控件
        if len(controls) == 1 and isinstance(controls[0], SwitchButton):
            return  # 开关卡: 标题左 / 开关右 已是移动端理想形态

        # 一个 QWidget 只能装一个 layout: 清空旧横排并把它卸到临时 widget, 腾出 card 装竖排
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
        titleRow.addLayout(card.vBoxLayout, 1)  # 标题/描述块铺满整行, 省略号空间更足
        outer.addLayout(titleRow)

        controlRow = QHBoxLayout()
        controlRow.setContentsMargins(32, 0, 0, 0)  # 与标题文字左缘对齐(图标16 + 间距16)
        controlRow.setSpacing(8)
        for widget in controls:
            controlRow.addWidget(widget)
        controlRow.addStretch(1)
        outer.addLayout(controlRow)

        # 解除组件写死的 setFixedHeight(70/50), 让卡片高度跟随两行内容
        card.setMinimumHeight(0)
        card.setMaximumHeight(_QWIDGETSIZE_MAX)
        card._mobileStacked = True

    def _trailingControls(self, card: SettingCard) -> list[QWidget]:
        """卡片标题块(vBoxLayout)之后的右侧控件 widget。"""
        controls = []
        afterTitle = False
        for i in range(card.hBoxLayout.count()):
            item = card.hBoxLayout.itemAt(i)
            if item.layout() is card.vBoxLayout:
                afterTitle = True
            elif afterTitle and item.widget() is not None:
                controls.append(item.widget())
        return controls
