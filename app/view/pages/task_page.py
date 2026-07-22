from __future__ import annotations

from enum import IntEnum
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QSize, QThread, QTimer
from PySide6.QtGui import QActionGroup, QColor, QCursor, QPainter
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (
    Action, CaptionLabel, CheckableMenu, CommandBarView, DropDownToolButton,
    FluentIcon, IconWidget, MenuIndicatorType, PushButton,
    RoundMenu, SegmentedToggleToolWidget, ToggleToolButton,
    ToolButton, ToolTipFilter, isDarkTheme,
)

from app.view.components.band_selector import BandSelector
from app.view.components.scroll_area import ScrollArea

from app.config.cfg import cfg
from app.format import toReadableSize
from app.models.task import TaskStatus
from app.view.cards.task_cards import TaskCard
from app.view.components.labels import IconBodyLabel

if TYPE_CHECKING:
    from app.models.task import Task
    from app.services.category_service import CategoryService
    from app.services.coroutine_runner import CoroutineRunner
    from app.services.feature_service import FeatureService
    from app.services.speed_meter import SpeedMeter
    from app.services.task_service import TaskService
    from app.services.plan import Plan


class FilterMode(IntEnum):
    ALL = 0
    ACTIVE = 1
    COMPLETED = 2


FILTER_TO_STATUSES = {
    FilterMode.ACTIVE: {TaskStatus.RUNNING, TaskStatus.WAITING, TaskStatus.PAUSED},
    FilterMode.COMPLETED: {TaskStatus.COMPLETED, TaskStatus.FAILED},
}

ROUTE_TO_FILTER = {
    "all": FilterMode.ALL,
    "active": FilterMode.ACTIVE,
    "completed": FilterMode.COMPLETED,
}


class SortField(IntEnum):
    CREATED_AT = 0
    NAME = 1
    SIZE = 2
    COMPLETED_AT = 3


class TaskCommandBarView(CommandBarView):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.redownloadAction = Action(FluentIcon.UPDATE, self.tr("重新下载"), self)
        self.deleteAction = Action(FluentIcon.DELETE, self.tr("删除"), self)
        self.moveCategoryAction = Action(FluentIcon.TAG, self.tr("移动到分类"), self)
        self.selectAllAction = Action(FluentIcon.CLEAR_SELECTION, self.tr("全选"), self)
        self.selectMissingAction = Action(FluentIcon.REMOVE, self.tr("选择缺失"), self)
        self.invertSelectAction = Action(FluentIcon.CUT, self.tr("反选"), self)
        self.cancelAction = Action(FluentIcon.CLEAR_SELECTION, self.tr("取消全选"), self)

        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.setIconSize(QSize(18, 18))
        self.addAction(self.redownloadAction)
        self.addAction(self.deleteAction)
        self.addAction(self.moveCategoryAction)
        self.addSeparator()
        self.addAction(self.selectAllAction)
        self.addAction(self.selectMissingAction)
        self.addAction(self.invertSelectAction)
        self.addAction(self.cancelAction)
        self.resizeToSuitableWidth()

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(35)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(0, 0, 0, 80 if isDarkTheme() else 30))
        self.setGraphicsEffect(shadow)

        self.moveCategoryAction.setVisible(cfg.isCategoryEnabled.value)
        cfg.isCategoryEnabled.valueChanged.connect(self._onCategoryEnabledChanged)

    def _onCategoryEnabledChanged(self, value) -> None:
        self.moveCategoryAction.setVisible(bool(value))


class EmptyStatusWidget(QWidget):

    def __init__(self, icon, text, parent=None):
        super().__init__(parent)
        self.iconWidget = IconWidget(icon)
        self.iconWidget.setFixedSize(64, 64)
        self.label = CaptionLabel(text)
        self.label.setTextColor(QColor(96, 96, 96), QColor(216, 216, 216))
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.borderRadius = 10

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 20, 16, 20)
        layout.addWidget(self.iconWidget, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self.label, 0, Qt.AlignmentFlag.AlignHCenter)

    def setText(self, text: str) -> None:
        self.label.setText(text)

    def paintEvent(self, e):
        painter = QPainter(self)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(255, 255, 255, 13 if isDarkTheme() else 200))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(self.rect(), self.borderRadius, self.borderRadius)


class TaskPage(QWidget):
    ROW_SPACING = 8
    SIDE_PADDING = 12
    BOTTOM_PADDING = 12
    VIEWPORT_BUFFER = 5

    def __init__(
        self,
        taskService: TaskService,
        featureService: FeatureService,
        categoryService: CategoryService,
        speedMeter: SpeedMeter,
        coroutineRunner: CoroutineRunner,
        plan: Plan | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._taskService = taskService
        self._featureService = featureService
        self._categoryService = categoryService
        self._speedMeter = speedMeter
        self._coroutineRunner = coroutineRunner
        self._plan = plan
        self._filterMode = FilterMode.ALL
        self._categoryFilter = ""
        self._sortField = SortField.CREATED_AT
        self._sortAscending = False
        self._searchText = ""
        self._isSelectionMode = False
        self._selectionAnchor: str | None = None
        self._liveCards: dict[str, TaskCard] = {}
        self._pendingUnmounts: list[TaskCard] = []
        self._displayOrder: list[str] = []
        self._selectedIds: set[str] = set()
        self._bandSnapshot: set[str] = set()
        self._runningIds: set[str] = set()

        self._refreshListTimer = QTimer(self, singleShot=True)
        self._refreshListTimer.setInterval(0)
        self._refreshListTimer.timeout.connect(self._refreshList)

        self._cardRefreshTimer = QTimer(self)
        self._cardRefreshTimer.setInterval(1000)
        self._cardRefreshTimer.timeout.connect(self._refreshRunningCards)

        self.scrollArea = ScrollArea(self)
        self.scrollWidget = QWidget(self)
        self.emptyStatusWidget = EmptyStatusWidget(FluentIcon.EMOJI_TAB_SYMBOLS, self.tr("暂无下载任务"), self)

        # toolbar
        self.toolBar = QWidget(self)
        self.startAllButton = PushButton(FluentIcon.PLAY, self.tr("全部开始"), self.toolBar)
        self.pauseAllButton = PushButton(FluentIcon.PAUSE, self.tr("全部暂停"), self.toolBar)
        self.selectButton = ToolButton(FluentIcon.CLEAR_SELECTION, self.toolBar)
        self.planButton = ToggleToolButton(FluentIcon.DATE_TIME, self.toolBar)
        self.rateLimitButton = ToggleToolButton(FluentIcon.SPEED_OFF, self.toolBar)
        self.speedBadge = IconBodyLabel("0.00B/s", FluentIcon.SPEED_HIGH, self.toolBar)
        self.sortButton = DropDownToolButton(FluentIcon.LAYOUT, self.toolBar)
        self.categoryFilterButton = DropDownToolButton(FluentIcon.TAG, self.toolBar)

        # sort menu
        self.sortMenu = CheckableMenu(parent=self, indicatorType=MenuIndicatorType.RADIO)
        self.sortFieldGroup = QActionGroup(self)
        self.sortOrderGroup = QActionGroup(self)
        self.createdAtSortAction = Action(FluentIcon.DATE_TIME, self.tr("按添加时间"), self, checkable=True)
        self.completedAtSortAction = Action(FluentIcon.HISTORY, self.tr("按完成时间"), self, checkable=True)
        self.nameSortAction = Action(FluentIcon.FONT, self.tr("按名称排序"), self, checkable=True)
        self.sizeSortAction = Action(FluentIcon.LIBRARY, self.tr("按大小排序"), self, checkable=True)
        self.ascendingAction = Action(FluentIcon.UP, self.tr("顺序"), self, checkable=True)
        self.descendingAction = Action(FluentIcon.DOWN, self.tr("倒序"), self, checkable=True)

        # filter segment
        self.filterSegment = SegmentedToggleToolWidget(self.toolBar)

        # category filter menu
        self.categoryFilterMenu = CheckableMenu(parent=self, indicatorType=MenuIndicatorType.RADIO)
        self.categoryFilterGroup = QActionGroup(self)

        # selection command bar
        self.commandView = TaskCommandBarView(self)
        self.commandView.hide()

        self._initWidget()
        self._initLayout()
        self._bind()

    def _initWidget(self) -> None:
        self.setObjectName("TaskPage")
        self.scrollArea.setWidget(self.scrollWidget)
        self.scrollArea.setWidgetResizable(True)
        self.scrollArea.enableTransparentBackground()

        self.sortFieldGroup.addAction(self.createdAtSortAction)
        self.sortFieldGroup.addAction(self.completedAtSortAction)
        self.sortFieldGroup.addAction(self.nameSortAction)
        self.sortFieldGroup.addAction(self.sizeSortAction)
        self.sortOrderGroup.addAction(self.ascendingAction)
        self.sortOrderGroup.addAction(self.descendingAction)
        self.sortMenu.addAction(self.createdAtSortAction)
        self.sortMenu.addAction(self.completedAtSortAction)
        self.sortMenu.addAction(self.nameSortAction)
        self.sortMenu.addAction(self.sizeSortAction)
        self.sortMenu.addSeparator()
        self.sortMenu.addAction(self.ascendingAction)
        self.sortMenu.addAction(self.descendingAction)
        self.sortButton.setMenu(self.sortMenu)
        self.createdAtSortAction.setChecked(True)
        self.descendingAction.setChecked(True)

        self.filterSegment.addItem("all", FluentIcon.HOME)
        self.filterSegment.addItem("active", FluentIcon.DOWNLOAD)
        self.filterSegment.addItem("completed", FluentIcon.ACCEPT)
        self.filterSegment.setCurrentItem("all")
        for key, tip in (("all", self.tr("全部任务")), ("active", self.tr("活动任务")), ("completed", self.tr("完成任务"))):
            w = self.filterSegment.widget(key)
            w.setToolTip(tip)
            w.installEventFilter(ToolTipFilter(w))

        self.categoryFilterButton.setMenu(self.categoryFilterMenu)
        self.categoryFilterButton.setVisible(cfg.isCategoryEnabled.value)

        self.rateLimitButton.setChecked(cfg.isSpeedLimitEnabled.value)

        for btn, tip in (
            (self.selectButton, self.tr("选择任务")),
            (self.planButton, self.tr("计划任务")),
            (self.rateLimitButton, self.tr("限速")),
            (self.categoryFilterButton, self.tr("按分类筛选")),
        ):
            btn.setToolTip(tip)
            btn.installEventFilter(ToolTipFilter(btn))

        self.emptyStatusWidget.setMinimumWidth(200)
        self.emptyStatusWidget.adjustSize()

        self._rebuildCategoryFilterMenu()

    def _initLayout(self) -> None:
        toolBarLayout = QHBoxLayout(self.toolBar)
        toolBarLayout.setContentsMargins(16, 10, 16, 10)
        toolBarLayout.addWidget(self.filterSegment)
        toolBarLayout.addWidget(self.startAllButton)
        toolBarLayout.addWidget(self.pauseAllButton)
        toolBarLayout.addWidget(self.selectButton)
        toolBarLayout.addWidget(self.planButton)
        toolBarLayout.addWidget(self.rateLimitButton)
        toolBarLayout.addSpacing(10)
        toolBarLayout.addWidget(self.speedBadge)
        toolBarLayout.addStretch(1)
        toolBarLayout.addWidget(self.sortButton)
        toolBarLayout.addWidget(self.categoryFilterButton)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.toolBar)
        layout.addWidget(self.scrollArea)

    def _bind(self) -> None:
        self._taskService.taskAdded.connect(self._onTaskAdded)
        self._taskService.taskRemoved.connect(self._onTaskRemoved)
        self._taskService.taskStarted.connect(self._onTaskStarted)
        self._taskService.taskPaused.connect(self._onTaskStopped)
        self._taskService.taskCompleted.connect(self._onTaskStopped)
        self._taskService.taskFailed.connect(self._onTaskStopped)
        self._taskService.tasksAllCompleted.connect(self._onAllCompleted)
        self._taskService.fileDisappeared.connect(self._onFileDisappeared)
        self._speedMeter.speedChanged.connect(self._onSpeedChanged)
        self.scrollArea.verticalScrollBar().valueChanged.connect(self._refreshViewport)

        self.startAllButton.clicked.connect(self.startAll)
        self.pauseAllButton.clicked.connect(self.pauseAll)
        self.selectButton.clicked.connect(lambda: self.setSelectionMode(not self._isSelectionMode))
        self.planButton.clicked.connect(self._onPlanButtonClicked)
        self.rateLimitButton.clicked.connect(self._onRateLimitToggled)

        self.createdAtSortAction.triggered.connect(lambda: self.setSortField(SortField.CREATED_AT))
        self.completedAtSortAction.triggered.connect(lambda: self.setSortField(SortField.COMPLETED_AT))
        self.nameSortAction.triggered.connect(lambda: self.setSortField(SortField.NAME))
        self.sizeSortAction.triggered.connect(lambda: self.setSortField(SortField.SIZE))
        self.ascendingAction.triggered.connect(lambda: self.setSortOrder(True))
        self.descendingAction.triggered.connect(lambda: self.setSortOrder(False))

        self.filterSegment.currentItemChanged.connect(lambda key: self.setFilterMode(ROUTE_TO_FILTER[key]))

        self.commandView.redownloadAction.triggered.connect(self._onRedownloadSelected)
        self.commandView.deleteAction.triggered.connect(self._onDeleteSelected)
        self.commandView.moveCategoryAction.triggered.connect(self._onMoveCategorySelected)
        self.commandView.selectAllAction.triggered.connect(self.selectAll)
        self.commandView.selectMissingAction.triggered.connect(self.selectMissing)
        self.commandView.invertSelectAction.triggered.connect(self.invertSelection)
        self.commandView.cancelAction.triggered.connect(lambda: self.setSelectionMode(False))

        cfg.isCategoryEnabled.valueChanged.connect(self._onCategoryEnabledChanged)
        self._categoryService.categoriesChanged.connect(self._rebuildCategoryFilterMenu)

        self._bandSelector = BandSelector(
            self.scrollArea, self.scrollWidget,
            TaskCard.ROW_HEIGHT, self.ROW_SPACING, self
        )
        self._bandSelector.dragStarted.connect(self._onBandDragStarted)
        self._bandSelector.bandChanged.connect(self._onBandChanged)
        self._bandSelector.dragFinished.connect(self._onBandDragFinished)

        self._refreshListTimer.start()

    # ── intent methods ──

    def setFilterMode(self, mode: FilterMode) -> None:
        self._filterMode = mode
        self._refreshList()

    def setCategoryFilter(self, categoryId: str) -> None:
        self._categoryFilter = categoryId
        self._refreshList()

    def setSortField(self, field: SortField) -> None:
        self._sortField = field
        self._refreshList()

    def setSortOrder(self, ascending: bool) -> None:
        self._sortAscending = ascending
        self._refreshList()

    @property
    def searchPlaceholder(self) -> str:
        return self.tr("搜索任务")

    def setSearchText(self, text: str) -> None:
        self._searchText = text
        self._refreshList()

    def startAll(self) -> None:
        self._taskService.startAll()

    def pauseAll(self) -> None:
        self._taskService.pauseAll()

    def selectAll(self) -> None:
        self._selectedIds.update(self._displayOrder)
        for card in self._liveCards.values():
            card.setChecked(True)

    def invertSelection(self) -> None:
        self._selectedIds ^= set(self._displayOrder)
        for taskId, card in self._liveCards.items():
            card.setChecked(taskId in self._selectedIds)

    def selectMissing(self) -> None:
        self._selectedIds.clear()
        for taskId in self._displayOrder:
            task = self._taskService.taskById(taskId)
            if task and task.hasOutputFile and not Path(task.outputPath).exists():
                self._selectedIds.add(taskId)
        for taskId, card in self._liveCards.items():
            card.setChecked(taskId in self._selectedIds)

    def setSelectionMode(self, enter: bool) -> None:
        if self._isSelectionMode == enter:
            return
        self._isSelectionMode = enter
        self._selectionAnchor = None
        if not enter:
            self._selectedIds.clear()
        for card in self._liveCards.values():
            card.setSelectionMode(enter)
            if not enter:
                card.setChecked(False)
        self.commandView.setVisible(enter)
        if enter:
            self.commandView.raise_()

    def _onCardSelectionChanged(self, taskId: str, checked: bool, extend: bool) -> None:
        if not self._isSelectionMode:
            self.setSelectionMode(True)

        if extend and self._selectionAnchor:
            try:
                anchorIdx = self._displayOrder.index(self._selectionAnchor)
                currentIdx = self._displayOrder.index(taskId)
            except ValueError:
                return
            self._selectedIds.clear()
            for i in range(min(anchorIdx, currentIdx), max(anchorIdx, currentIdx) + 1):
                self._selectedIds.add(self._displayOrder[i])
            for tid, card in self._liveCards.items():
                card.setChecked(tid in self._selectedIds)
        else:
            if checked:
                self._selectedIds.add(taskId)
            else:
                self._selectedIds.discard(taskId)
            card = self._liveCards.get(taskId)
            if card:
                card.setChecked(checked)
            if checked:
                self._selectionAnchor = taskId
            elif taskId == self._selectionAnchor:
                self._selectionAnchor = None

        if not self._selectedIds:
            self.setSelectionMode(False)

    @property
    def isSelectionMode(self) -> bool:
        return self._isSelectionMode

    @property
    def isSortAscending(self) -> bool:
        return self._sortAscending

    # ── toolbar handlers ──

    def _onSpeedChanged(self, speed: int) -> None:
        self.speedBadge.setText(f"{toReadableSize(speed)}/s")

    def _onRateLimitToggled(self) -> None:
        cfg.set(cfg.isSpeedLimitEnabled, self.rateLimitButton.isChecked())

    def _onPlanButtonClicked(self) -> None:
        plan = self._plan
        if plan is None:
            return
        if self.planButton.isChecked():
            from app.view.dialogs.plan_task import PlanTaskDialog
            dialog = PlanTaskDialog(self.window())
            if dialog.exec():
                plan.set(dialog.selectedAction(), dialog.selectedFilePath(),
                         onCleared=lambda: self.planButton.setChecked(False))
            else:
                self.planButton.setChecked(False)
            dialog.deleteLater()
        else:
            plan.clear()

    def _onCategoryEnabledChanged(self, value) -> None:
        self.categoryFilterButton.setVisible(bool(value))

    def _rebuildCategoryFilterMenu(self) -> None:
        self.categoryFilterMenu.clear()
        for action in self.categoryFilterGroup.actions():
            self.categoryFilterGroup.removeAction(action)
            action.deleteLater()

        allAction = Action(FluentIcon.FILTER, self.tr("全部分类"), self, checkable=True)
        allAction.triggered.connect(lambda: self.setCategoryFilter(""))
        self.categoryFilterGroup.addAction(allAction)
        self.categoryFilterMenu.addAction(allAction)
        self.categoryFilterMenu.addSeparator()

        validIds: set[str] = {""}
        for category in self._categoryService.categories():
            cid = category.categoryId
            validIds.add(cid)
            action = Action(category.toIcon(), category.name, self, checkable=True)
            action.triggered.connect(lambda checked=False, c=cid: self.setCategoryFilter(c))
            self.categoryFilterGroup.addAction(action)
            self.categoryFilterMenu.addAction(action)
            if cid == self._categoryFilter:
                action.setChecked(True)

        if self._categoryFilter not in validIds:
            self._categoryFilter = ""
            self._refreshList()

        if not self._categoryFilter:
            allAction.setChecked(True)

    def _onRedownloadSelected(self) -> None:
        for taskId in self._displayOrder:
            if taskId in self._selectedIds:
                task = self._taskService.taskById(taskId)
                if task:
                    self._taskService.redownload(task)
        self.setSelectionMode(False)

    def _onDeleteSelected(self) -> None:
        from qfluentwidgets import CheckBox, MessageBox
        dialog = MessageBox(self.tr("删除任务"), self.tr("确定要删除选中的下载任务吗？"), self.window())
        deleteFiles = CheckBox(self.tr("同时删除已下载的文件"))
        deleteFiles.setChecked(cfg.shouldDeleteFilesOnRemove.value)
        dialog.textLayout.addWidget(deleteFiles)
        if dialog.exec():
            cfg.set(cfg.shouldDeleteFilesOnRemove, deleteFiles.isChecked())
            self._onDeleteConfirmed(deleteFiles.isChecked())

    def _onMoveCategorySelected(self) -> None:
        targets = [
            task for taskId in self._displayOrder
            if taskId in self._selectedIds and (task := self._taskService.taskById(taskId))
        ]
        if not targets:
            return

        def moveTo(categoryId):
            for task in targets:
                self._taskService.setCategory(task, categoryId)
            self.setSelectionMode(False)
            self._refreshList()

        popup = RoundMenu(parent=self)
        uncategorized = Action(FluentIcon.MORE, self.tr("未分类"), self)
        uncategorized.triggered.connect(lambda: moveTo(""))
        popup.addAction(uncategorized)
        popup.addSeparator()
        for category in self._categoryService.categories():
            cid = category.categoryId
            action = Action(category.toIcon(), category.name, self)
            action.triggered.connect(lambda checked=False, c=cid: moveTo(c))
            popup.addAction(action)
        popup.exec(QCursor.pos())

    def _onDeleteConfirmed(self, shouldDeleteFiles: bool) -> None:
        for taskId in list(self._selectedIds & set(self._displayOrder)):
            task = self._taskService.taskById(taskId)
            if task:
                self._taskService.delete(task, shouldDeleteFiles)
        self.setSelectionMode(False)

    # ── list management ──

    def _refreshList(self) -> None:
        tasks = self._taskService.tasks

        if self._filterMode != FilterMode.ALL:
            statuses = FILTER_TO_STATUSES.get(self._filterMode)
            if statuses is not None:
                tasks = [t for t in tasks if t.status in statuses]

        if self._categoryFilter:
            tasks = [t for t in tasks if t.category == self._categoryFilter]

        if self._searchText:
            lower = self._searchText.lower()
            tasks = [t for t in tasks if lower in t.name.lower() or lower in t.url.lower()]

        if self._sortField == SortField.NAME:
            tasks.sort(key=lambda t: t.name.lower(), reverse=not self._sortAscending)
        elif self._sortField == SortField.SIZE:
            tasks.sort(key=lambda t: t.fileSize, reverse=not self._sortAscending)
        elif self._sortField == SortField.COMPLETED_AT:
            desc = not self._sortAscending
            completed = [t for t in tasks if t.completedAt]
            pending = [t for t in tasks if not t.completedAt]
            completed.sort(key=lambda t: t.completedAt, reverse=desc)
            pending.sort(key=lambda t: t.createdAt, reverse=desc)
            tasks = pending + completed if desc else completed + pending
        else:
            tasks.sort(key=lambda t: t.createdAt, reverse=not self._sortAscending)

        self._displayOrder = [t.taskId for t in tasks]
        self._runningIds = {t.taskId for t in self._taskService.tasks if t.status == TaskStatus.RUNNING}
        if self._runningIds and not self._cardRefreshTimer.isActive():
            self._cardRefreshTimer.start()
        elif not self._runningIds and self._cardRefreshTimer.isActive():
            self._cardRefreshTimer.stop()
        stride = TaskCard.ROW_HEIGHT + self.ROW_SPACING
        count = len(self._displayOrder)
        self.scrollWidget.setFixedHeight(
            count * stride - self.ROW_SPACING + self.BOTTOM_PADDING if count else 0
        )
        self._bandSelector.setItemCount(count)
        self._refreshViewport()

        if self._displayOrder:
            self.emptyStatusWidget.hide()
        else:
            if not self._taskService.tasks:
                text = self.tr("暂无下载任务")
            elif self._searchText and (self._filterMode != FilterMode.ALL or self._categoryFilter):
                text = self.tr("没有匹配筛选条件的任务")
            elif self._searchText:
                text = self.tr("没有匹配的任务")
            elif self._categoryFilter:
                text = self.tr("该分类下暂无任务")
            elif self._filterMode == FilterMode.ACTIVE:
                text = self.tr("暂无活动任务")
            elif self._filterMode == FilterMode.COMPLETED:
                text = self.tr("暂无完成任务")
            else:
                text = self.tr("暂无下载任务")
            self.emptyStatusWidget.setText(text)
            self.emptyStatusWidget.adjustSize()
            self.emptyStatusWidget.show()

    def _unmountCard(self, card: TaskCard) -> None:
        card.hide()
        # 嵌套事件循环（对话框 exec 等）可能正挂在卡片的栈帧上，
        # 此刻销毁会让栈回退进已删控件；推迟到回到主循环后的下次刷新
        if QThread.currentThread().loopLevel() > 1:
            self._pendingUnmounts.append(card)
        else:
            card.deleteLater()

    def _refreshViewport(self) -> None:
        if self._pendingUnmounts and QThread.currentThread().loopLevel() == 1:
            for card in self._pendingUnmounts:
                card.deleteLater()
            self._pendingUnmounts.clear()

        stride = TaskCard.ROW_HEIGHT + self.ROW_SPACING
        width = self.scrollWidget.width()
        count = len(self._displayOrder)
        if count:
            top = self.scrollArea.verticalScrollBar().value()
            height = self.scrollArea.viewport().height()
            first = max(0, top // stride - self.VIEWPORT_BUFFER)
            last = min(count - 1, (top + height) // stride + self.VIEWPORT_BUFFER)
        else:
            first, last = 0, -1

        desired: set[str] = {self._displayOrder[i] for i in range(first, last + 1)}

        for taskId in list(self._liveCards.keys() - desired):
            self._unmountCard(self._liveCards.pop(taskId))

        for idx in range(first, last + 1):
            taskId = self._displayOrder[idx]
            card = self._liveCards.get(taskId)
            if card is None:
                task = self._taskService.taskById(taskId)
                if task is None:
                    continue
                card = self._createCard(task)
                if card is None:
                    continue
                card.setSelectionMode(self._isSelectionMode)
                if taskId in self._selectedIds:
                    card.setChecked(True)
                card.selectionChanged.connect(
                    lambda checked, extend, tid=taskId: self._onCardSelectionChanged(tid, checked, extend)
                )
                # 队列投递：拖拽是阻塞式消息循环，不能挂在卡片的栈帧上
                card.dragRequested.connect(
                    self._onCardDragRequested, Qt.ConnectionType.QueuedConnection
                )
                self._liveCards[taskId] = card
                card.refresh()
            card.setGeometry(self.SIDE_PADDING, idx * stride, max(0, width - 2 * self.SIDE_PADDING), TaskCard.ROW_HEIGHT)
            card.show()

    def _refreshRunningCards(self) -> None:
        for taskId in self._runningIds:
            card = self._liveCards.get(taskId)
            if card is not None:
                card.refresh()

    def _onTaskStarted(self, task: Task) -> None:
        self._runningIds.add(task.taskId)
        card = self._liveCards.get(task.taskId)
        if card is not None:
            card.refresh()
        if not self._cardRefreshTimer.isActive():
            self._cardRefreshTimer.start()

    def _onTaskStopped(self, task: Task) -> None:
        self._runningIds.discard(task.taskId)
        card = self._liveCards.get(task.taskId)
        if card is not None:
            card.refresh()
        if not self._runningIds:
            self._cardRefreshTimer.stop()

    def _onAllCompleted(self) -> None:
        self._runningIds.clear()
        self._cardRefreshTimer.stop()

    # ── band selection ──

    def _onBandDragStarted(self, shiftHeld: bool) -> None:
        if not self._isSelectionMode:
            self.setSelectionMode(True)
        self._bandSnapshot = set(self._selectedIds) if shiftHeld else set()

    def _onBandChanged(self, first: int, last: int) -> None:
        bandIds = {self._displayOrder[i] for i in range(first, last + 1)} if first >= 0 else set()
        self._selectedIds = self._bandSnapshot | bandIds
        for taskId, card in self._liveCards.items():
            card.setChecked(taskId in self._selectedIds)

    def _onBandDragFinished(self) -> None:
        if not self._selectedIds:
            self.setSelectionMode(False)

    # ── file drag ──

    def _onCardDragRequested(self, taskId: str) -> None:
        from app.platform.desktop import startFileDrag
        if self._isSelectionMode and taskId in self._selectedIds:
            paths = [
                Path(task.outputPath)
                for tid in self._selectedIds
                if (task := self._taskService.taskById(tid))
                and task.status == TaskStatus.COMPLETED
                and task.hasOutputFile
                and Path(task.outputPath).exists()
            ]
        else:
            task = self._taskService.taskById(taskId)
            paths = [Path(task.outputPath)] if task else []
        if paths:
            startFileDrag(paths, self)

    # ── events ──

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Delete and self._isSelectionMode:
            self._onDeleteSelected()
        else:
            super().keyPressEvent(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._refreshViewport()
        self.commandView.move(
            (self.width() - self.commandView.width()) // 2,
            self.height() - self.commandView.sizeHint().height() - 20,
        )
        self.emptyStatusWidget.move(
            (self.width() - self.emptyStatusWidget.width()) // 2,
            (self.height() - self.emptyStatusWidget.height()) // 2,
        )

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._refreshViewport()

    def _createCard(self, task: Task) -> TaskCard | None:
        return self._featureService.taskCard(task, self.scrollWidget)

    def _onTaskAdded(self, task: Task) -> None:
        self._refreshListTimer.start()

    def _onTaskRemoved(self, taskId: str) -> None:
        card = self._liveCards.pop(taskId, None)
        if card is not None:
            self._unmountCard(card)
        self._selectedIds.discard(taskId)
        self._runningIds.discard(taskId)
        if self._selectionAnchor == taskId:
            self._selectionAnchor = None
        if not self._runningIds:
            self._cardRefreshTimer.stop()
        self._refreshListTimer.start()

    def _onFileDisappeared(self, task: Task) -> None:
        card = self._liveCards.get(task.taskId)
        if card is not None:
            card.refresh(force=True)
