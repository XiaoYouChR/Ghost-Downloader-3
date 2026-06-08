"""移动端任务页 —— 子类化 TaskPage: 挂载卡片套窄屏 mixin、头部单行工具栏(min 795px)拆两行、多选命令栏压进屏内。"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QWidget
from qfluentwidgets import FluentIcon, PrimaryToolButton, ToolButton

from app.bases.models import Task
from app.services.feature_service import featureService
from app.view.components.cards import TaskCard
from app.view.mobile.cards import MobileCardMixin, MobileFtpMixin
from app.view.pages.task_page import TaskPage


class MobileTaskPage(TaskPage):

    def __init__(self, parent=None, onSelectionModeChanged=None):
        self._mobileCardClasses: dict[type, type] = {}  # Task 子类 → 合成的移动端卡类(缓存)
        self._onSelectionModeChanged = onSelectionModeChanged  # 多选切换时回调(让 owner 收起 FAB)
        super().__init__(parent)

    def setSelectionMode(self, enter: bool):
        super().setSelectionMode(enter)
        # 多选命令栏浮在右下、会与「新建任务」FAB 撞位(还挡住其 ⋯ 溢出); 通知 owner 据多选态收 FAB
        if self._onSelectionModeChanged is not None:
            self._onSelectionModeChanged()

    def _initWidget(self):
        super()._initWidget()
        self.toolBar2 = QWidget(self)
        self.toolBar2Layout = QHBoxLayout(self.toolBar2)
        self.setViewportMargins(0, 104, 0, 0)  # 两行头部各 ~46px

        # 全开/全停换图标化 ToolButton: PushButton 清空文字后图标会顶向左、右留空位渲染不全。
        # 替换在基类 _bind 之前, _bind 接的就是这俩新按钮。
        for old in (self.allStartButton, self.allPauseButton):
            old.hide()  # deleteLater 是异步的; 不先 hide, 未入布局的旧按钮会暂留 (0,0) 被绘制
            old.deleteLater()
        self.allStartButton = PrimaryToolButton(FluentIcon.PLAY, self)
        self.allPauseButton = ToolButton(FluentIcon.PAUSE, self)
        self.allStartButton.setToolTip(self.tr("全部开始"))
        self.allPauseButton.setToolTip(self.tr("全部暂停"))

        self.selectButton.hide()  # 移动端长按进多选, 砍掉桌面「选择」按钮

    def _initLayout(self):
        self.vBoxLayout.setSpacing(6)
        self.vBoxLayout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.vBoxLayout.addWidget(self.toolBar)
        self.vBoxLayout.addWidget(self.toolBar2)

        # 行1: 全开 全停 速度 | 限速 计划
        self.toolBarLayout.setContentsMargins(10, 4, 10, 0)
        self.toolBarLayout.setSpacing(6)
        self.toolBarLayout.addWidget(self.allStartButton)
        self.toolBarLayout.addWidget(self.allPauseButton)
        self.toolBarLayout.addWidget(self.speedBadge)
        self.toolBarLayout.addStretch(1)
        self.toolBarLayout.addWidget(self.rateLimitButton)
        self.toolBarLayout.addWidget(self.planButton)

        # 行2: 排序 筛选 分类 搜索(占满)
        self.toolBar2Layout.setContentsMargins(10, 0, 10, 4)
        self.toolBar2Layout.setSpacing(6)
        self.toolBar2Layout.addWidget(self.sortButton)
        self.toolBar2Layout.addWidget(self.filterButton)
        self.toolBar2Layout.addWidget(self.categoryFilterButton)
        self.toolBar2Layout.addWidget(self.searchLineEdit, 1)

        self.searchLineEdit.setMinimumWidth(0)
        self.searchLineEdit.setMaximumWidth(16777215)

    def resizeEvent(self, event):
        self._fitCommandView()  # 先按当前页宽收窄多选命令栏, 再让基类按其新宽居中摆放
        super().resizeEvent(event)

    def _fitCommandView(self):
        """把多选命令栏宽度改设成 页宽-边距, 触发 CommandBar 把放不下的动作折进「⋯」菜单; 桌面按全宽固定了 bar, 窄屏会超出屏幕。"""
        bar = self.commandView.bar
        margin = 12  # CommandBarView hBoxLayout 左右各 6
        cap = max(self.width() - 24 - margin, bar.moreButton.width())
        width = min(bar.suitableWidth(), cap)
        bar.setFixedWidth(width)
        self.commandView.setFixedWidth(width + margin)

    def _mobileCardClass(self, task: Task) -> type:
        """取 task 对应的桌面卡类(探针构造一次拿到), 套上窄屏 mixin, 按 Task 子类缓存; 复用 featureService 分发而非硬编码一种卡, 否则各任务类型丢特性。"""
        taskType = type(task)
        cached = self._mobileCardClasses.get(taskType)
        if cached is not None:
            return cached

        probe = featureService.taskCard(task, None)
        baseClass = type(probe)
        probe.deleteLater()
        mixins = (MobileFtpMixin, MobileCardMixin) if task.packId == "ftp" else (MobileCardMixin,)
        mobileClass = type(f"Mobile{baseClass.__name__}", (*mixins, baseClass), {})

        self._mobileCardClasses[taskType] = mobileClass
        return mobileClass

    def _mountCard(self, task: Task) -> TaskCard:
        card = self._mobileCardClass(task)(task, self.container)
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
