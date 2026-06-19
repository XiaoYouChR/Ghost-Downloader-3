from PySide6.QtCore import Qt, QTimer
from qfluentwidgets import Action, CardWidget, FluentIcon, TransparentToolButton

from app.bases.models import TaskStatus
from app.supports.android import openFile, openFolder

LONG_PRESS_MS = 450

class MobileTaskCardBase:
    def initLayout(self):
        self.overflowButton = TransparentToolButton(FluentIcon.MORE, self)

        for widget in (self.verifyHashButton, self.openFileButton, self.openFolderButton, self.cancelButton):
            widget.hide()

        self.hBoxLayout.addWidget(self.checkBox)
        self.hBoxLayout.addWidget(self.iconLabel)

        self.infoVBoxLayout.addWidget(self.filenameLabel)
        self.infoLayout.addWidget(self.speedLabel)
        self.infoLayout.addWidget(self.progressLabel)
        self.infoLayout.addWidget(self.infoLabel)
        self.infoLayout.addStretch()
        self.infoVBoxLayout.addLayout(self.infoLayout)
        self.infoVBoxLayout.setContentsMargins(2, 8, 2, 8)
        self.hBoxLayout.addLayout(self.infoVBoxLayout, 1)

        self.hBoxLayout.addWidget(self.toggleRunningStatusButton)
        self.hBoxLayout.addWidget(self.overflowButton)
        self.hBoxLayout.setContentsMargins(12, 0, 12, 0)

    def refreshToggleButton(self):
        super().refreshToggleButton()
        self.verifyHashButton.hide()

    def _renderTaskState(self):
        super()._renderTaskState()
        self.leftTimeLabel.hide()

    def connectSignalToSlot(self):
        super().connectSignalToSlot()
        self.overflowButton.clicked.connect(self._showOverflowMenu)
        self._longPressed = False
        self._longPressTimer = QTimer(self)
        self._longPressTimer.setSingleShot(True)
        self._longPressTimer.setInterval(LONG_PRESS_MS)
        self._longPressTimer.timeout.connect(self._onLongPress)

    def _appendOverflowActions(self, menu):
        pass

    def _showOverflowMenu(self):
        menu = self.createContextMenu()
        menu.addSeparator()
        self._appendOverflowActions(menu)

        openFileAction = Action(FluentIcon.LINK, self.tr("打开文件"), self)
        openFileAction.triggered.connect(lambda: openFile(self.task.outputFolder))
        menu.addAction(openFileAction)

        openFolderAction = Action(FluentIcon.FOLDER, self.tr("打开文件夹"), self)
        openFolderAction.triggered.connect(lambda: openFolder(self.task.outputFolder))
        menu.addAction(openFolderAction)

        if self.task.status == TaskStatus.COMPLETED:
            verifyAction = Action(FluentIcon.FINGERPRINT, self.tr("校验哈希"), self)
            verifyAction.triggered.connect(self._onVerifyHashButtonClicked)
            menu.addAction(verifyAction)

        menu.addSeparator()
        deleteAction = Action(FluentIcon.DELETE, self.tr("删除"), self)
        deleteAction.triggered.connect(self._onDeleteButtonClicked)
        menu.addAction(deleteAction)

        menu.exec(self.overflowButton.mapToGlobal(self.overflowButton.rect().bottomLeft()))

    def mousePressEvent(self, e):
        super().mousePressEvent(e)
        if e.button() == Qt.MouseButton.LeftButton:
            self._longPressed = False
            self._longPressTimer.start()

    def mouseReleaseEvent(self, e):
        CardWidget.mouseReleaseEvent(self, e)
        self._longPressTimer.stop()
        if e.button() != Qt.MouseButton.LeftButton or self._longPressed:
            return
        if self.isSelectionMode:
            self.selectionChanged.emit(not self.isChecked(), False)
        else:
            openFile(self.task.outputFolder)

    def mouseDoubleClickEvent(self, e):
        pass

    def _onLongPress(self):
        self._longPressed = True
        if self.isSelectionMode:
            self.selectionChanged.emit(not self.isChecked(), False)
        else:
            self.selectionChanged.emit(True, False)

class MobileFtpTaskCardBase:
    def __init__(self, task, parent=None):
        super().__init__(task, parent)
        self.selectFilesButton.hide()

    def refresh(self):
        super().refresh()

        self.selectFilesButton.hide()
        self.verifyHashButton.hide()

    def _appendOverflowActions(self, menu):
        if self.task.countAll <= 1:
            return
        selectFilesAction = Action(FluentIcon.LIBRARY, self.tr("选择文件"), self)
        selectFilesAction.setEnabled(self.task.status != TaskStatus.RUNNING)
        selectFilesAction.triggered.connect(self._onSelectFilesClicked)
        menu.addAction(selectFilesAction)
