from __future__ import annotations

from urllib.parse import urlparse

from app.client import buildClient
from app.config.cfg import BoolValidator, ConfigItem, ConfigValidator
from app.models.pack import PackConfig

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


class GitHubConfig(PackConfig):
    enabled = ConfigItem("GitHub", "Enabled", False, BoolValidator())
    selectedSite = ConfigItem("GitHub", "SelectedSite", GITHUB_PROXY_SITES[0], GitHubProxySiteValidator())
    customSite = ConfigItem("GitHub", "CustomSite", "", GitHubProxySiteValidator())

    def settingGroups(self, parent: QWidget) -> list[CollapsibleSettingCardGroup]:
        from qfluentwidgets import FluentIcon, SwitchSettingCard
        from app.view.components.setting_card_group import CollapsibleSettingCardGroup
        from .setting_cards import GitHubProxySiteCard

        githubGroup = CollapsibleSettingCardGroup(self.tr("GitHub 加速"), "github", parent)
        enableCard = SwitchSettingCard(
            FluentIcon.LINK, self.tr("启用 GitHub 加速"),
            self.tr("优先使用所选代理站，不可用时自动切换其他站点或直连"),
            self.enabled, githubGroup,
        )
        proxySiteCard = GitHubProxySiteCard(self.submit, githubGroup)

        githubGroup.addSettingCards([enableCard, proxySiteCard])
        return [githubGroup]


githubConfig = GitHubConfig()
