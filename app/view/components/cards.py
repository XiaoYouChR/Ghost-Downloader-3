from pathlib import Path

from PySide6.QtCore import Qt, QEvent, QFileInfo, Signal
from PySide6.QtGui import QMouseEvent, QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget, QHBoxLayout, QFileIconProvider
from qfluentwidgets import ImageLabel, StrongBodyLabel, LineEdit, BodyLabel, isDarkTheme, CardWidget, CheckBox, \
    themeColor, IconWidget

from app.bases.models import Task
from app.services.core_service import coreService
from app.supports.utils import getReadableSize
from app.view.components.dialogs import DeleteTaskDialog


class ResultCard(QWidget):
    """显示下载链接解析结果的卡片组件"""

    def __init__(self, task: Task, parent: QWidget = None):
        super().__init__(parent)
        # self.task = task
        self.borderRadius = 5

    def getTask(self) -> Task:
        raise NotImplementedError

    @property
    def backgroundColor(self):
        return QColor(255, 255, 255, 13 if isDarkTheme() else 200)

    def paintEvent(self, e):
        painter = QPainter(self)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing)

        if isDarkTheme():
            painter.setPen(QColor(0, 0, 0, 96))
        else:
            painter.setPen(QColor(0, 0, 0, 24))

        painter.drawLine(self.rect().topLeft(), self.rect().topRight())


class GroupSettingCard(QWidget):

    def __init__(self, icon, title: str, parent=None):
        super().__init__(parent=parent)
        self.hBoxLayout = QHBoxLayout(self)

        self.iconWidget = IconWidget(icon, self)
        self.titleLabel = BodyLabel(title, self)

        self.initWidget()

    def initWidget(self):
        self.iconWidget.setFixedSize(16, 16)

        self.hBoxLayout.addWidget(self.iconWidget)
        self.hBoxLayout.addWidget(self.titleLabel)
        self.hBoxLayout.addStretch(1)

        self.hBoxLayout.setSpacing(15)
        self.hBoxLayout.setContentsMargins(24, 5, 24, 5)

    def addWidget(self, widget: QWidget, stretch=0):
        self.hBoxLayout.addWidget(widget, stretch=stretch)

    @property
    def backgroundColor(self):
        return QColor(255, 255, 255, 13 if isDarkTheme() else 200)

    def paintEvent(self, e):
        painter = QPainter(self)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing)

        if isDarkTheme():
            painter.setPen(QColor(0, 0, 0, 96))
        else:
            painter.setPen(QColor(0, 0, 0, 24))

        painter.drawLine(self.rect().topLeft(), self.rect().topRight())


class TaskCard(CardWidget):
    """ Task card base class """

    deleted = Signal()   # TODO Send Task ID, or lambda function?
    checkedChanged = Signal(bool)

    def __init__(self, task: Task, parent=None):
        super().__init__(parent)
        self.task = task
        # self.keyword = ""   # Task keyword, 用于搜索

        self.checkBox = CheckBox(self)
        self.checkBox.setFixedSize(23, 23)
        self.setSelectionMode(False)

        self.checkBox.stateChanged.connect(self._onCheckedChanged)

    def setSelectionMode(self, isSelected: bool):
        self.isSelectionMode = isSelected
        self.checkBox.setVisible(isSelected)
        if not isSelected:
            self.checkBox.setChecked(False)

        self.update()

    def refresh(self):
        raise NotImplementedError

    def isChecked(self):
        return self.checkBox.isChecked()

    def setChecked(self, checked):
        if checked == self.isChecked():
            return

        self.checkBox.setChecked(checked)
        self.update()

    def resumeTask(self):
        coreService.createTask(self.task)
        raise NotImplementedError

    def pauseTask(self):
        coreService.stopTask(self.task)
        raise NotImplementedError

    def removeTask(self, deleteFile=False):
        coreService.stopTask(self.task)
        # TODO task resolve path
        raise NotImplementedError

    def mouseReleaseEvent(self, e):
        super().mouseReleaseEvent(e)
        if self.isSelectionMode:
            self.setChecked(not self.isChecked())
        else:
            self.setSelectionMode(True)
            self.setChecked(True)

    def _onDeleteButtonClicked(self):
        w = DeleteTaskDialog(self.window(), deleteOnClose=False)
        w.deleteFileCheckBox.setChecked(False)

        if w.exec():
            self.removeTask(w.deleteFileCheckBox.isChecked())

        w.deleteLater()

    def _onCheckedChanged(self):
        self.setChecked(self.checkBox.isChecked())
        self.checkedChanged.emit(self.checkBox.isChecked())
        self.update()

    def paintEvent(self, e):
        if self.isSelectionMode and self.isChecked():
            painter = QPainter(self)
            painter.setRenderHints(QPainter.RenderHint.Antialiasing)

            r = self.borderRadius
            painter.setPen(QPen(themeColor(), 2))
            painter.setBrush(QColor(255, 255, 255, 15) if isDarkTheme() else QColor(0, 0, 0, 8))
            painter.drawRoundedRect(self.rect().adjusted(2, 2, -2, -2), r, r)

        return super().paintEvent(e)

