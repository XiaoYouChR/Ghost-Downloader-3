from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from qfluentwidgets import Action, CardWidget, FluentIcon, TransparentToolButton

from app.models.task import TaskStatus
from app.platform.android import openFile, openFolder

LONG_PRESS_MS = 450


class MobileTaskCardBase:
    """窄屏触屏改造: 操作按钮收进 ⋮ 溢出菜单, 长按多选, 轻触打开。"""

    def setupMobile(self) -> None:
        self.overflowButton = TransparentToolButton(FluentIcon.MORE, self)
        for button in (self.verifyHashButton, self.openFileButton, self.openFolderButton, self.deleteButton):
            button.hide()
        self.hBoxLayout.addWidget(self.overflowButton)
        self.overflowButton.clicked.connect(self._showOverflowMenu)

        self._longPressed = False
        self._longPressTimer = QTimer(self, singleShot=True)
        self._longPressTimer.setInterval(LONG_PRESS_MS)
        self._longPressTimer.timeout.connect(self._onLongPress)

    def _refreshButtons(self) -> None:
        super()._refreshButtons()
        self.verifyHashButton.hide()

    def _showOverflowMenu(self) -> None:
        menu = self.buildContextMenu()
        menu.addSeparator()

        openFileAction = Action(FluentIcon.LINK, self.tr("打开文件"), self)
        openFileAction.triggered.connect(lambda: openFile(self.task.outputPath))
        menu.addAction(openFileAction)

        openFolderAction = Action(FluentIcon.FOLDER, self.tr("打开文件夹"), self)
        openFolderAction.triggered.connect(lambda: openFolder(self.task.outputFolder))
        menu.addAction(openFolderAction)

        if self.task.status == TaskStatus.COMPLETED:
            verifyAction = Action(FluentIcon.FINGERPRINT, self.tr("校验哈希"), self)
            verifyAction.triggered.connect(self.verifyHashButton.click)
            menu.addAction(verifyAction)

        menu.addSeparator()
        deleteAction = Action(FluentIcon.DELETE, self.tr("删除"), self)
        deleteAction.triggered.connect(self.deleteButton.click)
        menu.addAction(deleteAction)

        menu.exec(self.overflowButton.mapToGlobal(self.overflowButton.rect().bottomLeft()))

    def mousePressEvent(self, e) -> None:
        super().mousePressEvent(e)
        if e.button() == Qt.MouseButton.LeftButton:
            self._longPressed = False
            self._longPressTimer.start()

    def mouseReleaseEvent(self, e) -> None:
        CardWidget.mouseReleaseEvent(self, e)  # 跳过桌面卡的「松手即选中」, 改走下面触屏语义
        self._longPressTimer.stop()
        if e.button() != Qt.MouseButton.LeftButton or self._longPressed:
            return
        if self._selectionMode:
            self.selectionChanged.emit(not self.isChecked(), False)
        else:
            openFile(self.task.outputPath)

    def mouseDoubleClickEvent(self, e) -> None:
        pass

    def _onLongPress(self) -> None:
        self._longPressed = True
        if self._selectionMode:
            self.selectionChanged.emit(not self.isChecked(), False)
        else:
            self.selectionChanged.emit(True, False)
