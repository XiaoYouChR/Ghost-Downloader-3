from pathlib import Path
from typing import Any

from PySide6.QtCore import Signal, QFileInfo, Qt, QEvent, QMimeData
from PySide6.QtGui import QColor, QPainter, QPen, QMouseEvent
from PySide6.QtWidgets import QWidget, QHBoxLayout, QFileIconProvider, QVBoxLayout, QApplication
from loguru import logger
from qfluentwidgets import BodyLabel, isDarkTheme, CardWidget, CheckBox, \
    themeColor, IconWidget, ImageLabel, StrongBodyLabel, FluentIcon, PrimaryToolButton, ToolButton, \
    TransparentToolButton, ProgressBar, IndeterminateProgressBar, LineEdit, RoundMenu, Action

from app.bases.models import Task, TaskStatus, SpecialFileSize
from app.services.core_service import coreService
from app.supports.recorder import taskRecorder
from app.supports.utils import openFile, getReadableSize, getReadableTime, openFolder
from app.supports.config import GD3_COPY_MIME_TYPE
from app.view.components.dialogs import DeleteTaskDialog, FileHashDialog
from app.view.components.labels import IconBodyLabel


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


class ParseSettingCard(QWidget):
    payloadChanged = Signal()

    def __init__(self, icon, title: str, parent=None):
        super().__init__(parent=parent)
        self.hBoxLayout = QHBoxLayout(self)

        self.iconWidget = IconWidget(icon, self)
        self.titleLabel = BodyLabel(title, self)

        self.initWidget()
        self.initCustomWidget()

    def initCustomWidget(self):
        raise NotImplementedError

    def initWidget(self):
        self.setFixedHeight(50)
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
        return QColor(255, 255, 255, 13 if isDarkTheme() else 128)

    def paintEvent(self, e):
        painter = QPainter(self)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing)

        if isDarkTheme():
            painter.setPen(QColor(0, 0, 0, 96))
        else:
            painter.setPen(QColor(0, 0, 0, 48))

        painter.drawLine(self.rect().topLeft(), self.rect().topRight())

    @property
    def payload(self) -> dict[str, Any]:
        raise NotImplementedError

class TaskCard(CardWidget):
    """ Task card base class """

    deleted = Signal()
    finished = Signal()
    selectionChanged = Signal(bool, bool)

    def __init__(self, task: Task, parent=None):
        super().__init__(parent)
        self.task = task

        self.checkBox = CheckBox(self)
        self.checkBox.setFixedSize(23, 23)
        self.setSelectionMode(False)

        self.checkBox.clicked.connect(lambda checked: self.selectionChanged.emit(checked, False))

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

    def redownloadTask(self):
        raise NotImplementedError

    def removeTask(self, deleteFile=False):
        coreService.stopTask(self.task)
        try:
            self.onTaskDeleted(deleteFile)
        except Exception as e:
            logger.opt(exception=e).error("failed to delete task resources {}", self.task.taskId)
        finally:
            self.deleted.emit()

    def createContextMenu(self) -> RoundMenu | None:
        menu = RoundMenu(parent=self)
        copyUrlAction = Action(FluentIcon.COPY, self.tr("复制下载链接"), self)
        copyUrlAction.triggered.connect(self._copyTaskUrl)
        menu.addAction(copyUrlAction)
        redownloadAction = Action(FluentIcon.UPDATE, self.tr("重新下载"), self)
        redownloadAction.triggered.connect(self.redownloadTask)
        menu.addAction(redownloadAction)
        return menu

    def _copyTaskUrl(self):
        clipboard = QApplication.clipboard()
        mimeData = QMimeData()
        mimeData.setText(self.task.url)
        mimeData.setData(GD3_COPY_MIME_TYPE, b"1")
        clipboard.setMimeData(mimeData)

    def mouseReleaseEvent(self, e):
        super().mouseReleaseEvent(e)
        if e.button() != Qt.MouseButton.LeftButton:
            return

        extend = bool(e.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        checked = True if extend or not self.isSelectionMode else not self.isChecked()
        self.selectionChanged.emit(checked, extend)

    def mouseDoubleClickEvent(self, e):
        super().mouseDoubleClickEvent(e)
        if e.button() != Qt.MouseButton.LeftButton:
            return

        openFile(self.task.resolvePath)

    def contextMenuEvent(self, e):
        menu = self.createContextMenu()
        if menu is None:
            super().contextMenuEvent(e)

        menu.exec(e.globalPos())
        e.accept()

    def _onDeleteButtonClicked(self):
        w = DeleteTaskDialog(self.window(), deleteOnClose=False)
        w.deleteFileCheckBox.setChecked(False)

        if w.exec():
            self.removeTask(w.deleteFileCheckBox.isChecked())

        w.deleteLater()


    def paintEvent(self, e):
        if self.isSelectionMode and self.isChecked():
            painter = QPainter(self)
            painter.setRenderHints(QPainter.RenderHint.Antialiasing)

            r = self.borderRadius
            painter.setPen(QPen(themeColor(), 2))
            painter.setBrush(QColor(255, 255, 255, 15) if isDarkTheme() else QColor(0, 0, 0, 8))
            painter.drawRoundedRect(self.rect().adjusted(2, 2, -2, -2), r, r)

        return super().paintEvent(e)

    def onTaskFinished(self):
        self.finished.emit()

    def onTaskDeleted(self, completely: bool = False):
        if not completely:
            return

        raise NotImplementedError

    def onTaskFailed(self):
        raise NotImplementedError


class UniversalTaskCard(TaskCard):
    """ Task card """
    def __init__(self, task: Task, parent=None):
        super().__init__(task, parent)
        self.setFixedHeight(60)
        self.task = task
        self.cardStatus = self.task.status

        self.hBoxLayout = QHBoxLayout(self)
        self.iconLabel = ImageLabel(self)
        self.infoVBoxLayout = QVBoxLayout(self)
        self.filenameLabel = StrongBodyLabel(self.task.title, self)
        self.infoLayout = QHBoxLayout(self)
        self.speedLabel = IconBodyLabel("", FluentIcon.SPEED_HIGH, self)
        self.leftTimeLabel = IconBodyLabel("", FluentIcon.STOP_WATCH, self)
        self.progressLabel = IconBodyLabel("", FluentIcon.LIBRARY, self)
        self.infoLabel = IconBodyLabel("", FluentIcon.INFO, self)
        self.toggleRunningStatusButton = PrimaryToolButton(FluentIcon.PAUSE, self)
        self.verifyHashButton = ToolButton(FluentIcon.FINGERPRINT, self)
        self.openFileButton = ToolButton(FluentIcon.LINK, self)
        self.openFolderButton = ToolButton(FluentIcon.FOLDER, self)
        self.cancelButton = TransparentToolButton(FluentIcon.CLOSE, self)
        if self.task.fileSize in {SpecialFileSize.UNKNOWN, SpecialFileSize.NOT_SUPPORTED}:
            self.progressBar = IndeterminateProgressBar(self)
        else:
            self.progressBar = ProgressBar(self)
            self.progressBar.setCustomBackgroundColor(QColor(0, 0, 0, 0), QColor(0, 0, 0, 0))
        # init widgets
        self.infoLabel.hide()
        # self.infoLabel.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        # init
        self.initLayout()
        self.connectSignalToSlot()
        self._refreshIconLabel()
        self._renderTaskState()

    def _refreshIconLabel(self):
        self.iconLabel.setPixmap(QFileIconProvider().icon(QFileInfo(self.task.resolvePath)).pixmap(48, 48))
        self.iconLabel.setFixedSize(48, 48)

    def connectSignalToSlot(self):
        self.toggleRunningStatusButton.clicked.connect(self.toggleRunningStatus)
        self.verifyHashButton.clicked.connect(self._onVerifyHashButtonClicked)
        self.openFileButton.clicked.connect(lambda: openFile(self.task.resolvePath))
        self.openFolderButton.clicked.connect(lambda: openFolder(self.task.resolvePath))
        self.cancelButton.clicked.connect(self._onDeleteButtonClicked)

    def toggleRunningStatus(self):
        if self.task.status == TaskStatus.RUNNING:
            self.pauseTask()
        else:
            self.resumeTask()

    def refreshToggleButton(self):
        if self.task.status == TaskStatus.RUNNING:
            self.toggleRunningStatusButton.setIcon(FluentIcon.PAUSE)
            self.toggleRunningStatusButton.setEnabled(self.task.fileSize != SpecialFileSize.NOT_SUPPORTED)
        elif self.task.status == TaskStatus.COMPLETED:
            self.toggleRunningStatusButton.setIcon(FluentIcon.PLAY)
            self.toggleRunningStatusButton.setEnabled(False)
        else:
            self.toggleRunningStatusButton.setIcon(FluentIcon.PLAY)
            self.toggleRunningStatusButton.setEnabled(True)

        self.verifyHashButton.setVisible(self.task.status == TaskStatus.COMPLETED)
        self.verifyHashButton.setEnabled(self.task.status == TaskStatus.COMPLETED)

    def showStatusInfo(self, text: str):
        self.speedLabel.hide()
        self.leftTimeLabel.hide()
        self.progressLabel.hide()
        self.infoLabel.setText(text)
        self.infoLabel.show()

    def _renderTaskState(self):
        division = len(self.task.stages)
        progress = 0
        speed = 0
        receivedBytes = 0

        for stage in self.task.stages:
            progress += stage.progress
            speed += stage.speed
            receivedBytes += stage.receivedBytes

        progress /= division

        self.progressBar.setValue(progress)

        if self.task.fileSize > 0:
            self.progressLabel.setText(f"{getReadableSize(receivedBytes)}/{getReadableSize(self.task.fileSize)}")
        else:
            self.progressLabel.setText(f"{getReadableSize(receivedBytes)}/--")

        if self.task.status == TaskStatus.RUNNING:
            self.progressBar.setError(False)
            if self.infoLabel.isVisible():
                self.infoLabel.hide()
                self.speedLabel.show()
                self.leftTimeLabel.show()
                self.progressLabel.show()
            self.speedLabel.setText(f"{getReadableSize(speed)}/s")
            if self.task.fileSize > 0:
                self.progressLabel.setText(f"{getReadableSize(receivedBytes)}/{getReadableSize(self.task.fileSize)}")
                self.leftTimeLabel.setText(getReadableTime(int((self.task.fileSize - receivedBytes) / speed)) if speed != 0 else "--m--s")
            else:
                self.progressLabel.setText(f"{getReadableSize(receivedBytes)}/--")
                self.leftTimeLabel.setText("--")
        elif self.task.status == TaskStatus.COMPLETED:
            if self.task.fileSize > 0:
                self.progressBar.setError(False)
                self.progressBar.hide()
            else:
                self.progressBar.stop()
            self.showStatusInfo(self.tr("任务已经完成"))
        elif self.task.status == TaskStatus.FAILED:
            self.progressBar.error()
            self.onTaskFailed()
        elif self.task.status == TaskStatus.PAUSED:
            self.progressBar.setError(False)
            self.progressBar.pause()
            self.showStatusInfo(self.tr("任务已经暂停"))
        else:
            self.progressBar.setError(False)
            self.progressBar.pause()
            self.showStatusInfo(self.tr("任务正在等待"))

        self.refreshToggleButton()

    def refresh(self):
        """通过 self.task 刷新界面"""
        if self.cardStatus == TaskStatus.COMPLETED or self.cardStatus == TaskStatus.FAILED:
            return

        if self.task.status == TaskStatus.COMPLETED and self.cardStatus != TaskStatus.COMPLETED:
            self.onTaskFinished()

        self._renderTaskState()

        if self.task.status != self.cardStatus:
            taskRecorder.flush()
            self.cardStatus = self.task.status

    def onTaskFinished(self):
        super().onTaskFinished()
        self._refreshIconLabel()

    def onTaskDeleted(self, completely: bool = False):
        if not completely:
            return

        candidates: set[Path] = set()
        if self.task.resolvePath:
            candidates.add(Path(self.task.resolvePath))
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
                    logger.opt(exception=e).error("failed to remove file {}", path)

    def onTaskFailed(self):
        message = self.task.lastError
        if not message:
            message = self.tr("下载过程中发生错误，请稍后重试")

        logger.warning("任务失败 {}: {}", self.task.title, message)
        self.showStatusInfo(message)

    def _onVerifyHashButtonClicked(self):
        if not Path(self.task.resolvePath).is_file():
            self.showStatusInfo(self.tr("文件不存在，无法校验"))
            return

        w = FileHashDialog(self.task.resolvePath, self.window(), deleteOnClose=False)
        w.hashReady.connect(self._onFileHashReady)
        w.hashFailed.connect(self._onFileHashFailed)
        w.exec()
        w.deleteLater()

    def _onFileHashReady(self, algorithm: str, digest: str):
        logger.info("任务文件校验完成 {} {}", self.task.title, algorithm)
        self.showStatusInfo(f"{algorithm}: {digest}")

    def _onFileHashFailed(self, error: str):
        logger.warning("任务文件校验失败 {}: {}", self.task.title, error)
        self.showStatusInfo(self.tr("校验失败：{0}").format(error))

    def redownloadTask(self):
        self.toggleRunningStatusButton.setDisabled(True)
        coreService.runCoroutine(
            coreService._stopTask(self.task),
            self._onTaskStoppedForRedownload,
        )

    def _onTaskStoppedForRedownload(self, _result=None, error: str | None = None):
        if error:
            logger.warning("重新下载任务失败 {}: {}", self.task.title, error)
            self.showStatusInfo(self.tr("重新下载失败：{0}").format(error))
            self.toggleRunningStatusButton.setEnabled(True)
            return

        try:
            self.onTaskDeleted(True)
            self.task.reset()
            self.cardStatus = self.task.status
            self._refreshIconLabel()
            self._renderTaskState()
            taskRecorder.flush()
            self.resumeTask()
            self.progressBar.show()
        except Exception as e:
            logger.opt(exception=e).error("重置任务失败 {}", self.task.title)
            self.showStatusInfo(self.tr("重新下载失败，请稍后重试"))
            self.toggleRunningStatusButton.setEnabled(True)

    def resumeTask(self):
        self.toggleRunningStatusButton.setIcon(FluentIcon.PAUSE)
        self.toggleRunningStatusButton.setDisabled(True)
        coreService.createTask(self.task)
        self.cardStatus = self.task.status
        self._renderTaskState()
        taskRecorder.flush()
        self.toggleRunningStatusButton.setEnabled(True)

    def pauseTask(self):
        if self.task.fileSize == SpecialFileSize.NOT_SUPPORTED:
            return

        self.toggleRunningStatusButton.setIcon(FluentIcon.PLAY)
        self.toggleRunningStatusButton.setDisabled(True)
        coreService.stopTask(self.task)
        self.cardStatus = self.task.status
        self._renderTaskState()
        taskRecorder.flush()
        self.toggleRunningStatusButton.setEnabled(True)

    def initLayout(self):
        self.hBoxLayout.addWidget(self.checkBox)
        self.hBoxLayout.addWidget(self.iconLabel)

        self.infoVBoxLayout.addWidget(self.filenameLabel)
        self.infoLayout.addWidget(self.speedLabel)
        self.infoLayout.addWidget(self.leftTimeLabel)
        self.infoLayout.addWidget(self.progressLabel)
        self.infoLayout.addWidget(self.infoLabel)
        self.infoLayout.addStretch()
        self.infoVBoxLayout.addLayout(self.infoLayout)
        self.infoVBoxLayout.setContentsMargins(2, 8, 2, 8)
        self.hBoxLayout.addLayout(self.infoVBoxLayout)
        self.hBoxLayout.addStretch()
        self.hBoxLayout.addWidget(self.toggleRunningStatusButton)
        self.hBoxLayout.addWidget(self.verifyHashButton)
        self.hBoxLayout.addWidget(self.openFileButton)
        self.hBoxLayout.addWidget(self.openFolderButton)
        self.hBoxLayout.addWidget(self.cancelButton)

        self.hBoxLayout.setContentsMargins(12, 0, 12, 0)

    def resizeEvent(self, e):
        self.progressBar.setGeometry(4, self.height() - 4, self.width() - 8, 4)
        return super().resizeEvent(e)


class UniversalResultCard(ResultCard):
    def __init__(self, task: Task, parent: QWidget = None):
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
        icon = QFileIconProvider().icon(QFileInfo(self.task.resolvePath))
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
            self.task.setTitle(newFilename)
            self.filenameLabel.setText(newFilename)
            self.resetFileIcon()

        self.filenameEdit.hide()
        self.filenameLabel.show()
        self.filenameLabel.setFocus()

    def setFilename(self, filename: str):
        """设置文件名"""
        self.task.setTitle(filename)
        self.filenameLabel.setText(filename)
        self.filenameEdit.setText(filename)
        self.resetFileIcon()

    def getTask(self) -> Task:
        return self.task
