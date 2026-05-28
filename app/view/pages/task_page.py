from enum import IntEnum
from sys import platform

from typing import Callable

from PySide6.QtCore import Qt, QSize, QTimer, Slot
from PySide6.QtGui import QPainter, QColor, QActionGroup, QCursor
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QGraphicsDropShadowEffect, QDialog
from loguru import logger
from qfluentwidgets import ScrollArea, PrimaryPushButton, FluentIcon, PushButton, \
    SearchLineEdit, ToolButton, ToggleToolButton, ToolTipFilter, Action, \
    CommandBarView, isDarkTheme, IconWidget, CaptionLabel, CheckableMenu, MenuIndicatorType, \
    DropDownToolButton, RoundMenu

from app.bases.models import Task, TaskStatus
from app.services.category_service import UNCATEGORIZED_ID, categoryService
from app.services.core_service import coreService
from app.services.feature_service import featureService
from app.services.task_service import taskService
from app.supports.config import cfg
from app.supports.utils import toReadableSize, openFile
from app.view.components.cards import TaskCard
from app.view.components.dialogs import DeleteTaskDialog, PlanTaskDialog
from app.view.components.labels import IconBodyLabel


ROW_HEIGHT = 60
ROW_SPACING = 8
SIDE_PADDING = 12
BOTTOM_PADDING = 12
BUFFER_ROWS = 5


class TaskCommandBarView(CommandBarView):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.redownloadAction = Action(FluentIcon.UPDATE, self.tr("重新下载"), self)
        self.deleteAction = Action(FluentIcon.DELETE, self.tr("删除"), self)
        self.moveCategoryAction = Action(FluentIcon.TAG, self.tr("移动到分类"), self)
        self.selectAllAction = Action(FluentIcon.CLEAR_SELECTION, self.tr("全选"), self)
        self.invertSelectAction = Action(FluentIcon.CUT, self.tr("反选"), self)
        self.cancelAction = Action(FluentIcon.CLEAR_SELECTION, self.tr("取消全选"), self)

        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.setIconSize(QSize(18, 18))
        self.addAction(self.redownloadAction)
        self.addAction(self.deleteAction)
        self.addAction(self.moveCategoryAction)
        self.addSeparator()
        self.addAction(self.selectAllAction)
        self.addAction(self.invertSelectAction)
        self.addAction(self.cancelAction)
        self.resizeToSuitableWidth()
        self.setShadowEffect()

        self.moveCategoryAction.setVisible(cfg.enableCategory.value)
        cfg.enableCategory.valueChanged.connect(
            lambda value: self.moveCategoryAction.setVisible(bool(value))
        )

    def setShadowEffect(self, blurRadius=35, offset=(0, 8)):
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


class TaskListView(QWidget):
    """Tall canvas hosting absolutely-positioned TaskCard children.

    Reports a sizeHint of `rowCount × (rowH + spacing)` so the surrounding
    ScrollArea knows how much vertical room the logical list needs, but does
    not own a layout — TaskPage positions visible cards via setGeometry.
    """

    def __init__(self, parent: "TaskPage", onResize: Callable[[], None]):
        super().__init__(parent)
        self._rowCount = 0
        self._onResize = onResize

    def setRowCount(self, count: int):
        if self._rowCount == count:
            return
        self._rowCount = count
        self.updateGeometry()

    def rowCount(self) -> int:
        return self._rowCount

    def rowTop(self, index: int) -> int:
        return index * (ROW_HEIGHT + ROW_SPACING)

    def rowAt(self, y: int) -> int:
        if y <= 0:
            return 0
        return y // (ROW_HEIGHT + ROW_SPACING)

    def sizeHint(self) -> QSize:
        if self._rowCount == 0:
            return QSize(0, 0)
        height = self._rowCount * ROW_HEIGHT + (self._rowCount - 1) * ROW_SPACING + BOTTOM_PADDING
        return QSize(0, height)

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._onResize()


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
        self.displayOrder: list[Task] = []
        self.mountedCards: dict[str, TaskCard] = {}
        self.selectedIds: set[str] = set()
        self.selectionAnchorTaskId: str | None = None
        self.isSelectionMode = False
        self.searchKeyword = ""
        self.filterMode: FilterMode = FilterMode.ALL
        self.categoryFilterId: str | None = None
        self.sortField: SortField = SortField.TIME
        self.sortReverse = True
        self.planAction: int | None = None
        self.planFilePath = ""

        self.container = TaskListView(self, self._refreshViewport)
        self.vBoxLayout = QVBoxLayout(self)
        # tool bar
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
        self.categoryFilterButton = DropDownToolButton(FluentIcon.TAG, self)
        self.categoryFilterMenu = CheckableMenu(parent=self, indicatorType=MenuIndicatorType.RADIO)
        self.categoryFilterActionGroup = QActionGroup(self)
        self.searchLineEdit = SearchLineEdit(self)
        # other widgets
        self.commandView = TaskCommandBarView(self)
        self.emptyStatusWidget = EmptyStatusWidget(FluentIcon.EMOJI_TAB_SYMBOLS, self.tr("暂无下载任务"), self)
        self.refreshTimer = QTimer(self, interval=1000)

        self._initWidget()
        self._initLayout()
        self._bind()

    def _initWidget(self):
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setWidget(self.container)
        self.setObjectName("TaskPage")
        self.setWidgetResizable(True)
        self.enableTransparentBackground()
        self.setViewportMargins(0, 60, 0, 0)

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
        self.rateLimitButton.setChecked(cfg.get(cfg.enableSpeedLimitation))

        self.filterActionGroup.addAction(self.noFilterAction)
        self.filterActionGroup.addAction(self.activeFilterAction)
        self.filterActionGroup.addAction(self.completedFilterAction)
        self.filterMenu.addAction(self.noFilterAction)
        self.filterMenu.addAction(self.activeFilterAction)
        self.filterMenu.addAction(self.completedFilterAction)
        self.filterButton.setMenu(self.filterMenu)

        self.categoryFilterButton.setMenu(self.categoryFilterMenu)
        self.categoryFilterButton.setToolTip(self.tr("按分类筛选"))
        self.categoryFilterButton.installEventFilter(ToolTipFilter(self.categoryFilterButton))
        self.categoryFilterButton.setVisible(cfg.enableCategory.value)
        self._rebuildCategoryFilterMenu()

        self.selectButton.setToolTip(self.tr("选择任务"))
        self.selectButton.installEventFilter(ToolTipFilter(self.selectButton))
        self.planButton.setToolTip(self.tr("计划任务"))
        self.planButton.installEventFilter(ToolTipFilter(self.planButton))
        self.rateLimitButton.setToolTip(self.tr("限速"))
        self.rateLimitButton.installEventFilter(ToolTipFilter(self.rateLimitButton))

        self.emptyStatusWidget.setMinimumWidth(200)
        self.emptyStatusWidget.adjustSize()

        self.commandView.hide()

        self.searchLineEdit.setPlaceholderText(self.tr("搜索任务"))

        self.timeSortAction.setChecked(True)
        self.reverseSortAction.setChecked(True)
        self.noFilterAction.setChecked(True)

    def _initLayout(self):
        self.vBoxLayout.setSpacing(20)
        self.vBoxLayout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.vBoxLayout.addWidget(self.toolBar)

        self.toolBarLayout.setContentsMargins(5, 5, 5, 5)
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
        self.toolBarLayout.addWidget(self.categoryFilterButton)
        self.toolBarLayout.addWidget(self.searchLineEdit)
        self.searchLineEdit.setMinimumWidth(200)
        self.searchLineEdit.setMaximumWidth(300)

    def _bind(self):
        self.allStartButton.clicked.connect(self.startAllTasks)
        self.allPauseButton.clicked.connect(self.pauseAllTasks)
        self.selectButton.clicked.connect(lambda: self.setSelectionMode(not self.isSelectionMode))
        self.commandView.redownloadAction.triggered.connect(self._onRedownloadActionTriggered)
        self.commandView.deleteAction.triggered.connect(self._onDeleteActionTriggered)
        self.commandView.selectAllAction.triggered.connect(self.selectAll)
        self.commandView.invertSelectAction.triggered.connect(self.invertSelection)
        self.commandView.cancelAction.triggered.connect(lambda: self.setSelectionMode(False))
        self.timeSortAction.triggered.connect(lambda: self.setSortField(SortField.TIME))
        self.nameSortAction.triggered.connect(lambda: self.setSortField(SortField.NAME))
        self.ascendingSortAction.triggered.connect(lambda: self.setSortOrder(False))
        self.reverseSortAction.triggered.connect(lambda: self.setSortOrder(True))
        self.noFilterAction.triggered.connect(lambda: self.setFilterMode(FilterMode.ALL))
        self.activeFilterAction.triggered.connect(lambda: self.setFilterMode(FilterMode.ACTIVE))
        self.completedFilterAction.triggered.connect(lambda: self.setFilterMode(FilterMode.COMPLETE))
        self.searchLineEdit.textChanged.connect(self._onSearchTextChanged)
        self.searchLineEdit.searchSignal.connect(self._onSearchTextChanged)
        self.searchLineEdit.clearSignal.connect(lambda: self._onSearchTextChanged(""))
        self.rateLimitButton.clicked.connect(self._onRateLimitButtonClicked)
        self.planButton.clicked.connect(self._onPlanButtonClicked)
        self.commandView.moveCategoryAction.triggered.connect(self._onMoveCategoryActionTriggered)
        cfg.enableCategory.valueChanged.connect(self._onEnableCategoryChanged)
        categoryService.categoriesChanged.connect(self._rebuildCategoryFilterMenu)

        self.verticalScrollBar().valueChanged.connect(self._refreshViewport)
        self.refreshTimer.timeout.connect(self.refresh)
        self.refreshTimer.start()

        taskService.taskAdded.connect(self._onTaskAdded)
        taskService.taskRemoved.connect(self._onTaskRemoved)

    def resumeMemorizedTasks(self):
        for task in taskService.tasks.values():
            if task.status in {TaskStatus.RUNNING, TaskStatus.WAITING}:
                coreService.createTask(task)

        self._refreshTaskList()

    def refresh(self):
        for card in self.mountedCards.values():
            card.refresh()

        self.speedBadge.setText(f"{toReadableSize(cfg.globalSpeed)}/s")
        cfg.resetGlobalSpeed()

    @Slot()
    def _onCardFinished(self):
        sender = self.sender()
        if isinstance(sender, TaskCard):
            coreService.sendNotification(sender.task)

        if self.filterMode != FilterMode.ALL or self.categoryFilterId is not None:
            self._refreshTaskList()

        if not self.planButton.isChecked() or not self.planAction or not taskService.tasks:
            return

        if any(task.status != TaskStatus.COMPLETED for task in taskService.tasks.values()):
            return

        action = self.planAction
        filePath = self.planFilePath
        self.planButton.setChecked(False)
        self.planAction = None
        self.planFilePath = ""

        try:
            if action == PlanTaskDialog.OPEN_FILE:
                if filePath:
                    openFile(filePath)
                return

            from subprocess import Popen

            if action == PlanTaskDialog.RESTART:
                if platform == "win32":
                    Popen(["shutdown", "/r", "/t", "0"])
                elif platform == "darwin":
                    Popen(["osascript", "-e", 'tell app "System Events" to restart'])
                else:
                    Popen(["shutdown", "-r", "now"])
                return

            if platform == "win32":
                Popen(["shutdown", "/s", "/t", "0"])
            elif platform == "darwin":
                Popen(["osascript", "-e", 'tell app "System Events" to shut down'])
            else:
                Popen(["shutdown", "-h", "now"])

        except Exception as e:
            logger.opt(exception=e).error("计划任务执行失败")

    @Slot()
    def _refreshTaskList(self):
        previousIds = {task.taskId for task in self.displayOrder}

        candidates = [task for task in taskService.tasks.values() if self._matchTask(task)]
        candidates.sort(key=self._sortKey, reverse=self.sortReverse)
        self.displayOrder = candidates

        currentIds = {task.taskId for task in self.displayOrder}
        for taskId in previousIds - currentIds:
            self._unmountCard(taskId)
        self.selectedIds &= currentIds
        if self.selectionAnchorTaskId not in currentIds:
            self.selectionAnchorTaskId = None

        self.container.setRowCount(len(self.displayOrder))
        self._refreshViewport()
        self._refreshEmptyState()

    @Slot(object)
    def _onTaskAdded(self, _task):
        self._refreshTaskList()

    @Slot(str)
    def _onTaskRemoved(self, taskId: str):
        self._unmountCard(taskId)
        self.selectedIds.discard(taskId)
        if self.selectionAnchorTaskId == taskId:
            self.selectionAnchorTaskId = None
        self._refreshTaskList()
        self._refreshSelection()

    def _sortKey(self, task: Task):
        if self.sortField == SortField.NAME:
            return str(getattr(task, "title", "")).lower()
        return getattr(task, "createdAt", 0)

    def _matchSearch(self, task: Task) -> bool:
        if not self.searchKeyword:
            return True
        return self.searchKeyword in str(task.title).strip().lower()

    def _matchFilter(self, task: Task) -> bool:
        if self.filterMode == FilterMode.ALL:
            return True
        if self.filterMode == FilterMode.ACTIVE:
            return task.status != TaskStatus.COMPLETED
        if self.filterMode == FilterMode.COMPLETE:
            return task.status == TaskStatus.COMPLETED
        return True

    def _matchCategory(self, task: Task) -> bool:
        if not cfg.enableCategory.value or self.categoryFilterId is None:
            return True
        return task.category == self.categoryFilterId

    def _matchTask(self, task: Task) -> bool:
        return self._matchSearch(task) and self._matchFilter(task) and self._matchCategory(task)

    def findCardByTaskId(self, taskId: str) -> TaskCard | None:
        return self.mountedCards.get(taskId)

    @Slot()
    def _refreshViewport(self):
        if not self.displayOrder:
            self._unmountAll()
            return

        viewportTop = self.verticalScrollBar().value()
        viewportHeight = self.viewport().height()
        firstIndex = max(0, self.container.rowAt(viewportTop) - BUFFER_ROWS)
        lastIndex = min(
            len(self.displayOrder) - 1,
            self.container.rowAt(viewportTop + viewportHeight) + BUFFER_ROWS,
        )

        targetIds = {self.displayOrder[idx].taskId for idx in range(firstIndex, lastIndex + 1)}
        for taskId in list(self.mountedCards.keys()):
            if taskId not in targetIds:
                self._unmountCard(taskId)

        for idx in range(firstIndex, lastIndex + 1):
            task = self.displayOrder[idx]
            card = self.mountedCards.get(task.taskId)
            if card is None:
                card = self._mountCard(task)
            self._positionCard(card, idx)

    def _mountCard(self, task: Task) -> TaskCard:
        card = featureService.taskCard(task, self.container)
        card.finished.connect(self._onCardFinished)
        card.selectionChanged.connect(
            lambda checked, extend, t=task: self._onCardSelectionChanged(t, checked, extend)
        )
        card.categoryChanged.connect(self._refreshTaskList)
        card.show()
        self.mountedCards[task.taskId] = card

        if self.isSelectionMode:
            card.setSelectionMode(True)
        if task.taskId in self.selectedIds:
            card.setChecked(True)
        return card

    def _unmountCard(self, taskId: str):
        card = self.mountedCards.pop(taskId, None)
        if card is not None:
            card.deleteLater()

    def _unmountAll(self):
        for taskId in list(self.mountedCards.keys()):
            self._unmountCard(taskId)

    def _positionCard(self, card: TaskCard, index: int):
        y = self.container.rowTop(index)
        width = self.container.width() - 2 * SIDE_PADDING
        card.setGeometry(SIDE_PADDING, y, max(0, width), ROW_HEIGHT)

    def _refreshEmptyState(self):
        if self.displayOrder:
            self.emptyStatusWidget.hide()
            return
        if not taskService.tasks:
            text = self.tr("暂无下载任务")
        elif self.searchKeyword and (self.filterMode != FilterMode.ALL or self.categoryFilterId is not None):
            text = self.tr("没有匹配筛选条件的任务")
        elif self.searchKeyword:
            text = self.tr("没有匹配的任务")
        elif self.categoryFilterId is not None:
            text = self.tr("该分类下暂无任务")
        elif self.filterMode == FilterMode.ACTIVE:
            text = self.tr("暂无活动任务")
        elif self.filterMode == FilterMode.COMPLETE:
            text = self.tr("暂无完成任务")
        else:
            text = self.tr("暂无下载任务")
        self.emptyStatusWidget.setText(text)
        self.emptyStatusWidget.adjustSize()
        self.emptyStatusWidget.move(
            (self.width() - self.emptyStatusWidget.width()) >> 1,
            (self.height() - self.emptyStatusWidget.height()) >> 1,
        )
        self.emptyStatusWidget.show()

    def _onRateLimitButtonClicked(self):
        cfg.set(cfg.enableSpeedLimitation, self.rateLimitButton.isChecked())

    def _onPlanButtonClicked(self):
        if self.planButton.isChecked():
            w = PlanTaskDialog(self.window(), deleteOnClose=False)
            if w.exec() == QDialog.DialogCode.Accepted:
                self.planAction = w.selectedAction()
                self.planFilePath = w.selectedFilePath()
            else:
                self.planButton.setChecked(False)
                self.planAction = None
                self.planFilePath = ""
            w.deleteLater()
        else:
            self.planAction = None
            self.planFilePath = ""

    def _onSearchTextChanged(self, text: str):
        keyword = text.strip().lower()
        if keyword == self.searchKeyword:
            return
        self.searchKeyword = keyword
        self._refreshTaskList()

    def setFilterMode(self, mode: FilterMode):
        if self.filterMode == mode:
            return
        self.filterMode = mode
        self._refreshTaskList()

    def setCategoryFilter(self, categoryId: str | None):
        if self.categoryFilterId == categoryId:
            return
        self.categoryFilterId = categoryId
        self._refreshTaskList()

    def _rebuildCategoryFilterMenu(self):
        self.categoryFilterMenu.clear()
        self.categoryFilterMenu.view.clear()
        for action in self.categoryFilterActionGroup.actions():
            self.categoryFilterActionGroup.removeAction(action)
            action.deleteLater()

        allAction = Action(FluentIcon.FILTER, self.tr("全部分类"), self, checkable=True)
        allAction.triggered.connect(lambda: self.setCategoryFilter(None))
        self.categoryFilterActionGroup.addAction(allAction)
        self.categoryFilterMenu.addAction(allAction)
        self.categoryFilterMenu.addSeparator()

        uncategorizedAction = Action(FluentIcon.MORE, self.tr("未分类"), self, checkable=True)
        uncategorizedAction.triggered.connect(lambda: self.setCategoryFilter(UNCATEGORIZED_ID))
        self.categoryFilterActionGroup.addAction(uncategorizedAction)
        self.categoryFilterMenu.addAction(uncategorizedAction)

        validIds = {UNCATEGORIZED_ID}
        for category in categoryService.categories():
            cid = category.categoryId
            validIds.add(cid)
            action = Action(category.fluentIcon(), category.name, self, checkable=True)
            action.triggered.connect(
                lambda checked=False, c=cid: self.setCategoryFilter(c)
            )
            self.categoryFilterActionGroup.addAction(action)
            self.categoryFilterMenu.addAction(action)

        if self.categoryFilterId is not None and self.categoryFilterId not in validIds:
            self.categoryFilterId = None
            self._refreshTaskList()

        for action in self.categoryFilterActionGroup.actions():
            action.setChecked(False)
        if self.categoryFilterId is None:
            allAction.setChecked(True)
        elif self.categoryFilterId == UNCATEGORIZED_ID:
            uncategorizedAction.setChecked(True)
        else:
            for action in self.categoryFilterActionGroup.actions():
                if action.text() and action is not allAction and action is not uncategorizedAction:
                    category = next(
                        (c for c in categoryService.categories() if c.name == action.text()),
                        None,
                    )
                    if category and category.categoryId == self.categoryFilterId:
                        action.setChecked(True)
                        break

    def _onEnableCategoryChanged(self, value: bool):
        self.categoryFilterButton.setVisible(bool(value))
        if not value and self.categoryFilterId is not None:
            self.categoryFilterId = None
        self._refreshTaskList()

    def _onMoveCategoryActionTriggered(self):
        targets = [taskService.tasks[tid] for tid in self.selectedIds if tid in taskService.tasks]
        if not targets:
            return

        popup = RoundMenu(parent=self)
        uncategorizedAction = Action(FluentIcon.MORE, self.tr("未分类"), self)
        uncategorizedAction.triggered.connect(
            lambda: self._applyCategoryToTasks(targets, UNCATEGORIZED_ID)
        )
        popup.addAction(uncategorizedAction)
        popup.addSeparator()
        for category in categoryService.categories():
            cid = category.categoryId
            action = Action(category.fluentIcon(), category.name, self)
            action.triggered.connect(
                lambda checked=False, c=cid: self._applyCategoryToTasks(targets, c)
            )
            popup.addAction(action)

        popup.exec(QCursor.pos())

    def _applyCategoryToTasks(self, tasks: list[Task], categoryId: str):
        for task in tasks:
            if task.category == categoryId:
                continue
            task.category = categoryId
            card = self.mountedCards.get(task.taskId)
            if card is not None:
                card._onCategoryUpdated()
        taskService.scheduleFlush()
        self._refreshTaskList()

    def setSortField(self, field: SortField):
        if self.sortField == field:
            return
        self.sortField = field
        self._refreshTaskList()

    def setSortOrder(self, reverse: bool):
        if self.sortReverse == reverse:
            return
        self.sortReverse = reverse
        self._refreshTaskList()

    def startAllTasks(self):
        for task in self.displayOrder:
            if task.status in {TaskStatus.WAITING, TaskStatus.PAUSED, TaskStatus.FAILED}:
                coreService.createTask(task)

    def pauseAllTasks(self):
        for task in self.displayOrder:
            if task.status in {TaskStatus.RUNNING, TaskStatus.WAITING}:
                coreService.stopTask(task)

    def selectAll(self):
        for task in self.displayOrder:
            self.selectedIds.add(task.taskId)
        if self.displayOrder:
            self.selectionAnchorTaskId = self.displayOrder[-1].taskId
        self._refreshSelection()

    def invertSelection(self):
        for task in self.displayOrder:
            if task.taskId in self.selectedIds:
                self.selectedIds.discard(task.taskId)
            else:
                self.selectedIds.add(task.taskId)
        self._refreshSelection()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._refreshViewport()
        width = self.width()
        height = self.height()
        self.commandView.move(
            (width - self.commandView.width()) >> 1,
            height - self.commandView.sizeHint().height() - 20,
        )
        self.emptyStatusWidget.move(
            (width - self.emptyStatusWidget.width()) >> 1,
            (height - self.emptyStatusWidget.height()) >> 1,
        )

    def _refreshSelection(self):
        for taskId, card in self.mountedCards.items():
            card.setChecked(taskId in self.selectedIds)
        self.setSelectionMode(bool(self.selectedIds))
        if not self.selectedIds:
            self.selectionAnchorTaskId = None

    def _onCardSelectionChanged(self, task: Task, checked: bool, extend: bool):
        if extend and self.displayOrder:
            anchorId = self.selectionAnchorTaskId
            anchorTask = taskService.tasks.get(anchorId) if anchorId else None
            if anchorTask is None or anchorTask not in self.displayOrder:
                anchorTask = task

            start = self.displayOrder.index(anchorTask)
            end = self.displayOrder.index(task)
            if start > end:
                start, end = end, start

            rangeIds = {self.displayOrder[i].taskId for i in range(start, end + 1)}
            self.selectedIds = rangeIds
            self.selectionAnchorTaskId = anchorTask.taskId
        else:
            if checked:
                self.selectedIds.add(task.taskId)
                self.selectionAnchorTaskId = task.taskId
            else:
                self.selectedIds.discard(task.taskId)
                if self.selectionAnchorTaskId == task.taskId:
                    self.selectionAnchorTaskId = None

        self._refreshSelection()

    def _onDeleteActionTriggered(self):
        w = DeleteTaskDialog(self.window(), deleteOnClose=False)
        w.deleteFileCheckBox.setChecked(False)

        if w.exec():
            deleteFiles = w.deleteFileCheckBox.isChecked()
            for taskId in list(self.selectedIds):
                task = taskService.tasks.get(taskId)
                if task is None:
                    continue
                card = self.mountedCards.get(taskId)
                if card is not None:
                    card.removeTask(deleteFiles)
                else:
                    coreService.runCoroutine(
                        coreService._stopTask(task),
                        lambda _result, _error, t=task, f=deleteFiles: self._onUnmountedTaskStopped(t, f),
                    )

        w.deleteLater()

    def _onUnmountedTaskStopped(self, task: Task, deleteFile: bool):
        if deleteFile:
            task.cleanup()
        taskService.remove(task)

    def _onRedownloadActionTriggered(self):
        for taskId in list(self.selectedIds):
            card = self.mountedCards.get(taskId)
            if card is not None:
                card.redownloadTask()

    def setSelectionMode(self, enter: bool):
        if self.isSelectionMode == enter:
            return

        self.isSelectionMode = enter

        for card in self.mountedCards.values():
            card.setSelectionMode(enter)
            card.setChecked(card.task.taskId in self.selectedIds)

        if enter:
            self.commandView.setVisible(True)
            self.commandView.raise_()
        else:
            self.commandView.setVisible(False)
            self.selectedIds.clear()
            self.selectionAnchorTaskId = None
