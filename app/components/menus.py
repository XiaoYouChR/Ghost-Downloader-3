from qfluentwidgets import Action
from qfluentwidgets.common.screen import getCurrentScreenGeometry
from qfluentwidgets.components.material import AcrylicMenu


class FixedAcrylicMenu(AcrylicMenu):
    """ 修复背景获取偏移、位置偏移的问题 """

    def addActionEx(self, icon, text, slot):
        action = Action(icon, text, self)
        action.triggered.connect(slot)
        self.addAction(action)

    def adjustPosition(self):
        m = self.layout().contentsMargins()
        rect = getCurrentScreenGeometry()
        w, h = self.layout().sizeHint().width() + 5, self.layout().sizeHint().height()

        x = min(self.x() - m.left(), rect.right() - w)
        y = self.y() - 45

        self.move(x, y)

    def showEvent(self, e):
        super().showEvent(e)
        self.adjustPosition()
        # self.view.acrylicBrush.grabImage(QRect(self.pos() + self.view.pos(), self.view.size()))
