from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    FluentIcon,
    InfoBar,
    LineEdit,
    MessageBoxBase,
    PrimaryPushButton,
    PushButton,
    SettingCard,
    SubtitleLabel,
    ToolButton,
    ToolTipFilter,
    TransparentToolButton,
)

from app.bootstrap_list import BootstrapList, SubscriptionStatus
from app.config.cfg import ConfigItem, cfg
from app.view.components.editors import AutoSizingEdit

FAILURE_NOTICE_AGE = 7 * 86400
CARD_HEIGHT = 70


def tr(text: str) -> str:
    return QCoreApplication.translate("BootstrapList", text)


def toAgoText(seconds: float) -> str:
    if seconds < 60:
        return tr("刚刚")
    if seconds < 3600:
        return tr("{0} 分钟前").format(int(seconds // 60))
    if seconds < 86400:
        return tr("{0} 小时前").format(int(seconds // 3600))
    return tr("{0} 天前").format(int(seconds // 86400))


def toStatusText(status: SubscriptionStatus | None) -> str:
    if status is None or status.count is None:
        return tr("更新失败") if status is not None and status.error else tr("未拉取")
    parts = [tr("{0} 条").format(status.count), tr("{0}更新").format(toAgoText(time.time() - status.updatedAt))]
    if status.error:
        parts.append(tr("更新失败"))
    return tr("，").join(parts)


def isSubscriptionUrl(url: str) -> bool:
    parts = urlsplit(url)
    return parts.scheme in {"http", "https"} and bool(parts.netloc)


class BootstrapListCard(SettingCard):
    def __init__(
        self,
        icon: FluentIcon,
        title: str,
        bootstrapList: BootstrapList,
        sourcesItem: ConfigItem,
        submit: Callable[..., str],
        parent=None,
        *,
        customItem: ConfigItem | None = None,
        probeNetworkText: Callable[[], Awaitable[str]] | None = None,
    ):
        super().__init__(icon, title, "", parent)
        self._list = bootstrapList
        self._sourcesItem = sourcesItem
        self._customItem = customItem
        self._submit = submit
        self._probeNetworkText = probeNetworkText
        self._networkText = ""
        self.manageButton = PrimaryPushButton(self.tr("管理"), self)
        self.refreshButton = ToolButton(FluentIcon.SYNC, self)

        self._initWidget()
        self._initLayout()
        self._bind()

    def _initWidget(self):
        self.setFixedHeight(CARD_HEIGHT)
        self.refreshButton.setToolTip(self.tr("立即更新"))
        self.refreshButton.installEventFilter(ToolTipFilter(self.refreshButton))
        if self._list.isRefreshing:
            self._startRefresh()
        else:
            self._refreshContent()
            self._probeNetwork()

    def _initLayout(self):
        self.hBoxLayout.addWidget(self.manageButton, 0)
        self.hBoxLayout.addSpacing(8)
        self.hBoxLayout.addWidget(self.refreshButton, 0)
        self.hBoxLayout.addSpacing(16)

    def _bind(self):
        self.manageButton.clicked.connect(self._onManageClicked)
        self.refreshButton.clicked.connect(self._startRefresh)

    def _refreshContent(self):
        if self._list.isRefreshing:
            self.setContent(self.tr("正在更新…"))
            return
        statuses = self._list.statuses()
        cached = [s for s in statuses if s.count is not None]
        parts = [self.tr("{0} 个订阅").format(len(statuses))]
        if cached:
            newest = max(s.updatedAt for s in cached)
            parts.append(self.tr("共 {0} 条").format(sum(s.count for s in cached)))
            parts.append(self.tr("{0}更新").format(toAgoText(time.time() - newest)))
            if any(s.error for s in statuses) and time.time() - newest > FAILURE_NOTICE_AGE:
                parts.append(self.tr("更新失败"))
        else:
            parts.append(self.tr("使用内置列表"))
            if any(s.error for s in statuses):
                parts.append(self.tr("更新失败"))
        if self._networkText:
            parts.append(self._networkText)
        self.setContent(self.tr("，").join(parts))

    def _probeNetwork(self):
        if self._probeNetworkText is not None:
            self._submit(self._probeNetworkText(), done=self._onNetworkProbed, owner=self)

    def _onNetworkProbed(self, text: str):
        self._networkText = text
        self._refreshContent()

    def _startRefresh(self):
        self.refreshButton.setEnabled(False)
        self._submit(self._list.refresh(), done=self._onRefreshed, failed=self._onRefreshed, owner=self)
        self._refreshContent()

    def _onRefreshed(self, _result=None):
        self.refreshButton.setEnabled(True)
        self._refreshContent()
        self._probeNetwork()

    def _onManageClicked(self):
        dialog = BootstrapListDialog(self._list, self._sourcesItem, self._customItem, self.window())
        try:
            if dialog.exec():
                self._startRefresh()
        finally:
            dialog.deleteLater()


class SubscriptionRow(QWidget):
    def __init__(self, url: str, statusText: str, onRemoved: Callable[[SubscriptionRow], None], parent=None):
        super().__init__(parent)
        self.urlEdit = LineEdit(self)
        self.statusLabel = BodyLabel(statusText, self)
        self.deleteButton = TransparentToolButton(FluentIcon.CLOSE, self)
        self.hBoxLayout = QHBoxLayout(self)
        self._onRemoved = onRemoved

        self._initWidget(url)
        self._initLayout()
        self._bind()

    @property
    def url(self) -> str:
        return self.urlEdit.text().strip()

    def _initWidget(self, url: str):
        self.urlEdit.setText(url)
        self.urlEdit.setPlaceholderText("https://")

    def _initLayout(self):
        self.hBoxLayout.setContentsMargins(0, 0, 0, 0)
        self.hBoxLayout.setSpacing(8)
        self.hBoxLayout.addWidget(self.urlEdit, 1)
        self.hBoxLayout.addWidget(self.statusLabel)
        self.hBoxLayout.addWidget(self.deleteButton)

    def _bind(self):
        self.deleteButton.clicked.connect(lambda: self._onRemoved(self))


class BootstrapListDialog(MessageBoxBase):
    def __init__(self, bootstrapList: BootstrapList, sourcesItem: ConfigItem,
                 customItem: ConfigItem | None, parent=None):
        super().__init__(parent)
        self._sourcesItem = sourcesItem
        self._customItem = customItem
        self._statuses = {s.url: s for s in bootstrapList.statuses()}
        self._rows: list[SubscriptionRow] = []
        self.sourceHeaderLabel = SubtitleLabel(self.tr("订阅地址"), self.widget)
        self.restoreButton = PushButton(self.tr("恢复默认"), self.widget)
        self.addButton = PrimaryPushButton(FluentIcon.ADD, self.tr("添加"), self.widget)
        self.rowContainer = QWidget(self.widget)
        self.customLabel = SubtitleLabel(self.tr("自定义条目"), self.widget)
        self.customEdit = AutoSizingEdit(self.widget)
        self.sourceHeaderLayout = QHBoxLayout()
        self.rowLayout = QVBoxLayout(self.rowContainer)

        self._initWidget()
        self._initLayout()
        self._bind()

    def _initWidget(self):
        self.widget.setMinimumWidth(720)
        self.yesButton.setText(self.tr("保存并更新"))
        self.cancelButton.setText(self.tr("取消"))
        for url in self._sourcesItem.value:
            self._addRow(url)
        self.customLabel.setVisible(self._customItem is not None)
        self.customEdit.setVisible(self._customItem is not None)
        if self._customItem is not None:
            self.customEdit.setPlaceholderText(self.tr("每行一个，不会被订阅更新覆盖"))
            self.customEdit.setPlainText(self._customItem.value)

    def _initLayout(self):
        self.sourceHeaderLayout.setContentsMargins(0, 0, 0, 0)
        self.sourceHeaderLayout.addWidget(self.sourceHeaderLabel)
        self.sourceHeaderLayout.addStretch(1)
        self.sourceHeaderLayout.addWidget(self.restoreButton)
        self.sourceHeaderLayout.addWidget(self.addButton)

        self.rowLayout.setContentsMargins(0, 0, 0, 0)
        self.rowLayout.setSpacing(8)

        self.viewLayout.addLayout(self.sourceHeaderLayout)
        self.viewLayout.addWidget(self.rowContainer)
        self.viewLayout.addSpacing(8)
        self.viewLayout.addWidget(self.customLabel)
        self.viewLayout.addWidget(self.customEdit)

    def _bind(self):
        self.addButton.clicked.connect(lambda: self._addRow(""))
        self.restoreButton.clicked.connect(self._onRestoreClicked)

    def validate(self) -> bool:
        for row in self._rows:
            if not isSubscriptionUrl(row.url):
                InfoBar.error(self.tr("订阅地址无效"), self.tr("请输入有效的 HTTP/HTTPS 地址"), parent=self)
                row.urlEdit.setFocus()
                return False
        cfg.set(self._sourcesItem, list(dict.fromkeys(row.url for row in self._rows)))
        if self._customItem is not None:
            lines = (line.strip() for line in self.customEdit.toPlainText().splitlines())
            cfg.set(self._customItem, "\n".join(line for line in lines if line))
        return True

    def _addRow(self, url: str):
        row = SubscriptionRow(url, toStatusText(self._statuses.get(url)), self._onRowRemoved, self.rowContainer)
        error = self._statuses[url].error if url in self._statuses else ""
        row.statusLabel.setToolTip(error)
        self.rowLayout.addWidget(row)
        self._rows.append(row)

    def _onRowRemoved(self, row: SubscriptionRow):
        self._rows.remove(row)
        self.rowLayout.removeWidget(row)
        row.deleteLater()

    def _onRestoreClicked(self):
        for row in list(self._rows):
            self._onRowRemoved(row)
        for url in self._sourcesItem.defaultValue:
            self._addRow(url)
