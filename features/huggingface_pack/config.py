from __future__ import annotations

from urllib.parse import urlparse

from app.client import buildClient
from app.config.cfg import BoolValidator, ConfigItem, ConfigValidator
from app.models.pack import PackConfig


HF_PROXY_SITES = (
    "https://hf-mirror.com",
)
CUSTOM_SITE_KEY = "__custom__"
PROBE_TARGET = "https://huggingface.co/api/models/gpt2"
TOKEN_URL = "https://huggingface.co/settings/tokens"


def toProxySite(site: str) -> str:
    value = str(site or "").strip()
    if not value:
        return ""
    if "://" not in value:
        value = f"https://{value}"
    return value.rstrip("/")


def selectedProxySite() -> str:
    if huggingFaceConfig.selectedSite.value == CUSTOM_SITE_KEY:
        return huggingFaceConfig.customSite.value
    return huggingFaceConfig.selectedSite.value


def accessToken() -> str:
    return huggingFaceConfig.accessToken.value


async def probeProxyLatencies() -> dict[str, int]:
    import asyncio
    from time import perf_counter

    sites = list(HF_PROXY_SITES)
    custom = huggingFaceConfig.customSite.value
    if custom:
        sites.append(custom)

    async def probeOne(site: str) -> tuple[str, int]:
        url = f"{site.rstrip('/')}/{PROBE_TARGET}"
        client = buildClient()
        try:
            start = perf_counter()
            response = await asyncio.wait_for(client.get(url), timeout=10)
            elapsed = int((perf_counter() - start) * 1000)
            return site, elapsed if response.status.as_int() < 400 else -1
        except Exception:
            return site, -1
        finally:
            client.close()

    results = await asyncio.gather(*(probeOne(s) for s in sites))
    return dict(results)


class HuggingFaceProxySiteValidator(ConfigValidator):
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


class HuggingFaceConfig(PackConfig):
    isEnabled = ConfigItem("HuggingFace", "Enabled", True, BoolValidator())
    selectedSite = ConfigItem("HuggingFace", "SelectedSite", HF_PROXY_SITES[0], HuggingFaceProxySiteValidator())
    customSite = ConfigItem("HuggingFace", "CustomSite", "", HuggingFaceProxySiteValidator())
    accessToken = ConfigItem("HuggingFace", "AccessToken", "")

    def settingGroups(self, parent: QWidget) -> list[CollapsibleSettingCardGroup]:
        from qfluentwidgets import FluentIcon, SwitchSettingCard
        from app.view.components.setting_card_group import CollapsibleSettingCardGroup
        from .setting_cards import HuggingFaceProxySiteCard, HuggingFaceTokenCard

        group = CollapsibleSettingCardGroup(self.tr("HuggingFace"), "huggingface", parent)
        group.addSettingCards([
            SwitchSettingCard(
                FluentIcon.CONNECT, self.tr("启用 HuggingFace 加速"),
                self.tr("命中 HuggingFace 链接时，自动改写为所选镜像站"),
                self.isEnabled, group,
            ),
            HuggingFaceProxySiteCard(self.submit, group),
            HuggingFaceTokenCard(group),
        ])
        return [group]


huggingFaceConfig = HuggingFaceConfig()
