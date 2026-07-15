from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import FluentIcon, PrimaryToolButton, ToolButton

from app.models.task import Task
from app.view.cards.task_cards import TaskCard
from app.view.mobile.cards import MobileTaskCardBase
from app.view.pages.task_page import TaskPage


class MobileTaskPage(TaskPage):
    selectionModeChanged = Signal(bool)

    def __init__(self, parent=None):
        self._mobileCardTypes: dict[type, type] = {}
        super().__init__(parent)

    def setSelectionMode(self, enter: bool) -> None:
        super().setSelectionMode(enter)
        self.selectionModeChanged.emit(enter)

    def _bind(self) -> None:
        super()._bind()
        self._bandSelector.setEnabled(False)

    def _initWidget(self) -> None:
        super()._initWidget()
        # 桌面的文字按钮在窄屏太宽, 换图标按钮; 选择改长按触发, 收起 selectButton
        for old in (self.startAllButton, self.pauseAllButton):
            old.hide()
            old.deleteLater()
        self.startAllButton = PrimaryToolButton(FluentIcon.PLAY, self.toolBar)
        self.pauseAllButton = ToolButton(FluentIcon.PAUSE, self.toolBar)
        self.startAllButton.setToolTip(self.tr("全部开始"))
        self.pauseAllButton.setToolTip(self.tr("全部暂停"))
        self.selectButton.hide()

        self.filterToolBar = QWidget(self)

    def _initLayout(self) -> None:
        toolBarLayout = QHBoxLayout(self.toolBar)
        toolBarLayout.setContentsMargins(10, 4, 10, 0)
        toolBarLayout.setSpacing(6)
        toolBarLayout.addWidget(self.startAllButton)
        toolBarLayout.addWidget(self.pauseAllButton)
        toolBarLayout.addWidget(self.speedBadge)
        toolBarLayout.addStretch(1)
        toolBarLayout.addWidget(self.rateLimitButton)
        toolBarLayout.addWidget(self.planButton)

        filterToolBarLayout = QHBoxLayout(self.filterToolBar)
        filterToolBarLayout.setContentsMargins(10, 0, 10, 4)
        filterToolBarLayout.setSpacing(6)
        filterToolBarLayout.addWidget(self.filterSegment)
        filterToolBarLayout.addStretch(1)
        filterToolBarLayout.addWidget(self.sortButton)
        filterToolBarLayout.addWidget(self.categoryFilterButton)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self.toolBar)
        layout.addWidget(self.filterToolBar)
        layout.addWidget(self.scrollArea)

    def _createCard(self, task: Task) -> TaskCard | None:
        card = super()._createCard(task)
        if card is None:  # 该任务所属 pack 未打包(如 Android 排除的 ed2k)
            return None
        baseType = type(card)
        mobileType = self._mobileCardTypes.get(baseType)
        if mobileType is None:
            mobileType = type(f"Mobile{baseType.__name__}", (MobileTaskCardBase, baseType), {})
            self._mobileCardTypes[baseType] = mobileType
        card.__class__ = mobileType  # 套上移动 mixin: 同一 C++ 类型, 仅改 Python MRO
        card.setupMobile()
        return card

    def resizeEvent(self, event) -> None:
        self._fitCommandView()
        super().resizeEvent(event)

    def _fitCommandView(self) -> None:
        # 窄屏放不下整条命令栏, 收窄它好让溢出动作折进「更多」按钮
        bar = self.commandView.bar
        margin = 12
        widthLimit = max(self.width() - 24 - margin, bar.moreButton.width())
        width = min(bar.suitableWidth(), widthLimit)
        bar.setFixedWidth(width)
        self.commandView.setFixedWidth(width + margin)
