from __future__ import annotations

from urllib.parse import urlparse

from app.client import buildClient
from app.config.cfg import BoolValidator, ConfigItem, ConfigValidator, OptionsValidator
from app.models.pack import PackConfig


MIRROR_SITES = (
    "https://hf-mirror.com",
)
CUSTOM_SITE_KEY = "__custom__"
PROBE_TARGET = "https://huggingface.co/api/models/gpt2"
TOKEN_URL = "https://huggingface.co/settings/tokens"


def toMirrorSite(site: str) -> str:
    value = str(site or "").strip()
    if not value:
        return ""
    if "://" not in value:
        value = f"https://{value}"
    return value.rstrip("/")


def selectedMirrorSite() -> str:
    if huggingFaceConfig.selectedSite.value == CUSTOM_SITE_KEY:
        return huggingFaceConfig.customSite.value
    return huggingFaceConfig.selectedSite.value


async def probeMirrorLatencies() -> dict[str, int]:
    import asyncio
    from time import perf_counter

    sites = list(MIRROR_SITES)
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


class HuggingFaceMirrorSiteValidator(ConfigValidator):
    def validate(self, value) -> bool:
        site = toMirrorSite(value)
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
        site = toMirrorSite(value)
        return site if self.validate(site) else ""


class HuggingFaceConfig(PackConfig):
    isEnabled = ConfigItem("HuggingFace", "Enabled", True, BoolValidator())
    selectedSite = ConfigItem("HuggingFace", "SelectedSite", MIRROR_SITES[0], OptionsValidator([*MIRROR_SITES, CUSTOM_SITE_KEY]))
    customSite = ConfigItem("HuggingFace", "CustomSite", "", HuggingFaceMirrorSiteValidator())
    accessToken = ConfigItem("HuggingFace", "AccessToken", "")

    def settingGroups(self, parent: QWidget) -> list[CollapsibleSettingCardGroup]:
        from qfluentwidgets import FluentIcon, SwitchSettingCard
        from app.view.components.setting_card_group import CollapsibleSettingCardGroup
        from .setting_cards import HuggingFaceMirrorSiteCard, HuggingFaceTokenCard

        group = CollapsibleSettingCardGroup(self.tr("HuggingFace 下载"), "huggingface", parent)
        group.addSettingCards([
            SwitchSettingCard(
                FluentIcon.CONNECT, self.tr("启用 HuggingFace 加速"),
                self.tr("命中 HuggingFace 链接时，自动改写为所选镜像站"),
                self.isEnabled, group,
            ),
            HuggingFaceMirrorSiteCard(self.submit, group),
            HuggingFaceTokenCard(group),
        ])
        return [group]


huggingFaceConfig = HuggingFaceConfig()
