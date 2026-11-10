from __future__ import annotations

import base64
import binascii
from dataclasses import replace

from app.i18n import N
from app.models.pack import FeaturePack, TaskParser, UriScheme
from app.models.task import Task, TaskError, TaskOptions, toScheme
from .config import wrappedLinkConfig

SCHEMES = {"thunder", "flashget", "qqdl"}


def toInnerUrl(url: str) -> str:
    scheme, _, payload = url.strip().partition("://")
    payload = payload.split("&", 1)[0].rstrip("/")
    try:
        raw = base64.b64decode(payload + "=" * (-len(payload) % 4))
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("gbk")
    except (binascii.Error, UnicodeDecodeError) as e:
        raise TaskError("无法解析该链接") from e

    match scheme.lower():
        case "thunder":
            if not (text.startswith("AA") and text.endswith("ZZ")):
                raise TaskError("无法解析该链接")
            text = text[2:-2]
        case "flashget":
            text = text.removeprefix("[FLASHGET]").removesuffix("[FLASHGET]").removesuffix("[/FLASHGET]")

    innerScheme = toScheme(text)
    if innerScheme in SCHEMES:
        raise TaskError("不支持多层包裹的链接")
    if not innerScheme:
        raise TaskError("无法解析该链接")
    return text.strip()


class WrappedLinkParser(TaskParser):
    priority = 10

    def match(self, options: TaskOptions) -> bool:
        return toScheme(options.url) in SCHEMES

    async def parse(self, options: TaskOptions) -> Task:
        return await self.pack.parse(replace(options, url=toInnerUrl(options.url)))


class WrappedLinkPack(FeaturePack):
    packId = "wrapped_link"
    capturedLinks = N("WrappedLinkPack", "迅雷、快车、QQ 旋风链接")
    config = wrappedLinkConfig
    parsers = [WrappedLinkParser]

    def uriSchemes(self) -> list[UriScheme]:
        return [UriScheme("thunder", "迅雷"), UriScheme("flashget", "快车"), UriScheme("qqdl", "QQ 旋风")]
