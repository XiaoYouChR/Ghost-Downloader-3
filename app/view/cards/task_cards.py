from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QApplication
from qfluentwidgets import (
    Action, CardWidget, CheckBox, FluentIcon, ImageLabel,
    IndeterminateProgressBar, PrimaryToolButton, ProgressBar,
    RoundMenu, ToolButton, ToolTipFilter, TransparentToolButton,
    isDarkTheme, themeColor,
)

from app.config.cfg import cfg
from app.format import toReadableSize, toReadableTime
from app.models.task import TaskStatus, SpecialFileSize
from app.platform.desktop import openFile, revealInFolder
from app.services.task_service import taskService
from app.view.components.labels import IconBodyLabel, IconStrongBodyLabel

if TYPE_CHECKING:
    from app.models.task import Task


class TaskCard(CardWidget):
    ROW_HEIGHT = 60
    selectionChanged = Signal(bool, bool)

    def __init__(self, task: Task, parent=None):
        super().__init__(parent)
        self._task = task
        self._selectionMode = False
        self._fileMissing = False

        self.checkBox = CheckBox(self)
        self.checkBox.setFixedSize(23, 23)
        self.checkBox.setVisible(False)
        self.checkBox.clicked.connect(lambda checked: self.selectionChanged.emit(checked, False))

    @property
    def task(self) -> Task:
        return self._task

    def refresh(self, force: bool = False) -> None:
        pass

    def setSelectionMode(self, enter: bool) -> None:
        self._selectionMode = enter
        self.checkBox.setVisible(enter)
        if not enter:
            self.checkBox.setChecked(False)
        self.update()

    def isChecked(self) -> bool:
        return self.checkBox.isChecked()

    def setChecked(self, checked: bool) -> None:
        if checked != self.isChecked():
            self.checkBox.setChecked(checked)
            self.update()

    def buildContextMenu(self) -> RoundMenu:
        menu = RoundMenu(parent=self)

        copyUrl = Action(FluentIcon.COPY, self.tr("复制下载链接"), self)
        copyUrl.triggered.connect(lambda: QApplication.clipboard().setText(self._task.url))
        menu.addAction(copyUrl)

        if self._task.canEdit and self._task.status != TaskStatus.COMPLETED:
            edit = Action(FluentIcon.EDIT, self.tr("编辑任务参数..."), self)
            edit.triggered.connect(self._onEditClicked)
            menu.addAction(edit)

        redownload = Action(FluentIcon.UPDATE, self.tr("重新下载"), self)
        redownload.triggered.connect(lambda: taskService.redownload(self._task))
        menu.addAction(redownload)

        if cfg.isCategoryEnabled.value:
            from app.services.category_service import categoryService
            moveMenu = RoundMenu(self.tr("移动到分类"), self)
            moveMenu.setIcon(FluentIcon.TAG)
            uncategorized = Action(FluentIcon.MORE, self.tr("未分类"), self)
            uncategorized.triggered.connect(lambda: taskService.setCategory(self._task, ""))
            moveMenu.addAction(uncategorized)
            moveMenu.addSeparator()
            for category in categoryService.categories():
                cid = category.categoryId
                action = Action(category.toIcon(), category.name, self)
                action.triggered.connect(lambda checked=False, c=cid: taskService.setCategory(self._task, c))
                moveMenu.addAction(action)
            menu.addMenu(moveMenu)

        return menu

    def _onEditClicked(self) -> None:
        from app.services.feature_service import featureService
        from app.view.dialogs.edit_task import LiveEditDialog
        LiveEditDialog(self._task, featureService.editCards(self._task, self.window()), self.window()).exec()
        self.refresh()

    def mouseReleaseEvent(self, e) -> None:
        super().mouseReleaseEvent(e)
        if e.button() == Qt.MouseButton.LeftButton:
            extend = bool(e.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            checked = True if extend or not self._selectionMode else not self.isChecked()
            self.selectionChanged.emit(checked, extend)

    def mouseDoubleClickEvent(self, e) -> None:
        super().mouseDoubleClickEvent(e)
        if e.button() == Qt.MouseButton.LeftButton:
            openFile(self._task.outputPath)

    def contextMenuEvent(self, e) -> None:
        menu = self.buildContextMenu()
        menu.exec(e.globalPos())
        e.accept()

    def paintEvent(self, e) -> None:
        if self._selectionMode and self.isChecked():
            painter = QPainter(self)
            painter.setRenderHints(QPainter.RenderHint.Antialiasing)
            r = self.borderRadius
            painter.setPen(QPen(themeColor(), 2))
            painter.setBrush(QColor(255, 255, 255, 15) if isDarkTheme() else QColor(0, 0, 0, 8))
            painter.drawRoundedRect(self.rect().adjusted(2, 2, -2, -2), r, r)
        super().paintEvent(e)


class UniversalTaskCard(TaskCard):

    def __init__(self, task: Task, parent=None):
        super().__init__(task, parent)
        self.setFixedHeight(self.ROW_HEIGHT)
        self._lastStatus: TaskStatus | None = None
        self._hashDigest: str = ""

        self.iconLabel = ImageLabel(self)
        self.nameLabel = IconStrongBodyLabel(task.name, self)
        self.speedLabel = IconBodyLabel("", FluentIcon.SPEED_HIGH, self)
        self.etaLabel = IconBodyLabel("", FluentIcon.STOP_WATCH, self)
        self.sizeLabel = IconBodyLabel("", FluentIcon.LIBRARY, self)
        self.statusLabel = IconBodyLabel("", FluentIcon.INFO, self)
        self.toggleButton = PrimaryToolButton(FluentIcon.PAUSE, self)
        self.verifyHashButton = ToolButton(FluentIcon.FINGERPRINT, self)
        self.openFileButton = ToolButton(FluentIcon.LINK, self)
        self.openFolderButton = ToolButton(FluentIcon.FOLDER, self)
        self.deleteButton = TransparentToolButton(FluentIcon.CLOSE, self)
        self.statusLabel.hide()
        self.progressBar = self._buildProgressBar()

        self._initWidget()
        self._initLayout()
        self._bind()
        self._refreshIcon()
        self._refreshCategoryIcon()

    def _buildProgressBar(self) -> QWidget:
        if self._task.fileSize in {SpecialFileSize.UNKNOWN, SpecialFileSize.NOT_SUPPORTED}:
            return IndeterminateProgressBar(self)
        bar = ProgressBar(self)
        bar.setCustomBackgroundColor(QColor(0, 0, 0, 0), QColor(0, 0, 0, 0))
        return bar

    def _initWidget(self) -> None:
        from PySide6.QtWidgets import QSizePolicy
        self.iconLabel.setFixedSize(48, 48)
        self.nameLabel.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        for btn, tip in (
            (self.verifyHashButton, self.tr("校验文件哈希")),
            (self.openFileButton, self.tr("打开文件")),
            (self.openFolderButton, self.tr("打开文件夹")),
        ):
            btn.setToolTip(tip)
            btn.installEventFilter(ToolTipFilter(btn))

    def _initLayout(self) -> None:
        infoLayout = QHBoxLayout()
        infoLayout.addWidget(self.speedLabel)
        infoLayout.addWidget(self.etaLabel)
        infoLayout.addWidget(self.sizeLabel)
        infoLayout.addWidget(self.statusLabel)
        infoLayout.addStretch()

        contentLayout = QVBoxLayout()
        contentLayout.setContentsMargins(2, 8, 2, 8)
        contentLayout.addWidget(self.nameLabel)
        contentLayout.addLayout(infoLayout)

        self.hBoxLayout = QHBoxLayout(self)
        self.hBoxLayout.setContentsMargins(12, 0, 12, 0)
        self.hBoxLayout.addWidget(self.checkBox)
        self.hBoxLayout.addWidget(self.iconLabel)
        self.hBoxLayout.addLayout(contentLayout, 1)
        self.hBoxLayout.addWidget(self.toggleButton)
        self.hBoxLayout.addWidget(self.verifyHashButton)
        self.hBoxLayout.addWidget(self.openFileButton)
        self.hBoxLayout.addWidget(self.openFolderButton)
        self.hBoxLayout.addWidget(self.deleteButton)

    def _bind(self) -> None:
        self.toggleButton.clicked.connect(self._onToggleClicked)
        self.verifyHashButton.clicked.connect(self._onVerifyHashClicked)
        self.openFileButton.clicked.connect(lambda: openFile(self._task.outputPath))
        self.openFolderButton.clicked.connect(lambda: revealInFolder(self._task.outputPath))
        self.deleteButton.clicked.connect(self._onDeleteClicked)

        from app.services.category_service import categoryService
        cfg.isCategoryEnabled.valueChanged.connect(self._refreshCategoryIcon)
        categoryService.categoriesChanged.connect(self._refreshCategoryIcon)

    def refresh(self, force: bool = False) -> None:
        if not force and self._lastStatus == self._task.status and self._task.status != TaskStatus.RUNNING:
            return

        self._fileMissing = False
        task = self._task
        progress, speed, receivedBytes = task.currentSnapshot()

        self.progressBar.setValue(int(progress))

        if task.fileSize > 0:
            self.sizeLabel.setText(f"{toReadableSize(receivedBytes)}/{toReadableSize(task.fileSize)}")
        else:
            self.sizeLabel.setText(f"{toReadableSize(receivedBytes)}/--")

        if task.status == TaskStatus.RUNNING:
            self.progressBar.setError(False)
            if self.statusLabel.isVisible():
                self.statusLabel.hide()
                self.progressBar.show()
                self.speedLabel.show()
                self.etaLabel.show()
                self.sizeLabel.show()
            self.speedLabel.setText(f"{toReadableSize(speed)}/s")
            if task.fileSize > 0 and speed > 0:
                self.etaLabel.setText(toReadableTime(int((task.fileSize - receivedBytes) / speed)))
            else:
                self.etaLabel.setText("--")

        elif task.status == TaskStatus.COMPLETED:
            self.progressBar.pause()
            self.progressBar.hide()
            if task.fileSize > 0:
                self.sizeLabel.setText(toReadableSize(task.fileSize))
            else:
                self.sizeLabel.hide()
            self._fileMissing = task.hasOutputFile and not Path(task.outputPath).exists()
            if self._fileMissing:
                statusText = self.tr("文件不存在")
            elif task.completedAt:
                from datetime import datetime
                statusText = self.tr("完成于 {}").format(
                    datetime.fromtimestamp(task.completedAt).strftime("%Y-%m-%d %H:%M:%S"))
            else:
                statusText = self.tr("任务已经完成")
            self._showStatus(statusText)
            if self._fileMissing:
                self.statusLabel.setTextColor(QColor(200, 160, 80), QColor(200, 170, 100))
            self.nameLabel.setText(task.name)
            self._refreshIcon()

        elif task.status == TaskStatus.FAILED:
            self.progressBar.setError(True)
            error = task.lastError
            if error:
                from PySide6.QtCore import QCoreApplication
                text = QCoreApplication.translate("TaskErrors", error.message)
                self._showStatus(text.format_map(error.params) if error.params else text)
            else:
                self._showStatus(self.tr("下载过程中发生错误，请稍后重试"))

        else:
            self.progressBar.setError(False)
            self.progressBar.pause()
            if task.status == TaskStatus.PAUSED:
                self._showStatus(self.tr("任务已经暂停"))
            elif task.status == TaskStatus.WAITING:
                self._showStatus(self.tr("任务正在等待"))

        self._refreshButtons()
        self._lastStatus = task.status

    def _showStatus(self, text: str) -> None:
        self.speedLabel.hide()
        self.etaLabel.hide()
        self.statusLabel.setTextColor()
        self.statusLabel.setText(text)
        self.statusLabel.show()

    def _refreshIcon(self) -> None:
        from PySide6.QtCore import QFileInfo
        from PySide6.QtWidgets import QFileIconProvider
        self.iconLabel.setPixmap(QFileIconProvider().icon(QFileInfo(self._task.outputPath)).pixmap(48, 48))
        self.iconLabel.setFixedSize(48, 48)

    def _refreshCategoryIcon(self) -> None:
        if not cfg.isCategoryEnabled.value or not self._task.category:
            self.nameLabel.setIcon(None)
            return
        from app.services.category_service import categoryService
        category = categoryService.categoryById(self._task.category)
        if category is None:
            self.nameLabel.setIcon(None)
            return
        self.nameLabel.setIcon(category.toIcon())

    def _refreshButtons(self) -> None:
        if self._task.status == TaskStatus.RUNNING:
            self.toggleButton.setIcon(FluentIcon.PAUSE)
            self.toggleButton.setEnabled(self._task.canPause)
        elif self._task.status == TaskStatus.COMPLETED:
            self.toggleButton.setIcon(FluentIcon.PLAY)
            self.toggleButton.setEnabled(False)
        else:
            self.toggleButton.setIcon(FluentIcon.PLAY)
            self.toggleButton.setEnabled(True)

        completed = self._task.status == TaskStatus.COMPLETED
        self.verifyHashButton.setVisible(completed)
        self.verifyHashButton.setEnabled(completed and not self._fileMissing)
        self.openFileButton.setEnabled(not completed or not self._fileMissing)

    def _onToggleClicked(self) -> None:
        if self._task.status == TaskStatus.RUNNING:
            taskService.pause(self._task)
        else:
            taskService.start(self._task)
        self.refresh()

    def _onDeleteClicked(self) -> None:
        from qfluentwidgets import MessageBox
        dialog = MessageBox(self.tr("删除任务"), self.tr("确定要删除这个下载任务吗？"), self.window())
        deleteFiles = CheckBox(self.tr("同时删除已下载的文件"))
        deleteFiles.setChecked(cfg.shouldDeleteFilesOnRemove.value)
        dialog.textLayout.addWidget(deleteFiles)
        if dialog.exec():
            cfg.set(cfg.shouldDeleteFilesOnRemove, deleteFiles.isChecked())
            taskService.delete(self._task, deleteFiles.isChecked())

    def _onVerifyHashClicked(self) -> None:
        if not Path(self._task.outputPath).is_file():
            self._showStatus(self.tr("文件不存在，无法校验"))
            return
        from app.view.dialogs.file_hash import FileHashDialog
        dialog = FileHashDialog(self._task.outputPath, self.window())
        dialog.hashReady.connect(self._onHashReady)
        dialog.exec()
        dialog.deleteLater()

    def _onHashReady(self, algorithm: str, digest: str) -> None:
        self._hashDigest = f"{algorithm}: {digest}"
        self._showStatus(self._hashDigest)

    def buildContextMenu(self) -> RoundMenu:
        menu = super().buildContextMenu()
        if self._hashDigest:
            copyHash = Action(FluentIcon.FINGERPRINT, self.tr("复制校验值"), self)
            copyHash.triggered.connect(lambda: QApplication.clipboard().setText(self._hashDigest))
            menu.insertAction(menu.actions()[1], copyHash)
        return menu

    def resizeEvent(self, e) -> None:
        self.progressBar.setGeometry(4, self.height() - 4, self.width() - 8, 4)
        super().resizeEvent(e)
