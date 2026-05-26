from qfluentwidgets import (
    FluentIcon,
    PrimaryPushButton,
    SettingCard,
    StateToolTip,
    ToolButton,
    ToolTipFilter,
)

from app.services.core_service import coreService

from .dialog import WebTrackerDialog
from .service import webTrackerService


class WebTrackerCard(SettingCard):

    def __init__(self, parent=None):
        super().__init__(
            FluentIcon.GLOBE,
            self.tr("Web Tracker"),
            "",
            parent,
        )
        # instant widget
        self.manageButton = PrimaryPushButton(self.tr("管理"), self)
        self.refreshButton = ToolButton(FluentIcon.SYNC, self)

        self._stateToolTip: StateToolTip | None = None

        self._initWidget()
        self._initLayout()
        self._bind()

    def refreshContent(self) -> None:
        sourceCount = len(webTrackerService.sourceUrls())
        cachedTotal = len(webTrackerService.mergedTrackers())
        self.setContent(
            self.tr("{0} 个源 · 共 {1} 条缓存").format(sourceCount, cachedTotal)
        )

    def _initWidget(self) -> None:
        self.refreshButton.setToolTip(self.tr("刷新缓存"))
        self.refreshButton.installEventFilter(ToolTipFilter(self.refreshButton))
        self.refreshContent()

    def _initLayout(self) -> None:
        self.hBoxLayout.addWidget(self.manageButton, 0)
        self.hBoxLayout.addSpacing(8)
        self.hBoxLayout.addWidget(self.refreshButton, 0)
        self.hBoxLayout.addSpacing(16)

    def _bind(self) -> None:
        self.manageButton.clicked.connect(self._onManageClicked)
        self.refreshButton.clicked.connect(self._refresh)
        webTrackerService.trackersChanged.connect(self.refreshContent)

    def _onManageClicked(self) -> None:
        dialog = WebTrackerDialog(self.window())
        try:
            if dialog.exec():
                self._refresh()
        finally:
            dialog.deleteLater()

    def _refresh(self) -> None:
        urls = webTrackerService.sourceUrls()
        if not urls:
            return

        self.refreshButton.setEnabled(False)
        self._stateToolTip = StateToolTip(
            self.tr("正在刷新 Web Tracker"),
            self.tr("正在拉取 {0} 个源...").format(len(urls)),
            self.window(),
        )
        self._stateToolTip.move(self._stateToolTip.getSuitablePos())
        self._stateToolTip.show()
        coreService.runCoroutine(webTrackerService.refresh(), self._onRefreshFinished)

    def _onRefreshFinished(self, result, error: str | None) -> None:
        self.refreshButton.setEnabled(True)
        if self._stateToolTip is None:
            return

        if error:
            self._stateToolTip.setContent(self.tr("刷新失败: {0}").format(error))
        else:
            success, total = result
            cachedTotal = len(webTrackerService.mergedTrackers())
            self._stateToolTip.setContent(
                self.tr("已刷新 {0}/{1} 个源,共 {2} 条 Tracker").format(
                    success, total, cachedTotal
                )
            )
        self._stateToolTip.setState(True)
        self._stateToolTip = None
