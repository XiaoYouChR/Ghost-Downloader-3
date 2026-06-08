"""移动端任务卡 —— 把「窄屏呈现」抽成 mixin 叠在桌面特性卡之上。

抽 mixin 而非具体子类: 卡类由 featureService 按任务类型分发(HttpTaskCard 分段进度条、
FtpTaskCard 选文件按钮…), 移动端不能只用一种卡否则丢这些特性。MobileTaskPage._mountCard
取到桌面卡类后动态合成 (MobileCardMixin, 桌面卡类), 既得窄屏布局又留特性。
"""

from PySide6.QtCore import Qt, QTimer
from qfluentwidgets import Action, CardWidget, FluentIcon, TransparentToolButton

from app.bases.models import TaskStatus
from app.supports.android import openFile, openFolder

LONG_PRESS_MS = 450


class MobileCardMixin:
    """窄屏呈现 mixin: 只留 暂停/继续 + ⋮(overflow), 其余动作收进 ⋮ 菜单; tap=打开文件、长按=进多选。"""

    def initLayout(self):
        self.overflowButton = TransparentToolButton(FluentIcon.MORE, self)
        # 改走 ⋮ 菜单, 不入布局; 不 hide 会因仍是子控件而停在 (0,0) 露出
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
        self.verifyHashButton.hide()  # 完成态基类会 setVisible 它; 校验入口已移到 ⋮ 菜单

    def _renderTaskState(self):
        super()._renderTaskState()
        # 剩余时间在窄屏挤掉进度文本, 移动端只留 速度 + 进度; 基类会在暂停→运行时重新 show 它, 故在此兜底
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
        """子类钩子: 在 ⋮ 菜单的「打开文件」前追加特性专属动作(默认无)。"""

    def _showOverflowMenu(self):
        menu = self.createContextMenu()  # 复制链接/编辑/重下/移动分类
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
        # 跳过 TaskCard.mouseReleaseEvent 的「单击即选中」桌面语义，保留 CardWidget 的按压动画
        CardWidget.mouseReleaseEvent(self, e)
        self._longPressTimer.stop()
        if e.button() != Qt.MouseButton.LeftButton or self._longPressed:
            return
        if self.isSelectionMode:
            self.selectionChanged.emit(not self.isChecked(), False)
        else:
            openFile(self.task.outputFolder)

    def mouseDoubleClickEvent(self, e):
        pass  # 移动端无双击；屏蔽桌面的双击打开文件夹

    def _onLongPress(self):
        self._longPressed = True
        if self.isSelectionMode:
            self.selectionChanged.emit(not self.isChecked(), False)
        else:
            self.selectionChanged.emit(True, False)  # 进入多选并选中本卡


class MobileFtpMixin:
    """FTP 卡的移动端特化: 把桌面的「选择文件」按钮收进 ⋮ 菜单(窄屏布局里它落在边缘)。"""

    def __init__(self, task, parent=None):
        super().__init__(task, parent)
        self.selectFilesButton.hide()

    def refresh(self):
        super().refresh()
        # FtpTaskCard.refresh 会按 countAll 重新 show 选文件/校验按钮; 移动端它们都在 ⋮ 菜单, 兜底隐藏
        self.selectFilesButton.hide()
        self.verifyHashButton.hide()

    def _appendOverflowActions(self, menu):
        if self.task.countAll <= 1:
            return
        selectFilesAction = Action(FluentIcon.LIBRARY, self.tr("选择文件"), self)
        selectFilesAction.setEnabled(self.task.status != TaskStatus.RUNNING)
        selectFilesAction.triggered.connect(self._onSelectFilesClicked)
        menu.addAction(selectFilesAction)
