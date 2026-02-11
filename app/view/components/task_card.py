from pathlib import Path
import sys
from PySide6.QtCore import Qt, Signal, Property, QFileInfo, QSize
from PySide6.QtGui import QPixmap, QPainter, QFont, QColor, QPen
from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QFileIconProvider

from qfluentwidgets import (CardWidget, IconWidget, ToolButton, FluentIcon,
                            BodyLabel, CaptionLabel, ProgressBar, ImageLabel, setFont,
                            MessageBoxBase, SubtitleLabel, CheckBox, InfoBar, InfoBarPosition,
                            PushButton, ToolTipFilter, InfoLevel, DotInfoBadge, MessageBox,
                            isDarkTheme, themeColor, RoundMenu, Action, MenuAnimationType, StrongBodyLabel,
                            PrimaryPushButton, TransparentToolButton, PrimaryToolButton)

from app.view.components.dialogs import DeleteTaskDialog
from app.bases.models import Task
from app.view.components.labels import IconBodyLabel


class TaskCardBase(CardWidget):
    """ Task card base class """

    deleted = Signal(str)   # Send Task ID
    checkedChanged = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.keyword = ""   # Task keyword, 用于搜索

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

    def isChecked(self):
        return self.checkBox.isChecked()

    def setChecked(self, checked):
        if checked == self.isChecked():
            return

        self.checkBox.setChecked(checked)
        self.update()

    def removeTask(self, deleteFile=False):
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

class TaskCard(TaskCardBase):
    """ Task card """
    def __init__(self, task: Task, parent=None):
        super().__init__(parent)
        self.task = task
        self.setFixedHeight(60)

        self.hBoxLayout = QHBoxLayout(self)
        self.iconLabel = ImageLabel(QFileIconProvider().icon(QFileInfo("C:/Users/XiaoYouChR/Videos/Captures/反恐精英：全球攻势 2025-11-09 12-51-21.mp4")).pixmap(48, 48), self)
        # TODO macOS
        self.iconLabel.setFixedSize(48, 48)

        self.infoVBoxLayout = QVBoxLayout(self)
        self.filenameLabel = StrongBodyLabel(self.task.title, self)
        self.infoLayout = QHBoxLayout(self)
        self.speedLabel = IconBodyLabel("0.00MB/s", FluentIcon.SPEED_HIGH, self)
        self.leftTimeLabel = IconBodyLabel("00:00:00", FluentIcon.STOP_WATCH, self)
        self.progressLabel = IconBodyLabel("2.22MB/342.12MB", FluentIcon.LIBRARY, self)
        self.pauseButton = PrimaryToolButton(FluentIcon.PAUSE, self)
        self.openFileButton = ToolButton(FluentIcon.LINK, self)
        self.openFolderButton = ToolButton(FluentIcon.FOLDER, self)
        self.cancelButton = TransparentToolButton(FluentIcon.CLOSE, self)
        self.progressBar = ProgressBar(self)
        self.progressBar.setCustomBackgroundColor(QColor(0, 0, 0, 0), QColor(0, 0, 0, 0))
        # init
        self.initLayout()
        # TODO For Test
        self.progressBar.setValue(24)

    def initLayout(self):
        self.hBoxLayout.addWidget(self.checkBox)
        self.hBoxLayout.addWidget(self.iconLabel)

        self.infoVBoxLayout.addWidget(self.filenameLabel)
        self.infoLayout.addWidget(self.speedLabel)
        self.infoLayout.addWidget(self.leftTimeLabel)
        self.infoLayout.addWidget(self.progressLabel)
        self.infoVBoxLayout.addLayout(self.infoLayout)
        self.infoVBoxLayout.setContentsMargins(2, 8, 2, 8)
        self.hBoxLayout.addLayout(self.infoVBoxLayout)
        self.hBoxLayout.addStretch()
        self.hBoxLayout.addWidget(self.pauseButton)
        self.hBoxLayout.addWidget(self.openFileButton)
        self.hBoxLayout.addWidget(self.openFolderButton)
        self.hBoxLayout.addWidget(self.cancelButton)

        self.hBoxLayout.setContentsMargins(12, 0, 12, 0)

    def resizeEvent(self, e):
        self.progressBar.setGeometry(4, self.height() - 4, self.width() - 8, 4)
        return super().resizeEvent(e)
