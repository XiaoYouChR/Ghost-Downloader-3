"""GitHub 加速的设置卡片（View）。config.py 只留配置数据。"""
from __future__ import annotations

from urllib.parse import urlparse

from qfluentwidgets import ComboBox, FluentIcon, LineEdit, SettingCard, ToolButton, ToolTipFilter

from .config import (
    CUSTOM_SITE_KEY,
    GITHUB_PROXY_SITES,
    PROBE_TIMEOUT,
    PROBE_UNAVAILABLE,
    githubConfig,
    probeProxyLatencies,
)


class GitHubProxySiteCard(SettingCard):
    def __init__(self, submit, parent=None):
        self.submit = submit
        super().__init__(
            FluentIcon.GLOBE, self.tr("代理站"),
            self.tr("选择 GitHub 反向代理站，延迟仅供参考"), parent,
        )
        self._latencies: dict[str, int | None] = {s: None for s in GITHUB_PROXY_SITES}
        self._isRefreshing = False
        self.comboBox = ComboBox(self)
        self.customSiteEdit = LineEdit(self)
        self.refreshButton = ToolButton(FluentIcon.SYNC, self)

        self._initWidget()
        self._initLayout()
        self._bind()

    def _initWidget(self):
        self.comboBox.setMinimumWidth(260)
        self.customSiteEdit.setPlaceholderText("https://example.com/")
        self.customSiteEdit.setClearButtonEnabled(True)
        self.customSiteEdit.setMinimumWidth(220)
        self.refreshButton.setToolTip(self.tr("刷新延迟"))
        self.refreshButton.installEventFilter(ToolTipFilter(self.refreshButton))

        for site in GITHUB_PROXY_SITES:
            self.comboBox.addItem(urlparse(site).netloc or site.rstrip("/"))
        self.comboBox.addItem(self.tr("自定义"))

        currentSite = githubConfig.selectedSite.value
        if currentSite == CUSTOM_SITE_KEY:
            self.comboBox.setCurrentIndex(len(GITHUB_PROXY_SITES))
        elif currentSite in GITHUB_PROXY_SITES:
            self.comboBox.setCurrentIndex(GITHUB_PROXY_SITES.index(currentSite))
        else:
            self.comboBox.setCurrentIndex(0)
        self.customSiteEdit.setText(githubConfig.customSite.value)
        self.customSiteEdit.setVisible(currentSite == CUSTOM_SITE_KEY)

    def _initLayout(self):
        self.hBoxLayout.addWidget(self.comboBox)
        self.hBoxLayout.addSpacing(8)
        self.hBoxLayout.addWidget(self.customSiteEdit)
        self.hBoxLayout.addSpacing(8)
        self.hBoxLayout.addWidget(self.refreshButton)
        self.hBoxLayout.addSpacing(16)

    def _bind(self):
        self.comboBox.currentIndexChanged.connect(self._onCurrentIndexChanged)
        self.customSiteEdit.editingFinished.connect(self._onCustomSiteEditingFinished)
        self.refreshButton.clicked.connect(self.refreshLatencies)

    def _latencyTag(self, latency: int | None) -> str:
        if latency is None:
            return ""
        if latency == PROBE_UNAVAILABLE:
            return self.tr("不可用")
        if latency == PROBE_TIMEOUT:
            return self.tr("超时")
        return f"{latency} ms"

    def _refreshLatencyLabels(self):
        for i, site in enumerate(GITHUB_PROXY_SITES):
            displayName = urlparse(site).netloc or site.rstrip("/")
            tag = self._latencyTag(self._latencies.get(site))
            label = f"{displayName} ({tag})" if tag else displayName
            self.comboBox.setItemText(i, label)

        customSite = githubConfig.customSite.value
        customLatency = self._latencies.get(customSite) if customSite else None
        tag = self._latencyTag(customLatency)
        customLabel = f"{self.tr('自定义')} ({tag})" if tag else self.tr("自定义")
        self.comboBox.setItemText(len(GITHUB_PROXY_SITES), customLabel)

    def _onCurrentIndexChanged(self, index: int):
        from app.config.cfg import cfg
        if index < 0:
            return
        if index < len(GITHUB_PROXY_SITES):
            cfg.set(githubConfig.selectedSite, GITHUB_PROXY_SITES[index])
        else:
            cfg.set(githubConfig.selectedSite, CUSTOM_SITE_KEY)
        self.customSiteEdit.setVisible(index >= len(GITHUB_PROXY_SITES))

    def _onCustomSiteEditingFinished(self):
        from app.config.cfg import cfg
        cfg.set(githubConfig.customSite, self.customSiteEdit.text().strip())

    def refreshLatencies(self):
        if self._isRefreshing:
            return
        self._isRefreshing = True
        self._latencies = {s: None for s in GITHUB_PROXY_SITES}
        self._refreshLatencyLabels()
        self.refreshButton.setEnabled(False)
        self.submit(
            probeProxyLatencies(),
            done=self._onLatenciesDone, failed=self._onLatenciesFailed,
            owner=self,
        )

    def _onLatenciesDone(self, latencies: dict[str, int]):
        self._isRefreshing = False
        self.refreshButton.setEnabled(True)
        self._latencies.update(latencies)
        self._refreshLatencyLabels()

    def _onLatenciesFailed(self, error):
        self._isRefreshing = False
        self.refreshButton.setEnabled(True)


