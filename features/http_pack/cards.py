from PySide6.QtCore import QFileInfo, Qt, QEvent
from PySide6.QtGui import QColor, QMouseEvent
from PySide6.QtWidgets import QHBoxLayout, QFileIconProvider, QVBoxLayout, QWidget
from qfluentwidgets import ImageLabel, StrongBodyLabel, FluentIcon, PrimaryToolButton, ToolButton, \
    TransparentToolButton, ProgressBar, LineEdit, BodyLabel

from app.bases.models import Task
from app.supports.utils import getReadableSize
from app.view.components.cards import TaskCard, ResultCard
from app.view.components.labels import IconBodyLabel
from features.http_pack.task import HttpTask


class HttpTaskCard(TaskCard):
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


class HttpResultCard(ResultCard):
    def __init__(self, task: HttpTask, parent: QWidget = None):
        super().__init__(task, parent)
        self.task = task
        self.iconLabel = ImageLabel(self)
        self.filenameLabel = StrongBodyLabel(self.task.title, self)
        self.filenameEdit = LineEdit(self)
        self.sizeLabel = BodyLabel(getReadableSize(self.task.fileSize), self)
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
        self.filenameEdit.setText(self.task.title)
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
        icon = QFileIconProvider().icon(QFileInfo(self.task.title))
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
        if newFilename and newFilename != self.task.title:
            self.task.title = newFilename
            self.filenameLabel.setText(newFilename)
            self.resetFileIcon()

        self.filenameEdit.hide()
        self.filenameLabel.show()
        self.filenameLabel.setFocus()

    def setFilename(self, filename: str):
        """设置文件名"""
        self.task.title = filename
        self.filenameLabel.setText(filename)
        self.filenameEdit.setText(filename)

    def getTask(self) -> HttpTask:
        return self.task
