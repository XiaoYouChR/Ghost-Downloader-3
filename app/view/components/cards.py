from pathlib import Path
from typing import Any

from PySide6.QtCore import Signal, QFileInfo, Qt, QEvent
from PySide6.QtGui import QColor, QPainter, QPen, QMouseEvent
from PySide6.QtWidgets import QWidget, QHBoxLayout, QFileIconProvider, QVBoxLayout, QApplication
from loguru import logger
from qfluentwidgets import BodyLabel, isDarkTheme, CardWidget, CheckBox, \
    themeColor, IconWidget, ImageLabel, StrongBodyLabel, FluentIcon, PrimaryToolButton, ToolButton, \
    TransparentToolButton, ProgressBar, IndeterminateProgressBar, LineEdit, \
    RoundMenu, Action, ToolTipFilter

from app.bases.models import Task, TaskStatus, SpecialFileSize
from app.services.category_service import UNCATEGORIZED_ID, categoryService
from app.services.core_service import coreService
from app.supports.config import cfg
from app.services.task_service import taskService
from app.supports.utils import openFile, toReadableSize, toReadableTime, openFolder
from app.view.components.dialogs import DeleteTaskDialog, FileHashDialog
from app.view.components.labels import IconBodyLabel, IconStrongBodyLabel


class ResultCard(QWidget):
    """显示下载链接解析结果的卡片组件"""

    categoryPicked = Signal(str)
    editRequested = Signal()

    def __init__(self, task: Task, parent: QWidget = None):
        super().__init__(parent)
        self.task = task
        self.borderRadius = 5

        self.categoryButton = TransparentToolButton(self)
        self.categoryMenu = RoundMenu(parent=self.categoryButton)
        self.editButton = TransparentToolButton(FluentIcon.EDIT, self)

        self._initCategoryButton()
        self._initEditButton()

    def _initEditButton(self):
        self.editButton.setFixedSize(28, 28)
        self.editButton.setToolTip(self.tr("编辑任务参数"))
        self.editButton.installEventFilter(ToolTipFilter(self.editButton))
        self.editButton.clicked.connect(self.editRequested.emit)
        self.editButton.setVisible(self.task.supportsEdit)

    def _initCategoryButton(self):
        self.categoryButton.setFixedSize(28, 28)
        self.categoryButton.installEventFilter(ToolTipFilter(self.categoryButton))
        self.categoryButton.clicked.connect(self._showCategoryMenu)
        cfg.enableCategory.valueChanged.connect(self._renderCategoryButton)
        categoryService.categoriesChanged.connect(self._refreshCategoryMenu)
        self._refreshCategoryMenu()

    def _showCategoryMenu(self):
        bottomLeft = self.categoryButton.mapToGlobal(
            self.categoryButton.rect().bottomLeft()
        )
        self.categoryMenu.exec(bottomLeft)

    def _refreshCategoryMenu(self):
        self.categoryMenu.clear()
        uncategorized = Action(FluentIcon.MORE, self.tr("未分类"), self)
        uncategorized.triggered.connect(
            lambda: self._onCategoryPicked(UNCATEGORIZED_ID)
        )
        self.categoryMenu.addAction(uncategorized)
        self.categoryMenu.addSeparator()
        for category in categoryService.categories():
            cid = category.categoryId
            action = Action(category.fluentIcon(), category.name, self)
            action.triggered.connect(
                lambda checked=False, c=cid: self._onCategoryPicked(c)
            )
            self.categoryMenu.addAction(action)
        self._renderCategoryButton()

    def _renderCategoryButton(self):
        if not cfg.enableCategory.value:
            self.categoryButton.hide()
            return
        category = categoryService.categoryById(self.task.category)
        if category is None:
            self.categoryButton.setIcon(FluentIcon.MORE)
            self.categoryButton.setToolTip(self.tr("未分类"))
        else:
            self.categoryButton.setIcon(category.fluentIcon())
            self.categoryButton.setToolTip(category.name)
        self.categoryButton.show()

    def _onCategoryPicked(self, categoryId: str):
        self.task.category = categoryId
        self._renderCategoryButton()
        self.categoryPicked.emit(categoryId)

    def getTask(self) -> Task:
        return self.task

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

    finished = Signal()
    selectionChanged = Signal(bool, bool)
    categoryChanged = Signal()

    def __init__(self, task: Task, parent=None):
        super().__init__(parent)
        self.task = task

        self.checkBox = CheckBox(self)
        self.checkBox.setFixedSize(23, 23)
        self.setSelectionMode(False)

        self.checkBox.clicked.connect(lambda checked: self.selectionChanged.emit(checked, False))

    def refresh(self):
        raise NotImplementedError

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

    def resumeTask(self):
        coreService.createTask(self.task)
        raise NotImplementedError

    def pauseTask(self):
        coreService.stopTask(self.task)
        raise NotImplementedError

    def redownloadTask(self):
        raise NotImplementedError

    def removeTask(self, deleteFile=False):
        if coreService.task(self.task.taskId) is None:
            self._onTaskStoppedForDeletion(deleteFile)
            return
        coreService.runCoroutine(
            coreService._stopTask(self.task),
            lambda _result, error: self._onTaskStoppedForDeletion(deleteFile, error),
        )

    def _onTaskStoppedForDeletion(self, deleteFile: bool, error: str | None = None):
        if error:
            logger.warning("failed to stop task {} before deletion: {}", self.task.taskId, error)
            return

        if deleteFile:
            # InstallTask.cleanup 删整个 installFolder, 工具进程占用时会抛
            try:
                self.task.cleanup()
            except Exception as e:
                logger.opt(exception=e).error("failed to clean up task resources {}", self.task.taskId)

        taskService.remove(self.task)

    def createContextMenu(self) -> RoundMenu | None:
        menu = RoundMenu(parent=self)
        copyUrlAction = Action(FluentIcon.COPY, self.tr("复制下载链接"), self)
        copyUrlAction.triggered.connect(lambda: QApplication.clipboard().setText(self.task.url))
        menu.addAction(copyUrlAction)

        canEdit = (
            self.task.supportsEdit
            and self.task.status != TaskStatus.COMPLETED
            and (self.task.status != TaskStatus.RUNNING or self.task.canPause)
        )
        if canEdit:
            editAction = Action(FluentIcon.EDIT, self.tr("编辑任务参数..."), self)
            editAction.triggered.connect(self._onEditTaskClicked)
            menu.addAction(editAction)

        redownloadAction = Action(FluentIcon.UPDATE, self.tr("重新下载"), self)
        redownloadAction.triggered.connect(self.redownloadTask)
        menu.addAction(redownloadAction)

        if cfg.enableCategory.value:
            moveMenu = RoundMenu(self.tr("移动到分类"), self)
            moveMenu.setIcon(FluentIcon.TAG)

            uncategorizedAction = Action(FluentIcon.MORE, self.tr("未分类"), self)
            uncategorizedAction.triggered.connect(
                lambda: self.setTaskCategory(UNCATEGORIZED_ID)
            )
            moveMenu.addAction(uncategorizedAction)
            moveMenu.addSeparator()
            for category in categoryService.categories():
                categoryId = category.categoryId
                action = Action(category.fluentIcon(), category.name, self)
                action.triggered.connect(
                    lambda checked=False, cid=categoryId: self.setTaskCategory(cid)
                )
                moveMenu.addAction(action)
            menu.addMenu(moveMenu)

        return menu

    def setTaskCategory(self, categoryId: str):
        if self.task.category == categoryId:
            return
        self.task.category = categoryId
        taskService.scheduleFlush()
        self._onCategoryUpdated()
        self.categoryChanged.emit()

    def _onCategoryUpdated(self):
        pass

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

        openFile(self.task.outputFolder)

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

    def _onEditTaskClicked(self):
        # 等 _stopTask 完成再开 Dialog, 否则 createTask 撞 runningTasks 旧 entry
        if self.task.status == TaskStatus.RUNNING and self.task.canPause:
            coreService.runCoroutine(
                coreService._stopTask(self.task),
                lambda *_: self._openEditTaskDialog(autoResume=True),
            )
        else:
            self._openEditTaskDialog(autoResume=False)

    def _openEditTaskDialog(self, autoResume: bool):
        from app.view.components.edit_task_dialog import EditTaskDialog

        dialog = EditTaskDialog(
            self.task, context="task", autoResume=autoResume, parent=self.window()
        )
        dialog.exec()
        dialog.deleteLater()
        self.refresh()


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

    def onTaskFailed(self):
        raise NotImplementedError


class UniversalTaskCard(TaskCard):
    """ Task card """
    def __init__(self, task: Task, parent=None):
        super().__init__(task, parent)
        self.setFixedHeight(60)
        self.task = task
        self.cardStatus: TaskStatus = self.task.status

        self.hBoxLayout = QHBoxLayout(self)
        self.iconLabel = ImageLabel(self)
        self.infoVBoxLayout = QVBoxLayout(self)
        self.filenameLabel = IconStrongBodyLabel(self.task.title, self)
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
        self.progressBar = self.createProgressBar()
        self.infoLabel.hide()

        self.initLayout()
        self.connectSignalToSlot()
        self._refreshIconLabel()
        self._renderCategoryIcon()
        self._renderTaskState()

        cfg.enableCategory.valueChanged.connect(self._renderCategoryIcon)
        categoryService.categoriesChanged.connect(self._renderCategoryIcon)

    def createProgressBar(self) -> QWidget:
        if self.task.fileSize in {SpecialFileSize.UNKNOWN, SpecialFileSize.NOT_SUPPORTED}:
            return IndeterminateProgressBar(self)
        bar = ProgressBar(self)
        bar.setCustomBackgroundColor(QColor(0, 0, 0, 0), QColor(0, 0, 0, 0))
        return bar

    def _renderCategoryIcon(self):
        if not cfg.enableCategory.value or not self.task.category:
            self.filenameLabel.setIcon(None)
            return

        category = categoryService.categoryById(self.task.category)
        if category is None:
            self.filenameLabel.setIcon(None)
            return

        self.filenameLabel.setIcon(category.fluentIcon())

    def _onCategoryUpdated(self):
        self._renderCategoryIcon()

    def _refreshIconLabel(self):
        self.iconLabel.setPixmap(QFileIconProvider().icon(QFileInfo(self.task.outputFolder)).pixmap(48, 48))
        self.iconLabel.setFixedSize(48, 48)

    def connectSignalToSlot(self):
        self.toggleRunningStatusButton.clicked.connect(self.toggleRunningStatus)
        self.verifyHashButton.clicked.connect(self._onVerifyHashButtonClicked)
        self.openFileButton.clicked.connect(lambda: openFile(self.task.outputFolder))
        self.openFolderButton.clicked.connect(lambda: openFolder(self.task.outputFolder))
        self.cancelButton.clicked.connect(self._onDeleteButtonClicked)

    def toggleRunningStatus(self):
        if self.task.status == TaskStatus.RUNNING:
            self.pauseTask()
        else:
            self.resumeTask()

    def refreshToggleButton(self):
        if self.task.status == TaskStatus.RUNNING:
            self.toggleRunningStatusButton.setIcon(FluentIcon.PAUSE)
            self.toggleRunningStatusButton.setEnabled(self.task.canPause)
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

    def statusInfoText(self) -> str | None:
        if self.task.status == TaskStatus.COMPLETED:
            return self.tr("任务已经完成")
        if self.task.status == TaskStatus.PAUSED:
            return self.tr("任务已经暂停")
        if self.task.status == TaskStatus.WAITING:
            return self.tr("任务正在等待")
        return None

    def _renderTaskState(self):
        progress, speed, receivedBytes = self.task.currentSnapshot()

        self.progressBar.setValue(progress)

        if self.task.fileSize > 0:
            self.progressLabel.setText(f"{toReadableSize(receivedBytes)}/{toReadableSize(self.task.fileSize)}")
        else:
            self.progressLabel.setText(f"{toReadableSize(receivedBytes)}/--")

        if self.task.status == TaskStatus.RUNNING:
            self.progressBar.setError(False)
            if self.infoLabel.isVisible():
                self.infoLabel.hide()
                self.speedLabel.show()
                self.leftTimeLabel.show()
                self.progressLabel.show()
            self.speedLabel.setText(f"{toReadableSize(speed)}/s")
            if self.task.fileSize > 0:
                self.leftTimeLabel.setText(toReadableTime(int((self.task.fileSize - receivedBytes) / speed)) if speed != 0 else "--m--s")
            else:
                self.leftTimeLabel.setText("--")
        elif self.task.status == TaskStatus.COMPLETED:
            if self.task.fileSize > 0:
                self.progressBar.setError(False)
                self.progressBar.hide()
            else:
                self.progressBar.stop()
            self.showStatusInfo(self.statusInfoText() or "")
        elif self.task.status == TaskStatus.FAILED:
            self.progressBar.error()
            self.onTaskFailed()
        else:
            self.progressBar.setError(False)
            self.progressBar.pause()
            self.showStatusInfo(self.statusInfoText() or "")

        self.refreshToggleButton()

    def refresh(self):
        if self.cardStatus == TaskStatus.COMPLETED or self.cardStatus == TaskStatus.FAILED:
            return

        if self.task.status == TaskStatus.COMPLETED and self.cardStatus != TaskStatus.COMPLETED:
            self.onTaskFinished()

        self._renderTaskState()

        if self.task.status != self.cardStatus:
            taskService.scheduleFlush()
            self.cardStatus = self.task.status

    def onTaskFinished(self):
        super().onTaskFinished()
        # M3U8 等 pack 在 _updateOutput 时才知道真实文件名，会调用 task.setTitle 改写 title
        self.filenameLabel.setText(self.task.title)
        self._refreshIconLabel()


    def onTaskFailed(self):
        message = self.task.lastError
        if not message:
            message = self.tr("下载过程中发生错误，请稍后重试")

        logger.warning("任务失败 {}: {}", self.task.title, message)
        self.showStatusInfo(message)

    def _onVerifyHashButtonClicked(self):
        if not Path(self.task.outputFolder).is_file():
            self.showStatusInfo(self.tr("文件不存在，无法校验"))
            return

        w = FileHashDialog(self.task.outputFolder, self.window(), deleteOnClose=False)
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
            self.task.cleanup()
            self.task.reset()
            self.cardStatus = self.task.status
            self._refreshIconLabel()
            self._renderTaskState()
            taskService.scheduleFlush()
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
        taskService.scheduleFlush()
        self.toggleRunningStatusButton.setEnabled(True)

    def pauseTask(self):
        if not self.task.canPause:
            return

        self.toggleRunningStatusButton.setIcon(FluentIcon.PLAY)
        self.toggleRunningStatusButton.setDisabled(True)
        coreService.stopTask(self.task)
        self.cardStatus = self.task.status
        self._renderTaskState()
        taskService.scheduleFlush()
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
        self.hBoxLayout.addLayout(self.infoVBoxLayout, 1)
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
        self.iconLabel = ImageLabel(self)
        self.filenameLabel = StrongBodyLabel(self.task.title, self)
        self.filenameEdit = LineEdit(self)
        self.sizeLabel = BodyLabel(toReadableSize(self.task.fileSize), self)
        self.mainLayout = QHBoxLayout(self)

        self.initWidget()
        self.initLayout()
        self._renderCategoryButton()

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
        self.mainLayout.addWidget(self.filenameLabel, 1)
        self.mainLayout.addWidget(self.filenameEdit, 1)
        self.mainLayout.addWidget(self.sizeLabel)
        self.mainLayout.addWidget(self.editButton)
        self.mainLayout.addWidget(self.categoryButton)

    def eventFilter(self, obj, event: QEvent):
        """事件过滤器，处理双击事件"""
        if obj is self.filenameLabel:
            if event.type() == QEvent.Type.MouseButtonDblClick and isinstance(event, QMouseEvent):
                if event.button() == Qt.MouseButton.LeftButton:
                    self._enterEditMode()
                    return True
        return super().eventFilter(obj, event)

    def resetFileIcon(self):
        icon = QFileIconProvider().icon(QFileInfo(self.task.outputFolder))
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
            self.filenameLabel.setText(self.task.title)
            self.filenameEdit.setText(self.task.title)
            self.resetFileIcon()

        self.filenameEdit.hide()
        self.filenameLabel.show()
        self.filenameLabel.setFocus()

    def setFilename(self, filename: str):
        """设置文件名"""
        self.task.setTitle(filename)
        self.filenameLabel.setText(self.task.title)
        self.filenameEdit.setText(self.task.title)
        self.resetFileIcon()

    def getTask(self) -> Task:
        return self.task
