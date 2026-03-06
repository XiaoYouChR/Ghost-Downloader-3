from enum import IntEnum

from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QPainter, QColor, QActionGroup
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QGraphicsDropShadowEffect
from loguru import logger
from qfluentwidgets import ScrollArea, PrimaryPushButton, FluentIcon, PushButton, \
    SearchLineEdit, ToolButton, ToggleToolButton, ToolTipFilter, Action, \
    CommandBarView, isDarkTheme, IconWidget, CaptionLabel, CheckableMenu, MenuIndicatorType, \
    DropDownToolButton

from app.services.feature_service import featureService
from app.bases.models import TaskStatus
from app.supports.config import cfg
from app.supports.recorder import taskRecorder
from app.supports.utils import getReadableSize
from app.view.components.cards import TaskCard
from app.view.components.dialogs import DeleteTaskDialog
from app.view.components.labels import IconBodyLabel


class TaskCommandBarView(CommandBarView):

    def __init__(self, parent=None):
        super().__init__(parent)
        # self.openAction = Action(FluentIcon.FOLDER, self.tr("打开文件夹"), self)
        self.redownloadAction = Action(FluentIcon.UPDATE, self.tr("重新下载"), self)
        self.deleteAction = Action(FluentIcon.DELETE, self.tr("删除"), self)
        self.selectAllAction = Action(FluentIcon.CLEAR_SELECTION, self.tr("全选"), self)
        self.cancelAction = Action(FluentIcon.CLEAR_SELECTION, self.tr("取消全选"), self)

        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.setIconSize(QSize(18, 18))
        # self.addAction(self.openAction)
        self.addAction(self.redownloadAction)
        self.addAction(self.deleteAction)
        self.addSeparator()
        self.addAction(self.selectAllAction)
        self.addAction(self.cancelAction)
        self.resizeToSuitableWidth()
        self.setShadowEffect()

    def setShadowEffect(self, blurRadius=35, offset=(0, 8)):
        """ add shadow to dialog """
        color = QColor(0, 0, 0, 80 if isDarkTheme() else 30)
        self.shadowEffect = QGraphicsDropShadowEffect(self)
        self.shadowEffect.setBlurRadius(blurRadius)
        self.shadowEffect.setOffset(*offset)
        self.shadowEffect.setColor(color)
        self.setGraphicsEffect(None)
        self.setGraphicsEffect(self.shadowEffect)


class EmptyStatusWidget(QWidget):

    def __init__(self, icon, text, parent=None):
        super().__init__(parent=parent)
        self.iconWidget = IconWidget(icon)
        self.label = CaptionLabel(text)
        self.vBoxLayout = QVBoxLayout(self)
        self.borderRadius = 10

        self.initWidget()

    def initWidget(self):
        self.iconWidget.setFixedSize(64, 64)

        self.label.setTextColor(QColor(96, 96, 96), QColor(216, 216, 216))
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.vBoxLayout.setSpacing(10)
        self.vBoxLayout.setContentsMargins(16, 20, 16, 20)
        self.vBoxLayout.addWidget(self.iconWidget, 0, Qt.AlignmentFlag.AlignHCenter)
        self.vBoxLayout.addWidget(self.label, 0, Qt.AlignmentFlag.AlignHCenter)

    def setIcon(self, icon):
        self.iconWidget.setIcon(icon)

    def setText(self, text):
        self.label.setText(text)

    @property
    def backgroundColor(self):
        return QColor(255, 255, 255, 13 if isDarkTheme() else 200)

    def paintEvent(self, e):
        painter = QPainter(self)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing)
        painter.setBrush(self.backgroundColor)
        painter.setPen(Qt.PenStyle.NoPen)

        r = self.borderRadius
        painter.drawRoundedRect(self.rect(), r, r)


class FilterMode(IntEnum):
    ALL = 0
    ACTIVE = 1
    COMPLETE = 2


class SortField(IntEnum):
    TIME = 0
    NAME = 1


class TaskPage(ScrollArea):

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.cards: list[TaskCard] = []
        self.selectionCount = 0
        self.isSelectionMode = False
        self.searchKeyword = ""
        self.filterMode: FilterMode = FilterMode.ALL
        self.sortField: SortField = SortField.TIME
        self.sortReverse = True

        self.container = QWidget(self)
        self.vBoxLayout = QVBoxLayout(self)
        self.viewLayout = QVBoxLayout(self.container)
        # init ToolBar
        self.toolBar = QWidget(self)
        self.toolBarLayout = QHBoxLayout(self.toolBar)
        self.allStartButton = PrimaryPushButton(FluentIcon.PLAY, self.tr("全部开始"), self)
        self.allPauseButton = PushButton(FluentIcon.PAUSE, self.tr("全部暂停"), self)
        self.selectButton = ToolButton(FluentIcon.CLEAR_SELECTION, self)
        self.planButton = ToggleToolButton(FluentIcon.DATE_TIME, self)
        self.rateLimitButton = ToggleToolButton(FluentIcon.SPEED_OFF, self)
        self.speedBadge = IconBodyLabel(self.tr("0.00KB/s"), FluentIcon.SPEED_HIGH, self)
        self.sortButton = DropDownToolButton(FluentIcon.LAYOUT, self)
        self.sortMenu = CheckableMenu(parent=self, indicatorType=MenuIndicatorType.RADIO)
        self.sortFieldActionGroup = QActionGroup(self)
        self.sortOrderActionGroup = QActionGroup(self)
        self.timeSortAction = Action(FluentIcon.DATE_TIME, self.tr('按时间排序'), self, checkable=True)
        self.nameSortAction = Action(FluentIcon.FONT, self.tr('按名称排序'), self, checkable=True)
        self.ascendingSortAction = Action(FluentIcon.UP, self.tr('顺序'), self, checkable=True)
        self.reverseSortAction = Action(FluentIcon.DOWN, self.tr('倒序'), self, checkable=True)
        self.filterButton = DropDownToolButton(FluentIcon.FILTER, self)
        self.filterMenu = CheckableMenu(parent=self, indicatorType=MenuIndicatorType.RADIO)
        self.filterActionGroup = QActionGroup(self)
        self.noFilterAction = Action(FluentIcon.FILTER, self.tr('全部任务'), self, checkable=True)
        self.activeFilterAction = Action(FluentIcon.DOWNLOAD, self.tr('活动任务'), self, checkable=True)
        self.completedFilterAction = Action(FluentIcon.TRAIN, self.tr('完成任务'), self, checkable=True)
        self.searchLineEdit = SearchLineEdit(self)
        # other widgets
        self.commandView = TaskCommandBarView(self)
        self.emptyStatusWidget = EmptyStatusWidget(FluentIcon.EMOJI_TAB_SYMBOLS, self.tr("暂无下载任务"), self)

        self.initWidget()
        self.initLayout()
        self.connectSignalToSlot()

        self.refreshTimer = QTimer(self, interval=1000)
        self.refreshTimer.timeout.connect(self.refresh)
        self.refreshTimer.start()

    def resumeMemorizedTasks(self):
        for task in taskRecorder.memorizedTasks.values():
            try:
                card = featureService.createTaskCard(task, self)
            except Exception as e:
                logger.error(f"无法恢复任务卡片 {task.taskId}: {repr(e)}")
                continue

            if task.status == TaskStatus.RUNNING:
                card.resumeTask()

            self.addCard(card)

    def refresh(self):
        for card in self.cards:
            card.refresh()

        self.speedBadge.setText(f"{getReadableSize(cfg.globalSpeed)}/s")
        cfg.resetGlobalSpeed()

        if self.filterMode != FilterMode.ALL:
            self.refreshCardVisibility()

    def addCard(self, card: TaskCard):
        card.deleted.connect(lambda: self.removeCard(card))
        card.checkedChanged.connect(self.onCardCheckedChanged)
        self.cards.append(card)
        self.viewLayout.addWidget(card)
        self.sortCards()
        self.refreshCardVisibility()

    def removeCard(self, card: TaskCard):
        taskRecorder.remove(card.task)
        if card not in self.cards:
            return

        self.cards.remove(card)
        self.viewLayout.removeWidget(card)
        card.deleteLater()
        self.refreshCardVisibility()

    def initWidget(self):
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setWidget(self.container)
        self.setObjectName("TaskPage")
        self.setWidgetResizable(True)
        self.enableTransparentBackground()
        self.setViewportMargins(0, 60, 0, 0)
        # Tool Bar
        self.sortFieldActionGroup.addAction(self.timeSortAction)
        self.sortFieldActionGroup.addAction(self.nameSortAction)
        self.sortOrderActionGroup.addAction(self.ascendingSortAction)
        self.sortOrderActionGroup.addAction(self.reverseSortAction)
        self.sortMenu.addAction(self.timeSortAction)
        self.sortMenu.addAction(self.nameSortAction)
        self.sortMenu.addSeparator()
        self.sortMenu.addAction(self.ascendingSortAction)
        self.sortMenu.addAction(self.reverseSortAction)
        self.sortButton.setMenu(self.sortMenu)

        self.filterActionGroup.addAction(self.noFilterAction)
        self.filterActionGroup.addAction(self.activeFilterAction)
        self.filterActionGroup.addAction(self.completedFilterAction)
        self.filterMenu.addAction(self.noFilterAction)
        self.filterMenu.addAction(self.activeFilterAction)
        self.filterMenu.addAction(self.completedFilterAction)
        self.filterButton.setMenu(self.filterMenu)

        self.selectButton.setToolTip(self.tr("选择任务"))
        self.selectButton.installEventFilter(ToolTipFilter(self.selectButton))
        self.planButton.setToolTip(self.tr("计划任务"))
        self.planButton.installEventFilter(ToolTipFilter(self.planButton))
        self.rateLimitButton.setToolTip(self.tr("限速"))
        self.rateLimitButton.installEventFilter(ToolTipFilter(self.rateLimitButton))
        # other widgets
        self.emptyStatusWidget.setMinimumWidth(200)
        self.emptyStatusWidget.adjustSize()
        self.emptyStatusWidget.hide()

        self.commandView.hide()

        self.searchLineEdit.setPlaceholderText(self.tr("搜索任务"))

        self.timeSortAction.setChecked(True)
        self.reverseSortAction.setChecked(True)
        self.noFilterAction.setChecked(True)

    def initLayout(self):
        self.vBoxLayout.setSpacing(20)
        self.vBoxLayout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.viewLayout.setContentsMargins(12, 0, 12, 12)
        self.viewLayout.setAlignment(Qt.AlignmentFlag.AlignTop)
        # Tool Bar
        self.vBoxLayout.addWidget(self.toolBar)
        self.toolBarLayout.setContentsMargins(0, 0, 0 ,0)
        self.toolBarLayout.addWidget(self.allStartButton)
        self.toolBarLayout.addWidget(self.allPauseButton)
        self.toolBarLayout.addWidget(self.selectButton)
        self.toolBarLayout.addWidget(self.planButton)
        self.toolBarLayout.addWidget(self.rateLimitButton)
        self.toolBarLayout.addSpacing(10)
        self.toolBarLayout.addWidget(self.speedBadge)
        self.toolBarLayout.addStretch(1)
        self.toolBarLayout.addWidget(self.sortButton)
        self.toolBarLayout.addWidget(self.filterButton)
        self.toolBarLayout.addWidget(self.searchLineEdit)
        self.searchLineEdit.setMinimumWidth(200)
        self.searchLineEdit.setMaximumWidth(300)

    def connectSignalToSlot(self):
        self.allStartButton.clicked.connect(self.startAllTasks)
        self.allPauseButton.clicked.connect(self.pauseAllTasks)
        self.selectButton.clicked.connect(lambda: self.setSelectionMode(not self.isSelectionMode))
        self.commandView.deleteAction.triggered.connect(self.onDeleteActionTriggered)
        self.commandView.selectAllAction.triggered.connect(self.selectAll)
        self.commandView.cancelAction.triggered.connect(lambda: self.setSelectionMode(False))
        self.timeSortAction.triggered.connect(lambda: self.setSortField(SortField.TIME))
        self.nameSortAction.triggered.connect(lambda: self.setSortField(SortField.NAME))
        self.ascendingSortAction.triggered.connect(lambda: self.setSortOrder(False))
        self.reverseSortAction.triggered.connect(lambda: self.setSortOrder(True))
        self.noFilterAction.triggered.connect(lambda: self.setFilterMode(FilterMode.ALL))
        self.activeFilterAction.triggered.connect(lambda: self.setFilterMode(FilterMode.ACTIVE))
        self.completedFilterAction.triggered.connect(lambda: self.setFilterMode(FilterMode.COMPLETE))
        self.searchLineEdit.textChanged.connect(self.onSearchTextChanged)
        self.searchLineEdit.searchSignal.connect(self.onSearchTextChanged)
        self.searchLineEdit.clearSignal.connect(lambda: self.onSearchTextChanged(""))

    def _getSortKey(self, card: TaskCard):
        if self.sortField == SortField.NAME:
            return str(getattr(card.task, "title", "")).lower()
        return getattr(card.task, "createdAt", 0)

    def sortCards(self):
        if len(self.cards) < 2:
            return

        self.cards.sort(key=self._getSortKey, reverse=self.sortReverse)

        for i, card in enumerate(self.cards):
            self.viewLayout.insertWidget(i, card)

    def _setEmptyStatusText(self, text: str):
        self.emptyStatusWidget.setText(text)
        self.emptyStatusWidget.adjustSize()
        self.emptyStatusWidget.move(
            (self.width() - self.emptyStatusWidget.width()) >> 1,
            (self.height() - self.emptyStatusWidget.height()) >> 1,
        )

    def _matchSearch(self, card: TaskCard) -> bool:
        if not self.searchKeyword:
            return True

        query = self.searchKeyword
        return query in str(card.task.title).strip().lower()

    def _matchFilter(self, card: TaskCard) -> bool:
        if self.filterMode == FilterMode.ALL:
            return True

        if self.filterMode == FilterMode.ACTIVE:
            return not card.task.status == TaskStatus.COMPLETED
        if self.filterMode == FilterMode.COMPLETE:
            return card.task.status == TaskStatus.COMPLETED

        return True

    def _matchCard(self, card: TaskCard) -> bool:
        return self._matchSearch(card) and self._matchFilter(card)

    def _getEmptyTextForFilter(self) -> str:
        if self.searchKeyword and self.filterMode != FilterMode.ALL:
            return self.tr("没有匹配筛选条件的任务")
        if self.searchKeyword:
            return self.tr("没有匹配的任务")
        if self.filterMode == FilterMode.ACTIVE:
            return self.tr("暂无活动任务")
        if self.filterMode == FilterMode.COMPLETE:
            return self.tr("暂无完成任务")

        return self.tr("暂无下载任务")

    def refreshCardVisibility(self):
        if not self.cards:
            self._setEmptyStatusText(self.tr("暂无下载任务"))
            self.emptyStatusWidget.show()
            return

        visibleCount = 0
        for card in self.cards:
            visible = self._matchCard(card)
            card.setVisible(visible)
            if visible:
                visibleCount += 1

        if visibleCount > 0:
            self.emptyStatusWidget.hide()
            return

        self._setEmptyStatusText(self._getEmptyTextForFilter())
        self.emptyStatusWidget.show()

    def onSearchTextChanged(self, text: str):
        self.searchKeyword = text.strip().lower()
        self.refreshCardVisibility()

    def setFilterMode(self, mode: FilterMode):
        if self.filterMode == mode:
            return

        self.filterMode = mode
        self.refreshCardVisibility()

    def setSortField(self, field: SortField):
        if self.sortField == field:
            return

        self.sortField = field
        self.sortCards()

    def setSortOrder(self, reverse: bool):
        if self.sortReverse == reverse:
            return

        self.sortReverse = reverse
        self.sortCards()

    def startAllTasks(self):
        for card in self.cards:
            status = card.task.status
            if status in {TaskStatus.WAITING, TaskStatus.PAUSED, TaskStatus.FAILED}:
                card.resumeTask()

    def pauseAllTasks(self):
        for card in self.cards:
            if card.task.status == TaskStatus.RUNNING:
                card.pauseTask()

    def selectAll(self):
        for card in self.cards:
            card.setChecked(True)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        width = self.width()
        height = self.height()
        self.commandView.move((width - self.commandView.width()) >> 1, height - self.commandView.sizeHint().height() - 20)
        self.emptyStatusWidget.move((width - self.emptyStatusWidget.width()) >> 1, (height - self.emptyStatusWidget.height()) >> 1)

    def onCardCheckedChanged(self, checked: bool):
        if checked:
            self.selectionCount += 1
            self.setSelectionMode(True)
        else:
            self.selectionCount -= 1
            if self.selectionCount == 0:
                self.setSelectionMode(False)

    def onDeleteActionTriggered(self):
        w = DeleteTaskDialog(self.window(), deleteOnClose=False)
        w.deleteFileCheckBox.setChecked(False)

        if w.exec():
            for card in self.cards.copy():
                if card.isChecked():
                    card.removeTask(w.deleteFileCheckBox.isChecked())

        w.deleteLater()

    def setSelectionMode(self, enter: bool):
        if self.isSelectionMode == enter:
            return

        self.isSelectionMode = enter

        for card in self.cards:
            card.setSelectionMode(enter)

        if enter:
            self.commandView.setVisible(True)
            self.commandView.raise_()
        else:
            self.commandView.setVisible(False)
            self.selectionCount = 0
