from __future__ import annotations

from enum import IntEnum
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QActionGroup, QColor, QCursor, QPainter
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (
    Action, CaptionLabel, CheckableMenu, CommandBarView, DropDownToolButton,
    FluentIcon, IconWidget, MenuIndicatorType, PrimaryPushButton, PushButton,
    RoundMenu, ScrollArea, SearchLineEdit, ToggleToolButton, ToolButton, ToolTipFilter,
    isDarkTheme,
)

from app.config.cfg import cfg
from app.format import toReadableSize
from app.models.task import TaskStatus
from app.services.feature_service import featureService
from app.services.speed_meter import speedMeter
from app.services.task_service import taskService
from app.view.cards.task_cards import TaskCard
from app.view.components.labels import IconBodyLabel

if TYPE_CHECKING:
    from app.models.task import Task


class FilterMode(IntEnum):
    ALL = 0
    ACTIVE = 1
    COMPLETED = 2


FILTER_TO_STATUSES = {
    FilterMode.ACTIVE: {TaskStatus.RUNNING, TaskStatus.WAITING, TaskStatus.PAUSED},
    FilterMode.COMPLETED: {TaskStatus.COMPLETED, TaskStatus.FAILED},
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

    def __init__(self, parent=None):
        super().__init__(parent)
        self._filterMode = FilterMode.ALL
        self._categoryFilter = ""
        self._sortField = SortField.CREATED_AT
        self._sortAscending = False
        self._searchText = ""
        self._selectionMode = False
        self._selectionAnchor: str | None = None
        self._cards: dict[str, TaskCard] = {}
        self._displayOrder: list[str] = []
        self._mounted: set[str] = set()

        self._rebuildTimer = QTimer(self, singleShot=True)
        self._rebuildTimer.setInterval(0)
        self._rebuildTimer.timeout.connect(self._rebuildList)

        self.scrollArea = ScrollArea(self)
        self.scrollWidget = QWidget(self)
        self.emptyStatusWidget = EmptyStatusWidget(FluentIcon.EMOJI_TAB_SYMBOLS, self.tr("暂无下载任务"), self)

        # toolbar
        self.toolBar = QWidget(self)
        self.startAllButton = PrimaryPushButton(FluentIcon.PLAY, self.tr("全部开始"), self.toolBar)
        self.pauseAllButton = PushButton(FluentIcon.PAUSE, self.tr("全部暂停"), self.toolBar)
        self.selectButton = ToolButton(FluentIcon.CLEAR_SELECTION, self.toolBar)
        self.planButton = ToggleToolButton(FluentIcon.DATE_TIME, self.toolBar)
        self.rateLimitButton = ToggleToolButton(FluentIcon.SPEED_OFF, self.toolBar)
        self.speedBadge = IconBodyLabel("0.00B/s", FluentIcon.SPEED_HIGH, self.toolBar)
        self.sortButton = DropDownToolButton(FluentIcon.LAYOUT, self.toolBar)
        self.filterButton = DropDownToolButton(FluentIcon.FILTER, self.toolBar)
        self.categoryFilterButton = DropDownToolButton(FluentIcon.TAG, self.toolBar)
        self.searchLineEdit = SearchLineEdit(self.toolBar)

        # sort menu
        self.sortMenu = CheckableMenu(parent=self, indicatorType=MenuIndicatorType.RADIO)
        self.sortFieldGroup = QActionGroup(self)
        self.sortOrderGroup = QActionGroup(self)
        self.createdAtSortAction = Action(FluentIcon.DATE_TIME, self.tr("按添加时间"), self, checkable=True)
        self.completedAtSortAction = Action(FluentIcon.HISTORY, self.tr("按完成时间"), self, checkable=True)
        self.nameSortAction = Action(FluentIcon.FONT, self.tr("按名称排序"), self, checkable=True)
        self.ascendingAction = Action(FluentIcon.UP, self.tr("顺序"), self, checkable=True)
        self.descendingAction = Action(FluentIcon.DOWN, self.tr("倒序"), self, checkable=True)

        # filter menu
        self.filterMenu = CheckableMenu(parent=self, indicatorType=MenuIndicatorType.RADIO)
        self.filterGroup = QActionGroup(self)
        self.allFilterAction = Action(FluentIcon.FILTER, self.tr("全部任务"), self, checkable=True)
        self.activeFilterAction = Action(FluentIcon.DOWNLOAD, self.tr("活动任务"), self, checkable=True)
        self.completedFilterAction = Action(FluentIcon.TRAIN, self.tr("完成任务"), self, checkable=True)

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
        self.sortOrderGroup.addAction(self.ascendingAction)
        self.sortOrderGroup.addAction(self.descendingAction)
        self.sortMenu.addAction(self.createdAtSortAction)
        self.sortMenu.addAction(self.completedAtSortAction)
        self.sortMenu.addAction(self.nameSortAction)
        self.sortMenu.addSeparator()
        self.sortMenu.addAction(self.ascendingAction)
        self.sortMenu.addAction(self.descendingAction)
        self.sortButton.setMenu(self.sortMenu)
        self.createdAtSortAction.setChecked(True)
        self.descendingAction.setChecked(True)

        self.filterGroup.addAction(self.allFilterAction)
        self.filterGroup.addAction(self.activeFilterAction)
        self.filterGroup.addAction(self.completedFilterAction)
        self.filterMenu.addAction(self.allFilterAction)
        self.filterMenu.addAction(self.activeFilterAction)
        self.filterMenu.addAction(self.completedFilterAction)
        self.filterButton.setMenu(self.filterMenu)
        self.allFilterAction.setChecked(True)

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

        self.searchLineEdit.setPlaceholderText(self.tr("搜索任务"))
        self.searchLineEdit.setMinimumWidth(200)
        self.searchLineEdit.setMaximumWidth(300)

        self.emptyStatusWidget.setMinimumWidth(200)
        self.emptyStatusWidget.adjustSize()

        self._rebuildCategoryFilterMenu()

    def _initLayout(self) -> None:
        toolBarLayout = QHBoxLayout(self.toolBar)
        toolBarLayout.setContentsMargins(16, 10, 16, 10)
        toolBarLayout.addWidget(self.startAllButton)
        toolBarLayout.addWidget(self.pauseAllButton)
        toolBarLayout.addWidget(self.selectButton)
        toolBarLayout.addWidget(self.planButton)
        toolBarLayout.addWidget(self.rateLimitButton)
        toolBarLayout.addSpacing(10)
        toolBarLayout.addWidget(self.speedBadge)
        toolBarLayout.addStretch(1)
        toolBarLayout.addWidget(self.sortButton)
        toolBarLayout.addWidget(self.filterButton)
        toolBarLayout.addWidget(self.categoryFilterButton)
        toolBarLayout.addWidget(self.searchLineEdit)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.toolBar)
        layout.addWidget(self.scrollArea)

    def _bind(self) -> None:
        taskService.taskAdded.connect(self._onTaskAdded)
        taskService.taskRemoved.connect(self._onTaskRemoved)
        for signal in (taskService.taskStarted, taskService.taskPaused,
                       taskService.taskCompleted, taskService.taskFailed):
            signal.connect(self._refreshVisibleCards)
        taskService.fileDisappeared.connect(self._onFileDisappeared)
        speedMeter.speedChanged.connect(self._onSpeedChanged)
        self.scrollArea.verticalScrollBar().valueChanged.connect(self._refreshViewport)

        self.startAllButton.clicked.connect(self.startAll)
        self.pauseAllButton.clicked.connect(self.pauseAll)
        self.selectButton.clicked.connect(lambda: self.setSelectionMode(not self._selectionMode))
        self.planButton.clicked.connect(self._onPlanButtonClicked)
        self.rateLimitButton.clicked.connect(self._onRateLimitToggled)

        self.createdAtSortAction.triggered.connect(lambda: self.setSortField(SortField.CREATED_AT))
        self.completedAtSortAction.triggered.connect(lambda: self.setSortField(SortField.COMPLETED_AT))
        self.nameSortAction.triggered.connect(lambda: self.setSortField(SortField.NAME))
        self.ascendingAction.triggered.connect(lambda: self.setSortOrder(True))
        self.descendingAction.triggered.connect(lambda: self.setSortOrder(False))

        self.allFilterAction.triggered.connect(lambda: self.setFilterMode(FilterMode.ALL))
        self.activeFilterAction.triggered.connect(lambda: self.setFilterMode(FilterMode.ACTIVE))
        self.completedFilterAction.triggered.connect(lambda: self.setFilterMode(FilterMode.COMPLETED))

        self.searchLineEdit.textChanged.connect(self.setSearchText)
        self.searchLineEdit.clearSignal.connect(lambda: self.setSearchText(""))

        self.commandView.redownloadAction.triggered.connect(self._onRedownloadSelected)
        self.commandView.deleteAction.triggered.connect(self._onDeleteSelected)
        self.commandView.moveCategoryAction.triggered.connect(self._onMoveCategorySelected)
        self.commandView.selectAllAction.triggered.connect(self.selectAll)
        self.commandView.selectMissingAction.triggered.connect(self.selectMissing)
        self.commandView.invertSelectAction.triggered.connect(self.invertSelection)
        self.commandView.cancelAction.triggered.connect(lambda: self.setSelectionMode(False))

        cfg.isCategoryEnabled.valueChanged.connect(self._onCategoryEnabledChanged)
        from app.services.category_service import categoryService
        categoryService.categoriesChanged.connect(self._rebuildCategoryFilterMenu)

        for task in taskService.tasks:
            self._onTaskAdded(task)

    # ── intent methods ──

    def setFilterMode(self, mode: FilterMode) -> None:
        self._filterMode = mode
        self._rebuildList()

    def setCategoryFilter(self, categoryId: str) -> None:
        self._categoryFilter = categoryId
        self._rebuildList()

    def setSortField(self, field: SortField) -> None:
        self._sortField = field
        self._rebuildList()

    def setSortOrder(self, ascending: bool) -> None:
        self._sortAscending = ascending
        self._rebuildList()

    def setSearchText(self, text: str) -> None:
        self._searchText = text
        self._rebuildList()

    def startAll(self) -> None:
        taskService.startAll()

    def pauseAll(self) -> None:
        taskService.pauseAll()

    def selectAll(self) -> None:
        for taskId in self._displayOrder:
            card = self._cards.get(taskId)
            if card:
                card.setChecked(True)

    def invertSelection(self) -> None:
        for taskId in self._displayOrder:
            card = self._cards.get(taskId)
            if card:
                card.setChecked(not card.isChecked())

    def selectMissing(self) -> None:
        for taskId in self._displayOrder:
            card = self._cards.get(taskId)
            if card:
                card.setChecked(card._fileMissing)

    def setSelectionMode(self, enter: bool) -> None:
        if self._selectionMode == enter:
            return
        self._selectionMode = enter
        self._selectionAnchor = None
        for card in self._cards.values():
            card.setSelectionMode(enter)
            if not enter:
                card.setChecked(False)
        self.commandView.setVisible(enter)
        if enter:
            self.commandView.raise_()

    def _onCardSelectionChanged(self, taskId: str, checked: bool, extend: bool) -> None:
        if not self._selectionMode:
            self.setSelectionMode(True)

        if extend and self._selectionAnchor:
            try:
                anchorIdx = self._displayOrder.index(self._selectionAnchor)
                currentIdx = self._displayOrder.index(taskId)
            except ValueError:
                return
            for tid in self._displayOrder:
                card = self._cards.get(tid)
                if card:
                    card.setChecked(False)
            for i in range(min(anchorIdx, currentIdx), max(anchorIdx, currentIdx) + 1):
                card = self._cards.get(self._displayOrder[i])
                if card:
                    card.setChecked(True)
        else:
            card = self._cards.get(taskId)
            if card:
                card.setChecked(checked)
            if checked:
                self._selectionAnchor = taskId
            elif taskId == self._selectionAnchor:
                self._selectionAnchor = None

        if not any(c.isChecked() for c in self._cards.values()):
            self.setSelectionMode(False)

    @property
    def isSelectionMode(self) -> bool:
        return self._selectionMode

    @property
    def isSortAscending(self) -> bool:
        return self._sortAscending

    # ── toolbar handlers ──

    def _onSpeedChanged(self, speed: int) -> None:
        self.speedBadge.setText(f"{toReadableSize(speed)}/s")
        self._refreshVisibleCards()

    def _onRateLimitToggled(self) -> None:
        cfg.set(cfg.isSpeedLimitEnabled, self.rateLimitButton.isChecked())

    def _onPlanButtonClicked(self) -> None:
        from app.services.plan import plan
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
        from app.services.category_service import categoryService
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
        for category in categoryService.categories():
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
            self._rebuildList()

        if not self._categoryFilter:
            allAction.setChecked(True)

    def _onRedownloadSelected(self) -> None:
        for taskId in list(self._displayOrder):
            card = self._cards.get(taskId)
            if card and card.isChecked():
                taskService.redownload(card.task)
        self.setSelectionMode(False)

    def _onDeleteSelected(self) -> None:
        from qfluentwidgets import CheckBox, MessageBox
        dialog = MessageBox(self.tr("删除任务"), self.tr("确定要删除选中的下载任务吗？"), self.window())
        deleteFiles = CheckBox(self.tr("同时删除已下载的文件"))
        dialog.textLayout.addWidget(deleteFiles)
        if dialog.exec():
            self._onDeleteConfirmed(deleteFiles.isChecked())

    def _onMoveCategorySelected(self) -> None:
        from app.services.category_service import categoryService
        targets = [
            card.task for taskId in self._displayOrder
            if (card := self._cards.get(taskId)) and card.isChecked()
        ]
        if not targets:
            return

        def moveTo(categoryId):
            for task in targets:
                taskService.setCategory(task, categoryId)
            self.setSelectionMode(False)
            self._rebuildList()

        popup = RoundMenu(parent=self)
        uncategorized = Action(FluentIcon.MORE, self.tr("未分类"), self)
        uncategorized.triggered.connect(lambda: moveTo(""))
        popup.addAction(uncategorized)
        popup.addSeparator()
        for category in categoryService.categories():
            cid = category.categoryId
            action = Action(category.toIcon(), category.name, self)
            action.triggered.connect(lambda checked=False, c=cid: moveTo(c))
            popup.addAction(action)
        popup.exec(QCursor.pos())

    def _onDeleteConfirmed(self, shouldDeleteFiles: bool) -> None:
        toDelete = [
            taskId for taskId in self._displayOrder
            if (card := self._cards.get(taskId)) and card.isChecked()
        ]
        for taskId in toDelete:
            task = taskService.taskById(taskId)
            if task:
                taskService.delete(task, shouldDeleteFiles)
        self.setSelectionMode(False)

    # ── list management ──

    def _rebuildList(self) -> None:
        tasks = taskService.tasks

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
        stride = TaskCard.ROW_HEIGHT + self.ROW_SPACING
        count = len(self._displayOrder)
        self.scrollWidget.setFixedHeight(
            count * stride - self.ROW_SPACING + self.BOTTOM_PADDING if count else 0
        )
        self._refreshViewport()

        if self._displayOrder:
            self.emptyStatusWidget.hide()
        else:
            if not self._cards:
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

    def _refreshViewport(self) -> None:
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

        desired: set[str] = set()
        for idx in range(first, last + 1):
            taskId = self._displayOrder[idx]
            card = self._cards.get(taskId)
            if card is None:
                continue
            card.setGeometry(self.SIDE_PADDING, idx * stride, max(0, width - 2 * self.SIDE_PADDING), TaskCard.ROW_HEIGHT)
            if taskId not in self._mounted:
                card.refresh()
            card.show()
            desired.add(taskId)

        for taskId in self._mounted - desired:
            card = self._cards.get(taskId)
            if card is not None:
                card.hide()
        self._mounted = desired

    def _refreshVisibleCards(self) -> None:
        for taskId in self._mounted:
            card = self._cards.get(taskId)
            if card is not None:
                card.refresh()

    # ── events ──

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
        return featureService.taskCard(task, self.scrollWidget)

    def _onTaskAdded(self, task: Task) -> None:
        if task.taskId in self._cards:
            return
        card = self._createCard(task)
        if card is None:  # 该任务所属 pack 不可用, 跳过渲染
            return
        card.hide()
        self._cards[task.taskId] = card
        card.setSelectionMode(self._selectionMode)
        card.selectionChanged.connect(
            lambda checked, extend, tid=task.taskId: self._onCardSelectionChanged(tid, checked, extend)
        )
        self._rebuildTimer.start()

    def _onTaskRemoved(self, taskId: str) -> None:
        card = self._cards.pop(taskId, None)
        if card is not None:
            card.hide()
            card.deleteLater()
        self._mounted.discard(taskId)
        if self._selectionAnchor == taskId:
            self._selectionAnchor = None
        self._rebuildTimer.start()

    def _onFileDisappeared(self, task: Task) -> None:
        card = self._cards.get(task.taskId)
        if card is not None:
            card.refresh(force=True)
