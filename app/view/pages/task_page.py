from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QPainter, QColor
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QGraphicsDropShadowEffect
from qfluentwidgets import ScrollArea, PrimaryPushButton, FluentIcon, PushButton, \
    SearchLineEdit, ToolButton, ToggleToolButton, ToolTipFilter, Action, \
    CommandBarView, isDarkTheme, IconWidget, CaptionLabel, CheckableMenu, MenuIndicatorType, \
    DropDownToolButton

from app.bases.models import TaskStatus
from app.supports.recorder import taskRecorder
from app.view.components.cards import TaskCard
from app.view.components.labels import IconBodyLabel
from features.http_pack.cards import HttpTaskCard


class TaskCommandBarView(CommandBarView):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.openAction = Action(FluentIcon.FOLDER, self.tr("打开文件夹"), self)
        self.redownloadAction = Action(FluentIcon.UPDATE, self.tr("重新下载"), self)
        self.deleteAction = Action(FluentIcon.DELETE, self.tr("删除"), self)
        self.selectAllAction = Action(FluentIcon.CLEAR_SELECTION, self.tr("全选"), self)
        self.cancelAction = Action(FluentIcon.CLEAR_SELECTION, self.tr("取消全选"), self)

        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.setIconSize(QSize(18, 18))
        self.addAction(self.openAction)
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


class TaskPage(ScrollArea):

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.cards = []

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
        self.timeSortAction = Action(FluentIcon.DATE_TIME, self.tr('按时间排序'), self, checkable=True)
        self.nameSortAction = Action(FluentIcon.FONT, self.tr('按名称排序'), self, checkable=True)
        self.ascendingSortAction = Action(FluentIcon.UP, self.tr('顺序'), self, checkable=True)
        self.reverseSortAction = Action(FluentIcon.DOWN, self.tr('倒序'), self, checkable=True)
        self.filterButton = DropDownToolButton(FluentIcon.FILTER, self)
        self.filterMenu = CheckableMenu(parent=self, indicatorType=MenuIndicatorType.RADIO)
        self.noFilterAction = Action(FluentIcon.FILTER, self.tr('全部任务'), self, checkable=True)
        self.activeFilterAction = Action(FluentIcon.DOWNLOAD, self.tr('活动任务'), self, checkable=True)
        self.completedFilterAction = Action(FluentIcon.TRAIN, self.tr('完成任务'), self, checkable=True)
        self.searchLineEdit = SearchLineEdit(self)
        # other widgets
        self.commandView = TaskCommandBarView(self)
        self.emptyStatusWidget = EmptyStatusWidget(FluentIcon.EMOJI_TAB_SYMBOLS, self.tr("暂无下载任务"), self)

        self.initWidget()
        self.initLayout()
        self.resumeMemorizedTasks()

        self.timeSortAction.setChecked(True)
        self.reverseSortAction.setChecked(True)
        self.noFilterAction.setChecked(True)
        # self.emptyStatusWidget.hide()
        self.refreshTimer = QTimer(self, interval=1000)
        self.refreshTimer.timeout.connect(self.refreshTaskCards)
        self.refreshTimer.start()

    def resumeMemorizedTasks(self):
        for task in taskRecorder.memorizedTasks.values():
            card = HttpTaskCard(task, self)
            if task.status == TaskStatus.RUNNING:
                card.resumeTask()
            self.addCard(card)

    def refreshTaskCards(self):
        for card in self.cards:
            card.refresh()

    def addCard(self, card: TaskCard):
        card.deleted.connect(lambda: self.removeCard(card))
        self.cards.append(card)
        self.viewLayout.addWidget(card, alignment=Qt.AlignmentFlag.AlignTop)

        if self.emptyStatusWidget.isVisible():
            self.emptyStatusWidget.hide()

    def removeCard(self, card: TaskCard):
        self.cards.remove(card)
        self.viewLayout.removeWidget(card)

        if not self.cards:
            self.emptyStatusWidget.show()

    def initWidget(self):
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setWidget(self.container)
        self.setObjectName("TaskPage")
        self.setWidgetResizable(True)
        self.enableTransparentBackground()
        self.setViewportMargins(0, 60, 0, 0)
        # Tool Bar
        self.sortMenu.addAction(self.timeSortAction)
        self.sortMenu.addAction(self.nameSortAction)
        self.sortMenu.addSeparator()
        self.sortMenu.addAction(self.ascendingSortAction)
        self.sortMenu.addAction(self.reverseSortAction)
        self.sortButton.setMenu(self.sortMenu)

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
        self.searchLineEdit.setPlaceholderText(self.tr("搜索任务"))

    def initLayout(self):
        self.vBoxLayout.setSpacing(20)
        self.vBoxLayout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.viewLayout.setContentsMargins(12, 0, 12, 12)
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

    def resizeEvent(self, event):
        super().resizeEvent(event)
        width = self.width()
        height = self.height()
        self.commandView.move((width - self.commandView.width()) >> 1, height - self.commandView.sizeHint().height() - 20)
        self.emptyStatusWidget.move((width - self.emptyStatusWidget.width()) >> 1, (height - self.emptyStatusWidget.height()) >> 1)
