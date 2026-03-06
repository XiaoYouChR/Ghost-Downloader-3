from pathlib import Path

from PySide6.QtCore import QFileInfo, Qt, QEvent
from PySide6.QtGui import QColor, QMouseEvent
from PySide6.QtWidgets import QHBoxLayout, QFileIconProvider, QVBoxLayout, QWidget
from loguru import logger
from qfluentwidgets import ImageLabel, StrongBodyLabel, FluentIcon, PrimaryToolButton, ToolButton, \
    TransparentToolButton, ProgressBar, LineEdit, BodyLabel

from app.bases.models import TaskStatus
from app.services.core_service import coreService
from app.supports.recorder import taskRecorder
from app.supports.utils import getReadableSize, getReadableTime, openFile
from app.view.components.cards import TaskCard, ResultCard
from app.view.components.labels import IconBodyLabel
from features.http_pack.task import HttpTask, HttpTaskStage


class HttpTaskCard(TaskCard):
    """ Task card """
    def __init__(self, task: HttpTask, parent=None):
        super().__init__(task, parent)
        self.setFixedHeight(60)
        self.task = task
        self.cardStatus = TaskStatus.RUNNING

        self.hBoxLayout = QHBoxLayout(self)
        self.iconLabel = ImageLabel(QFileIconProvider().icon(QFileInfo(self.task.stages[0].resolvePath)).pixmap(48, 48), self)
        # TODO macOS
        self.iconLabel.setFixedSize(48, 48)

        self.infoVBoxLayout = QVBoxLayout(self)
        self.filenameLabel = StrongBodyLabel(self.task.title, self)
        self.infoLayout = QHBoxLayout(self)
        self.speedLabel = IconBodyLabel("", FluentIcon.SPEED_HIGH, self)
        self.leftTimeLabel = IconBodyLabel("", FluentIcon.STOP_WATCH, self)
        self.progressLabel = IconBodyLabel("", FluentIcon.LIBRARY, self)
        self.toggleRunningStatusButton = PrimaryToolButton(FluentIcon.PAUSE, self)
        self.openFileButton = ToolButton(FluentIcon.LINK, self)
        self.openFolderButton = ToolButton(FluentIcon.FOLDER, self)
        self.cancelButton = TransparentToolButton(FluentIcon.CLOSE, self)
        # TODO 分段进度条
        self.progressBar = ProgressBar(self)
        self.progressBar.setCustomBackgroundColor(QColor(0, 0, 0, 0), QColor(0, 0, 0, 0))
        # init
        self.initLayout()
        self.connectSignalToSlot()
        self.refreshToggleButton()

    def connectSignalToSlot(self):
        self.toggleRunningStatusButton.clicked.connect(self.toggleRunningStatus)
        self.openFileButton.clicked.connect(lambda: (openFile(self.task.path / self.task.title)))
        self.openFolderButton.clicked.connect(lambda: (openFile(self.task.path)))
        self.cancelButton.clicked.connect(self._onDeleteButtonClicked)

    def toggleRunningStatus(self):
        print("toggleRunningStatus", self.task.status)
        if self.task.status == TaskStatus.RUNNING:
            self.pauseTask()
        else:
            self.resumeTask()

    def refreshToggleButton(self):
        if self.task.status == TaskStatus.RUNNING:
            self.toggleRunningStatusButton.setIcon(FluentIcon.PAUSE)
            self.toggleRunningStatusButton.setEnabled(True)
        elif self.task.status == TaskStatus.COMPLETED:
            self.toggleRunningStatusButton.setIcon(FluentIcon.PLAY)
            self.toggleRunningStatusButton.setEnabled(False)
        else:
            self.toggleRunningStatusButton.setIcon(FluentIcon.PLAY)
            self.toggleRunningStatusButton.setEnabled(True)

    def refresh(self):
        """通过 self.task 刷新界面"""
        if self.cardStatus == TaskStatus.COMPLETED:
            return

        stage: HttpTaskStage = self.task.stages[0]

        self.task.syncStatus()
        self.progressBar.setValue(stage.progress)

        if self.task.fileSize > 0:
            self.progressLabel.setText(f"{getReadableSize(stage.receivedBytes)}/{getReadableSize(self.task.fileSize)}")
        else:
            self.progressLabel.setText(f"{getReadableSize(stage.receivedBytes)}/--")

        if self.task.status == TaskStatus.RUNNING:
            speed = stage.speed
            self.speedLabel.setText(f"{getReadableSize(speed)}/s")
            self.progressLabel.setText(getReadableSize(stage.receivedBytes) + "/" + getReadableSize(self.task.fileSize))
            self.leftTimeLabel.setText(getReadableTime(int((self.task.fileSize - stage.receivedBytes) / speed)) if speed != 0 else "--m--s")
        elif self.cardStatus != TaskStatus.COMPLETED and stage.status == TaskStatus.COMPLETED:
            self.onTaskFinished()
        elif self.cardStatus != TaskStatus.FAILED and self.task.status == TaskStatus.FAILED:
            self.onTaskFailed()
            # TODO 上报错误暂未实现
        elif self.cardStatus != TaskStatus.WAITING and self.task.status == TaskStatus.WAITING:
            self.speedLabel.setText("0.00 B/s")
            self.leftTimeLabel.setText("等待中")

        if self.task.status != self.cardStatus:
            taskRecorder.flush()
            self.cardStatus = self.task.status
            self.refreshToggleButton()

    def onTaskFinished(self):
        self.progressBar.setValue(100)
        self.speedLabel.setText("0.00 B/s")
        self.leftTimeLabel.setText("完成")

    def onTaskDeleted(self, completely: bool = False):
        if not completely:
            return

        candidates: set[Path] = set()
        candidates.add(Path(self.task.path) / self.task.title)
        for stage in self.task.stages:
            resolvePath = getattr(stage, "resolvePath", None)
            if resolvePath:
                candidates.add(Path(resolvePath))

        for target in candidates:
            if not target:
                continue

            for path in (target, Path(str(target) + ".ghd")):
                try:
                    if path.is_file() or path.is_symlink():
                        path.unlink()
                except FileNotFoundError:
                    continue
                except Exception as e:
                    logger.error(f"failed to remove file {path}: {repr(e)}")

    def onTaskFailed(self):
        self.speedLabel.setText("0.00 B/s")
        self.leftTimeLabel.setText("失败")

    def resumeTask(self):
        self.toggleRunningStatusButton.setIcon(FluentIcon.PAUSE)
        self.toggleRunningStatusButton.setDisabled(True)
        coreService.createTask(self.task)
        self.cardStatus = self.task.status
        taskRecorder.flush()
        self.toggleRunningStatusButton.setEnabled(True)

    def pauseTask(self):
        self.toggleRunningStatusButton.setIcon(FluentIcon.PLAY)
        self.toggleRunningStatusButton.setDisabled(True)
        coreService.stopTask(self.task)
        self.cardStatus = self.task.status
        taskRecorder.flush()
        self.toggleRunningStatusButton.setEnabled(True)
        # TODO 暂停样式

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
        self.hBoxLayout.addWidget(self.toggleRunningStatusButton)
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
