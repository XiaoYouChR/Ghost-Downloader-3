from __future__ import annotations

from urllib.parse import urlparse

from app.client import buildClient
from app.config.cfg import ConfigItem
from app.models.pack import PackConfig
from qfluentwidgets import BoolValidator, ComboBox, ConfigValidator, FluentIcon, LineEdit, SettingCard, ToolButton, ToolTipFilter

GITHUB_PROXY_SITES = (
    "https://gh-proxy.com",
    "https://gh-proxy.org",
    "https://gh.ddlc.top",
    "https://ghfast.top",
)
CUSTOM_SITE_KEY = "__custom__"
PROBE_TARGET = "https://github.com/cli/cli/releases/download/v2.62.0/gh_2.62.0_linux_amd64.tar.gz"


def toProxySite(site: str) -> str:
    value = str(site or "").strip()
    if not value:
        return ""
    if "://" not in value:
        value = f"https://{value}"
    return value.rstrip("/")


def selectedProxySite() -> str:
    if githubConfig.selectedSite.value == CUSTOM_SITE_KEY:
        return githubConfig.customSite.value
    return githubConfig.selectedSite.value


PROBE_UNAVAILABLE = -1
PROBE_TIMEOUT = -2


async def probeProxyLatencies() -> dict[str, int]:
    import asyncio
    from time import perf_counter

    sites = list(GITHUB_PROXY_SITES)
    custom = githubConfig.customSite.value
    if custom:
        sites.append(custom)

    async def probeOne(site: str) -> tuple[str, int]:
        url = f"{site.rstrip('/')}/{PROBE_TARGET}"
        client = buildClient()
        try:
            start = perf_counter()
            response = await asyncio.wait_for(client.head(url), timeout=10)
            elapsed = int((perf_counter() - start) * 1000)
            return site, elapsed if response.status.as_int() < 400 else PROBE_UNAVAILABLE
        except (asyncio.TimeoutError, TimeoutError):
            return site, PROBE_TIMEOUT
        except Exception:
            return site, PROBE_TIMEOUT
        finally:
            client.close()

    results = await asyncio.gather(*(probeOne(s) for s in sites))
    return dict(results)


class GitHubProxySiteValidator(ConfigValidator):
    def validate(self, value) -> bool:
        site = toProxySite(value)
        if not site:
            return False
        parsed = urlparse(site)
        return (
            parsed.scheme in {"http", "https"}
            and bool(parsed.netloc)
            and not parsed.params
            and not parsed.query
            and not parsed.fragment
        )

    def correct(self, value) -> str:
        site = toProxySite(value)
        return site if self.validate(site) else ""


class GitHubProxySiteCard(SettingCard):
    def __init__(self, parent=None):
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
        from app.services.coroutine_runner import coroutineRunner

        coroutineRunner.submit(
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


class GitHubConfig(PackConfig):
    enabled = ConfigItem("GitHub", "Enabled", True, BoolValidator())
    selectedSite = ConfigItem("GitHub", "SelectedSite", GITHUB_PROXY_SITES[0], GitHubProxySiteValidator())
    customSite = ConfigItem("GitHub", "CustomSite", "", GitHubProxySiteValidator())

    def settingGroups(self, parent: QWidget) -> list[CollapsibleSettingCardGroup]:
        from qfluentwidgets import FluentIcon, SwitchSettingCard
        from app.view.components.setting_card_group import CollapsibleSettingCardGroup

        githubGroup = CollapsibleSettingCardGroup(self.tr("GitHub 加速"), "github", parent)
        enableCard = SwitchSettingCard(
            FluentIcon.LINK, self.tr("启用 GitHub 加速"),
            self.tr("命中 GitHub 文件链接时，自动改写为所选反向代理站"),
            self.enabled, githubGroup,
        )
        proxySiteCard = GitHubProxySiteCard(githubGroup)

        githubGroup.addSettingCards([enableCard, proxySiteCard])
        return [githubGroup]


githubConfig = GitHubConfig()
