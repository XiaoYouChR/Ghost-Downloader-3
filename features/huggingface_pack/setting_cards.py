"""HuggingFace 加速的设置卡片（View）。config.py 只留配置数据。"""
from __future__ import annotations

from urllib.parse import urlparse

from qfluentwidgets import (
    ComboBox, FluentIcon, HyperlinkButton, LineEdit, PasswordLineEdit,
    SettingCard, ToolButton, ToolTipFilter,
)

from .config import (
    CUSTOM_SITE_KEY,
    HF_PROXY_SITES,
    TOKEN_URL,
    huggingFaceConfig,
    probeProxyLatencies,
)


class HuggingFaceProxySiteCard(SettingCard):
    def __init__(self, submit, parent=None):
        self.submit = submit
        super().__init__(
            FluentIcon.GLOBE, self.tr("镜像站"),
            self.tr("选择 HuggingFace 镜像站，延迟仅供参考"), parent,
        )
        self._latencies: dict[str, int | None] = {s: None for s in HF_PROXY_SITES}
        self._isRefreshing = False
        self.comboBox = ComboBox(self)
        self.customSiteEdit = LineEdit(self)
        self.refreshButton = ToolButton(FluentIcon.SYNC, self)

        self._initWidget()
        self._initLayout()
        self._bind()

    def _initWidget(self) -> None:
        self.comboBox.setMinimumWidth(260)
        self.customSiteEdit.setPlaceholderText("https://example.com/")
        self.customSiteEdit.setClearButtonEnabled(True)
        self.customSiteEdit.setMinimumWidth(220)
        self.refreshButton.setToolTip(self.tr("刷新延迟"))
        self.refreshButton.installEventFilter(ToolTipFilter(self.refreshButton))

        for site in HF_PROXY_SITES:
            self.comboBox.addItem(urlparse(site).netloc or site.rstrip("/"))
        self.comboBox.addItem(self.tr("自定义"))

        currentSite = huggingFaceConfig.selectedSite.value
        if currentSite == CUSTOM_SITE_KEY:
            self.comboBox.setCurrentIndex(len(HF_PROXY_SITES))
        elif currentSite in HF_PROXY_SITES:
            self.comboBox.setCurrentIndex(HF_PROXY_SITES.index(currentSite))
        else:
            self.comboBox.setCurrentIndex(0)
        self.customSiteEdit.setText(huggingFaceConfig.customSite.value)
        self.customSiteEdit.setVisible(currentSite == CUSTOM_SITE_KEY)

    def _initLayout(self) -> None:
        self.hBoxLayout.addWidget(self.comboBox)
        self.hBoxLayout.addSpacing(8)
        self.hBoxLayout.addWidget(self.customSiteEdit)
        self.hBoxLayout.addSpacing(8)
        self.hBoxLayout.addWidget(self.refreshButton)
        self.hBoxLayout.addSpacing(16)

    def _bind(self) -> None:
        self.comboBox.currentIndexChanged.connect(self._onCurrentIndexChanged)
        self.customSiteEdit.editingFinished.connect(self._onCustomSiteEditingFinished)
        self.refreshButton.clicked.connect(self.refreshLatencies)

    def _refreshLatencyLabels(self) -> None:
        for i, site in enumerate(HF_PROXY_SITES):
            displayName = urlparse(site).netloc or site.rstrip("/")
            latency = self._latencies.get(site)
            if latency is None:
                label = displayName
            elif latency < 0:
                label = f"{displayName} ({self.tr('超时')})"
            else:
                label = f"{displayName} ({latency} ms)"
            self.comboBox.setItemText(i, label)

        customSite = huggingFaceConfig.customSite.value
        customLatency = self._latencies.get(customSite) if customSite else None
        if customLatency is None:
            customLabel = self.tr("自定义")
        elif customLatency < 0:
            customLabel = f"{self.tr('自定义')} ({self.tr('超时')})"
        else:
            customLabel = f"{self.tr('自定义')} ({customLatency} ms)"
        self.comboBox.setItemText(len(HF_PROXY_SITES), customLabel)

    def _onCurrentIndexChanged(self, index: int) -> None:
        from app.config.cfg import cfg
        if index < 0:
            return
        if index < len(HF_PROXY_SITES):
            cfg.set(huggingFaceConfig.selectedSite, HF_PROXY_SITES[index])
        else:
            cfg.set(huggingFaceConfig.selectedSite, CUSTOM_SITE_KEY)
        self.customSiteEdit.setVisible(index >= len(HF_PROXY_SITES))

    def _onCustomSiteEditingFinished(self) -> None:
        from app.config.cfg import cfg
        cfg.set(huggingFaceConfig.customSite, self.customSiteEdit.text().strip())

    def refreshLatencies(self) -> None:
        if self._isRefreshing:
            return
        self._isRefreshing = True
        self._latencies = {s: None for s in HF_PROXY_SITES}
        self._refreshLatencyLabels()
        self.refreshButton.setEnabled(False)
        self.submit(
            probeProxyLatencies(),
            done=self._onLatenciesDone, failed=self._onLatenciesFailed,
            owner=self,
        )

    def _onLatenciesDone(self, latencies: dict[str, int]) -> None:
        self._isRefreshing = False
        self.refreshButton.setEnabled(True)
        self._latencies.update(latencies)
        self._refreshLatencyLabels()

    def _onLatenciesFailed(self, error) -> None:
        self._isRefreshing = False
        self.refreshButton.setEnabled(True)


class HuggingFaceTokenCard(SettingCard):
    def __init__(self, parent=None):
        super().__init__(
            FluentIcon.FINGERPRINT, self.tr("Access Token"),
            self.tr("用于下载需要授权的模型（如 Llama、Mistral）"), parent,
        )
        self.tokenEdit = PasswordLineEdit(self)
        self.tokenEdit.setPlaceholderText("hf_xxxxxxxxxxxx")
        self.tokenEdit.setMinimumWidth(240)
        self.tokenEdit.setText(huggingFaceConfig.accessToken.value)
        self.openTokenPageButton = HyperlinkButton(self)
        self.openTokenPageButton.setText(self.tr("获取 Token"))
        self.openTokenPageButton.setUrl(TOKEN_URL)

        self.hBoxLayout.addWidget(self.tokenEdit)
        self.hBoxLayout.addSpacing(8)
        self.hBoxLayout.addWidget(self.openTokenPageButton)
        self.hBoxLayout.addSpacing(16)

        self.tokenEdit.editingFinished.connect(self._onTokenEdited)

    def _onTokenEdited(self) -> None:
        from app.config.cfg import cfg
        cfg.set(huggingFaceConfig.accessToken, self.tokenEdit.text().strip())


