from PySide6.QtCore import Qt, QEvent, QFileInfo, Signal
from PySide6.QtGui import QMouseEvent, QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget, QHBoxLayout, QFileIconProvider, QVBoxLayout
from qfluentwidgets import ImageLabel, StrongBodyLabel, LineEdit, BodyLabel, isDarkTheme, CardWidget, CheckBox, \
    themeColor, FluentIcon, PrimaryToolButton, ToolButton, TransparentToolButton, ProgressBar, IconWidget, CaptionLabel

from app.bases.models import Task
from app.supports.utils import getReadableSize
from app.view.components.dialogs import DeleteTaskDialog
from app.view.components.labels import IconBodyLabel


class ResultCardBase(QWidget):
    """显示下载链接解析结果的卡片组件"""

    def __init__(self, filename: str, fileSize: int, url: str, parent: QWidget = None):
        super().__init__(parent)
        self.filename = filename
        self.fileSize = fileSize
        self.url = url
        self.borderRadius = 5

        self.iconLabel = ImageLabel(self)
        self.filenameLabel = StrongBodyLabel(filename, self)
        self.filenameEdit = LineEdit(self)
        self.sizeLabel = BodyLabel(getReadableSize(fileSize), self)
        self.mainLayout = QHBoxLayout(self)

        self.initWidget()
        self.initLayout()

    def initWidget(self):
        """初始化组件属性"""
        self.setFixedHeight(35)
        self.resetFileIcon()
        # 设置文件名标签
        self.filenameLabel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.filenameLabel.installEventFilter(self)
        # 设置编辑框
        self.filenameEdit.setText(self.filename)
        self.filenameEdit.editingFinished.connect(self._onEditingFinished)
        self.filenameEdit.hide()

    def initLayout(self):
        """初始化布局"""
        self.mainLayout.setContentsMargins(10, 2, 10, 2)
        self.mainLayout.setSpacing(12)
        self.mainLayout.addWidget(self.iconLabel)
        self.mainLayout.addWidget(self.filenameLabel)
        self.mainLayout.addWidget(self.filenameEdit)
        self.mainLayout.addStretch()
        self.mainLayout.addWidget(self.sizeLabel)

    def eventFilter(self, obj, event: QEvent):
        """事件过滤器，处理双击事件"""
        if obj is self.filenameLabel:
            if event.type() == QEvent.Type.MouseButtonDblClick and isinstance(event, QMouseEvent):
                if event.button() == Qt.MouseButton.LeftButton:
                    self._enterEditMode()
                    return True
        return super().eventFilter(obj, event)

    def resetFileIcon(self):
        icon = QFileIconProvider().icon(QFileInfo(self.filename))
        self.iconLabel.setImage(icon.pixmap(16, 16))
        self.iconLabel.setFixedSize(16, 16)

    def _enterEditMode(self):
        """进入编辑模式"""
        self.filenameLabel.hide()
        self.filenameEdit.show()
        self.filenameEdit.setFocus()
        self.filenameEdit.selectAll()

    def _onEditingFinished(self):
        """编辑完成回调"""
        newFilename = self.filenameEdit.text().strip()
        if newFilename and newFilename != self.filename:
            self.filename = newFilename
            self.filenameLabel.setText(newFilename)
            self.resetFileIcon()

        self.filenameEdit.hide()
        self.filenameLabel.show()
        self.filenameLabel.setFocus()

    def getData(self) -> dict:
        """获取卡片数据"""
        return {
            "filename": self.filename,
            "file_size": self.fileSize,
            "url": self.url
        }

    def setFilename(self, filename: str):
        """设置文件名"""
        self.filename = filename
        self.filenameLabel.setText(filename)
        self.filenameEdit.setText(filename)

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
