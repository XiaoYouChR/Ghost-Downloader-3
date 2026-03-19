import asyncio
from time import perf_counter
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from loguru import logger
import niquests
from PySide6.QtCore import Qt
from qfluentwidgets import (
    BoolValidator,
    ComboBox,
    ConfigItem,
    ConfigValidator,
    FluentIcon,
    HyperlinkButton,
    LineEdit,
    MessageBoxBase,
    OptionsConfigItem,
    OptionsValidator,
    PlainTextEdit,
    SettingCard,
    SettingCardGroup,
    SubtitleLabel,
    SwitchSettingCard,
    ToolButton,
    ToolTipFilter,
)

from app.bases.models import PackConfig
from app.services.core_service import coreService
from app.supports.config import cfg
from app.supports.utils import getProxies

if TYPE_CHECKING:
    from app.view.pages.setting_page import SettingPage


GITHUB_PROXY_SITES = (
    "https://gh-proxy.com/",
    "https://ghproxy.vip/",
    "https://ghproxy.homeboyc.cn/",
    "https://gh.llkk.cc/",
)
GITHUB_CUSTOM_PROXY_SITE = "__custom__"
GITHUB_PROBE_TARGET = "https://raw.githubusercontent.com/asjdf/ghproxy/main/src/index.ts"

GITHUB_USER_AGREEMENT = """使用前请确认以下风险并自行承担：

1. GitHub Pack 使用的是第三方 GitHub 反向代理站，这些站点并非由 Ghost Downloader 或 GitHub 官方运营。
2. 当你启用该功能后，请求会先经过你选定的代理站，代理站可能获取你的请求地址、IP、请求头等网络信息。
3. 请不要使用该功能下载包含 Cookie、Token、私有仓库鉴权信息、签名链接或其他敏感凭据的 GitHub 链接。
4. 第三方代理站可能出现内容篡改、缓存过期、服务中断、限流、劫持或记录访问日志等风险。
5. 对于重要文件，请在下载完成后自行校验哈希值、签名或文件来源，确认文件完整性与可信性。
6. 代理站的可用性、速度和合规性会随时变化；是否继续使用以及由此产生的后果，由你自行判断并负责。

继续启用即表示你已阅读、理解并同意以上内容。"""


def _siteName(site: str) -> str:
    return urlparse(site).netloc or site.rstrip("/")


def _normalizeSite(site: str) -> str:
    value = str(site or "").strip()
    if not value:
        return ""
    if "://" not in value:
        value = f"https://{value}"
    return value.rstrip("/")


class GitHubProxySiteValidator(ConfigValidator):
    def validate(self, value) -> bool:
        site = _normalizeSite(value)
        if not site:
            return False

        parsedSite = urlparse(site)
        return (
            parsedSite.scheme in {"http", "https"}
            and bool(parsedSite.netloc)
            and not parsedSite.params
            and not parsedSite.query
            and not parsedSite.fragment
        )

    def correct(self, value) -> str:
        site = _normalizeSite(value)
        return site if self.validate(site) else ""


def getSelectedProxySite() -> str:
    if githubConfig.proxySite.value == GITHUB_CUSTOM_PROXY_SITE:
        return githubConfig.customProxySite.value
    return githubConfig.proxySite.value


def _siteText(site: str, latency: int | None) -> str:
    if latency is None:
        return _siteName(site)
    if latency < 0:
        return f"{_siteName(site)} (超时)"
    return f"{_siteName(site)} ({latency} ms)"


def _customSiteText(site: str, latency: int | None) -> str:
    if not site:
        return "自定义"
    if latency is None:
        return "自定义"
    if latency < 0:
        return "自定义 (超时)"
    return f"自定义 ({latency} ms)"


class GitHubAgreementDialog(MessageBoxBase):
    def __init__(self, parent=None, requireAcceptance: bool = False):
        super().__init__(parent)
        self.requireAcceptance = requireAcceptance
        self.titleLabel = SubtitleLabel(self.tr("GitHub 加速用户协议"), self)
        self.contentEdit = PlainTextEdit(self)

        self._initWidget()

    def _initWidget(self):
        self.widget.setMinimumWidth(560)
        self.contentEdit.setReadOnly(True)
        self.contentEdit.setPlainText(self.tr(GITHUB_USER_AGREEMENT))
        self.contentEdit.setMinimumHeight(260)

        if self.requireAcceptance:
            self.yesButton.setText(self.tr("同意并启用"))
            self.cancelButton.setText(self.tr("取消"))
        else:
            self.yesButton.setText(self.tr("关闭"))
            self.cancelButton.hide()

        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addSpacing(8)
        self.viewLayout.addWidget(self.contentEdit)


async def measureProxyLatencies() -> dict[str, int]:
    sites = list(GITHUB_PROXY_SITES)
    customSite = githubConfig.customProxySite.value
    if customSite and customSite not in sites:
        sites.append(customSite)

    session = niquests.AsyncSession(happy_eyeballs=True)
    session.trust_env = False

    async def measureSiteLatency(site: str) -> tuple[str, int]:
        startedAt = perf_counter()
        try:
            response = await session.get(
                f"{site.rstrip('/')}/{GITHUB_PROBE_TARGET}",
                timeout=15,
                proxies=getProxies(),
                verify=cfg.SSLVerify.value,
                allow_redirects=True,
                stream=True,
            )
            try:
                response.raise_for_status()
            finally:
                await response.close()

            return site, max(1, int((perf_counter() - startedAt) * 1000))
        except Exception as e:
            logger.opt(exception=e).error("{} 测速失败", site)
            return site, -1

    try:
        results = await asyncio.gather(*(measureSiteLatency(site) for site in sites))
    finally:
        await session.close()

    return dict(results)


class GitHubProxySiteCard(SettingCard):
    def __init__(self, parent=None):
        super().__init__(
            FluentIcon.GLOBE,
            self.tr("代理站"),
            self.tr("选择 GitHub 反向代理站，延迟仅供参考"),
            parent,
        )
        self.latencies = {site: None for site in GITHUB_PROXY_SITES}
        self.comboBox = ComboBox(self)
        self.customSiteEdit = LineEdit(self)
        self.refreshButton = ToolButton(FluentIcon.SYNC, self)
        self.isRefreshing = False

        self._initWidget()
        self._reloadItems()
        self._connectSignalToSlot()

    def _initWidget(self):
        self.comboBox.setMinimumWidth(260)
        self.customSiteEdit.setPlaceholderText("https://example.com/")
        self.customSiteEdit.setClearButtonEnabled(True)
        self.customSiteEdit.setMinimumWidth(220)
        self.refreshButton.setToolTip(self.tr("刷新延迟"))
        self.refreshButton.installEventFilter(ToolTipFilter(self.refreshButton))
        self.hBoxLayout.addWidget(self.comboBox)
        self.hBoxLayout.addSpacing(8)
        self.hBoxLayout.addWidget(self.customSiteEdit)
        self.hBoxLayout.addSpacing(8)
        self.hBoxLayout.addWidget(self.refreshButton)
        self.hBoxLayout.addSpacing(16)

    def _connectSignalToSlot(self):
        self.comboBox.currentIndexChanged.connect(self._onCurrentIndexChanged)
        self.customSiteEdit.editingFinished.connect(self._onCustomSiteEditingFinished)
        self.refreshButton.clicked.connect(self.refreshLatencies)

    def _reloadItems(self):
        currentSite = githubConfig.proxySite.value
        if currentSite not in (*GITHUB_PROXY_SITES, GITHUB_CUSTOM_PROXY_SITE):
            currentSite = GITHUB_PROXY_SITES[0]
        customSite = githubConfig.customProxySite.value
        customLatency = self.latencies.get(customSite)

        self.comboBox.blockSignals(True)
        self.customSiteEdit.blockSignals(True)
        self.comboBox.clear()
        for site in GITHUB_PROXY_SITES:
            self.comboBox.addItem(_siteText(site, self.latencies[site]))
        self.comboBox.addItem(_customSiteText(customSite, customLatency))
        if currentSite == GITHUB_CUSTOM_PROXY_SITE:
            self.comboBox.setCurrentIndex(len(GITHUB_PROXY_SITES))
        else:
            self.comboBox.setCurrentIndex(GITHUB_PROXY_SITES.index(currentSite))
        self.customSiteEdit.setText(customSite)
        self.customSiteEdit.setVisible(currentSite == GITHUB_CUSTOM_PROXY_SITE)
        self.comboBox.blockSignals(False)
        self.customSiteEdit.blockSignals(False)

    def _onCurrentIndexChanged(self, index: int):
        if index < 0:
            return
        if index < len(GITHUB_PROXY_SITES):
            cfg.set(githubConfig.proxySite, GITHUB_PROXY_SITES[index])
        else:
            cfg.set(githubConfig.proxySite, GITHUB_CUSTOM_PROXY_SITE)
        self._reloadItems()

    def _onCustomSiteEditingFinished(self):
        oldCustomSite = githubConfig.customProxySite.value
        cfg.set(githubConfig.customProxySite, self.customSiteEdit.text())
        if oldCustomSite and oldCustomSite not in GITHUB_PROXY_SITES:
            self.latencies.pop(oldCustomSite, None)
        self._reloadItems()

    def refreshLatencies(self):
        if self.isRefreshing:
            return

        self.isRefreshing = True
        self.latencies = {site: None for site in GITHUB_PROXY_SITES}
        self._reloadItems()
        self.refreshButton.setEnabled(False)
        coreService.runCoroutine(measureProxyLatencies(), self._onLatencyUpdated)

    def _onLatencyUpdated(self, latencies: dict[str, int] | None, error: str | None = None):
        self.isRefreshing = False
        self.refreshButton.setEnabled(True)

        if error:
            logger.error("GitHub 代理站测速失败: {}", error)
            return
        if latencies is None:
            return

        self.latencies.update(latencies)
        self._reloadItems()


class GitHubConfig(PackConfig):
    enabled = ConfigItem("GitHub", "Enabled", False, BoolValidator())
    proxySite = OptionsConfigItem(
        "GitHub",
        "ProxySite",
        GITHUB_PROXY_SITES[0],
        OptionsValidator([*GITHUB_PROXY_SITES, GITHUB_CUSTOM_PROXY_SITE]),
    )
    customProxySite = ConfigItem(
        "GitHub",
        "CustomProxySite",
        "",
        GitHubProxySiteValidator(),
    )

    def loadSettingCards(self, settingPage: "SettingPage"):
        self.githubGroup = SettingCardGroup(self.tr("GitHub 加速"), settingPage.container)
        self.enableCard = SwitchSettingCard(
            FluentIcon.LINK,
            self.tr("启用 GitHub 加速"),
            self.tr("命中 GitHub 文件链接时，自动改写为所选反向代理站"),
            self.enabled,
            self.githubGroup,
        )
        self.viewAgreementButton = HyperlinkButton(self.enableCard)
        self.viewAgreementButton.setText(self.tr("查看协议"))
        self.proxySiteCard = GitHubProxySiteCard(self.githubGroup)

        self.enableCard.hBoxLayout.insertSpacing(5, 16)
        self.enableCard.hBoxLayout.insertWidget(5, self.viewAgreementButton, 0, Qt.AlignmentFlag.AlignRight)
        self.githubGroup.addSettingCard(self.enableCard)
        self.githubGroup.addSettingCard(self.proxySiteCard)

        settingPage.vBoxLayout.addWidget(self.githubGroup)

        self.enableCard.checkedChanged.connect(self._onEnabledChanged)
        self.viewAgreementButton.clicked.connect(self._showAgreement)

    def _showAgreementDialog(self, parent, requireAcceptance: bool) -> bool:
        dialog = GitHubAgreementDialog(parent, requireAcceptance=requireAcceptance)
        accepted = dialog.exec()
        dialog.deleteLater()
        return accepted

    def _onEnabledChanged(self, checked: bool):
        if not checked:
            return

        if self._showAgreementDialog(self.enableCard.window(), requireAcceptance=True):
            return

        cfg.set(self.enabled, False)

    def _showAgreement(self):
        self._showAgreementDialog(self.enableCard.window(), requireAcceptance=False)


githubConfig = GitHubConfig()
