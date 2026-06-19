from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QWidget
from qfluentwidgets import FluentIcon, PrimaryToolButton, ToolButton

from app.bases.models import Task
from app.services.feature_service import featureService
from app.supports.android_notification import notifyDownloadComplete
from app.view.components.cards import TaskCard
from app.view.mobile.cards import MobileFtpTaskCardBase, MobileTaskCardBase
from app.view.pages.task_page import TaskPage

class MobileTaskPage(TaskPage):
    def __init__(self, parent=None, onSelectionModeChanged=None):
        self._mobileCardTypesByBaseType: dict[type[TaskCard], type[TaskCard]] = {}
        self._onSelectionModeChanged = onSelectionModeChanged
        super().__init__(parent)

    def setSelectionMode(self, enter: bool):
        super().setSelectionMode(enter)

        if self._onSelectionModeChanged is not None:
            self._onSelectionModeChanged()

    def _initWidget(self):
        super()._initWidget()
        self.filterToolBar = QWidget(self)
        self.filterToolBarLayout = QHBoxLayout(self.filterToolBar)
        self.setViewportMargins(0, 104, 0, 0)

        for old in (self.allStartButton, self.allPauseButton):
            old.hide()
            old.deleteLater()
        self.allStartButton = PrimaryToolButton(FluentIcon.PLAY, self)
        self.allPauseButton = ToolButton(FluentIcon.PAUSE, self)
        self.allStartButton.setToolTip(self.tr("全部开始"))
        self.allPauseButton.setToolTip(self.tr("全部暂停"))

        self.selectButton.hide()

    def _initLayout(self):
        self.vBoxLayout.setSpacing(6)
        self.vBoxLayout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.vBoxLayout.addWidget(self.toolBar)
        self.vBoxLayout.addWidget(self.filterToolBar)

        self.toolBarLayout.setContentsMargins(10, 4, 10, 0)
        self.toolBarLayout.setSpacing(6)
        self.toolBarLayout.addWidget(self.allStartButton)
        self.toolBarLayout.addWidget(self.allPauseButton)
        self.toolBarLayout.addWidget(self.speedBadge)
        self.toolBarLayout.addStretch(1)
        self.toolBarLayout.addWidget(self.rateLimitButton)
        self.toolBarLayout.addWidget(self.planButton)

        self.filterToolBarLayout.setContentsMargins(10, 0, 10, 4)
        self.filterToolBarLayout.setSpacing(6)
        self.filterToolBarLayout.addWidget(self.sortButton)
        self.filterToolBarLayout.addWidget(self.filterButton)
        self.filterToolBarLayout.addWidget(self.categoryFilterButton)
        self.filterToolBarLayout.addWidget(self.searchLineEdit, 1)

        self.searchLineEdit.setMinimumWidth(0)
        self.searchLineEdit.setMaximumWidth(16777215)

    def resizeEvent(self, event):
        self._fitCommandView()
        super().resizeEvent(event)

    def _fitCommandView(self):
        commandBar = self.commandView.bar
        margin = 12
        widthLimit = max(self.width() - 24 - margin, commandBar.moreButton.width())
        width = min(commandBar.suitableWidth(), widthLimit)
        commandBar.setFixedWidth(width)
        self.commandView.setFixedWidth(width + margin)

    def _mobileCardType(self, task: Task) -> type[TaskCard]:
        sampleCard = featureService.taskCard(task, None)
        try:
            baseCardType = type(sampleCard)
        finally:
            sampleCard.deleteLater()

        mobileCardType = self._mobileCardTypesByBaseType.get(baseCardType)
        if mobileCardType is not None:
            return mobileCardType

        mobileCardBases = (
            (MobileFtpTaskCardBase, MobileTaskCardBase)
            if task.packId == "ftp"
            else (MobileTaskCardBase,)
        )
        mobileCardType = type(f"Mobile{baseCardType.__name__}", (*mobileCardBases, baseCardType), {})

        self._mobileCardTypesByBaseType[baseCardType] = mobileCardType
        return mobileCardType

    def _onCardFinished(self):
        super()._onCardFinished()
        sender = self.sender()
        if isinstance(sender, TaskCard):
            notifyDownloadComplete(sender.task.taskId, self.tr("下载完成"), sender.task.title)

    def _mountCard(self, task: Task) -> TaskCard:
        cardType = self._mobileCardType(task)
        card = cardType(task, self.container)
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
