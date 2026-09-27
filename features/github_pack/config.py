from __future__ import annotations

from urllib.parse import urlparse

from app.config.cfg import BoolValidator, ConfigItem, ConfigValidator, OptionsValidator
from app.models.pack import PackConfig

GITHUB_PROXY_SITES = (
    "https://gh-proxy.com",
    "https://gh-proxy.org",
    "https://cdn.gh-proxy.org",
    "https://edgeone.gh-proxy.org",
    "https://hk.gh-proxy.org",
    "https://ghfast.top",
    "https://ghfile.geekertao.top",
    "https://gh.chjina.com",
    "https://gh.monlor.com",
    "https://gh.jasonzeng.dev",
    "https://ghproxy.monkeyray.net",
    "https://github.ednovas.xyz",
    "https://gh.nxnow.top",
    "https://ghproxy.cxkpro.top",
    "https://fastgit.cc",
    "https://gh.zwy.one",
    "https://gitproxy.mrhjx.cn",
    "https://github.boki.moe",
    "https://gh.xxooo.cf",
    "https://gh.llkk.cc",
    "https://wget.la",
)
AUTO_SITE_KEY = "__auto__"
CUSTOM_SITE_KEY = "__custom__"


def toProxySite(site: str) -> str:
    value = str(site or "").strip()
    if not value:
        return ""
    if "://" not in value:
        value = f"https://{value}"
    return value.rstrip("/")


def selectedProxySite() -> str:
    if githubConfig.selectedSite.value == AUTO_SITE_KEY:
        return ""
    if githubConfig.selectedSite.value == CUSTOM_SITE_KEY:
        return githubConfig.customSite.value
    return githubConfig.selectedSite.value


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


class GitHubConfig(PackConfig):
    enabled = ConfigItem("GitHub", "Enabled", False, BoolValidator())
    selectedSite = ConfigItem(
        "GitHub", "SelectedSite", AUTO_SITE_KEY,
        OptionsValidator([AUTO_SITE_KEY, *GITHUB_PROXY_SITES, CUSTOM_SITE_KEY]),
    )
    customSite = ConfigItem("GitHub", "CustomSite", "", GitHubProxySiteValidator())

    def settingGroups(self, parent: QWidget) -> list[CollapsibleSettingCardGroup]:
        from qfluentwidgets import FluentIcon, SwitchSettingCard
        from app.view.components.setting_card_group import CollapsibleSettingCardGroup
        from .setting_cards import GitHubProxySiteCard

        githubGroup = CollapsibleSettingCardGroup(self.tr("GitHub 加速"), "github", parent)
        enableCard = SwitchSettingCard(
            FluentIcon.LINK, self.tr("启用 GitHub 加速"),
            self.tr("经代理站下载 GitHub 文件，不可用时自动切换其他站点或直连"),
            self.enabled, githubGroup,
        )
        proxySiteCard = GitHubProxySiteCard(self.submit, githubGroup)

        githubGroup.addSettingCards([enableCard, proxySiteCard])
        return [githubGroup]


githubConfig = GitHubConfig()
