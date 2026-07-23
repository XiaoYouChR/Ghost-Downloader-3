from __future__ import annotations

import re
import sys
from datetime import timedelta
from typing import TYPE_CHECKING

from loguru import logger
from wreq import Client, Emulation, Proxy
from wreq.emulation import Platform, Profile
from wreq.redirect import Policy

from app.config.cfg import cfg, proxy

if TYPE_CHECKING:
    from wreq import ClientConfig3

FALLBACK_PROFILE = "chrome"

FAMILY_BY_PREFIX = {
    "Chrome": "chrome", "Edge": "edge", "Firefox": "firefox", "Opera": "opera",
    "Safari": "safari", "OkHttp": "okhttp",
    "FirefoxAndroid": "firefox-android", "SafariIos": "safari-ios",
    "SafariIPad": "safari-ipad", "SafariIpad": "safari-ipad",
}
PLATFORM_BY_FAMILY = {
    "okhttp": Platform.Android, "firefox-android": Platform.Android,
    "safari-ios": Platform.IOS, "safari-ipad": Platform.IOS,
}


def buildRegistry() -> dict[str, list[tuple[str, tuple[int, ...], Profile]]]:
    families: dict[str, list[tuple[str, tuple[int, ...], Profile]]] = {}
    for name in dir(Emulation):
        m = re.match(r"^([A-Za-z]+?)(\d[\d_]*)$", name)
        if not m or not isinstance(getattr(Emulation, name), Profile):
            continue
        family = FAMILY_BY_PREFIX.get(m.group(1))
        if family is not None:
            version = tuple(int(x) for x in m.group(2).split("_"))
            families.setdefault(family, []).append((name, version, getattr(Emulation, name)))
    for entries in families.values():
        entries.sort(key=lambda e: e[1], reverse=True)
    return families


PROFILES_BY_FAMILY = buildRegistry()


def toEmulation(profile: str, sourceUa: str = "") -> Emulation | None:
    profile = profile or cfg.clientProfile.value
    host = {"win32": Platform.Windows, "darwin": Platform.MacOS}.get(sys.platform, Platform.Linux)

    if profile == "raw":
        return None

    if profile == "auto":
        return matchEmulation(sourceUa, host) or Emulation(
            profile=PROFILES_BY_FAMILY["chrome"][0][2], platform=host,
        )

    if profile in PROFILES_BY_FAMILY:
        return Emulation(
            profile=PROFILES_BY_FAMILY[profile][0][2],
            platform=PLATFORM_BY_FAMILY.get(profile, host),
        )

    for entries in PROFILES_BY_FAMILY.values():
        for name, _ver, pinned in entries:
            if name == profile:
                m = re.match(r"^([A-Za-z]+?)\d", profile)
                fam = FAMILY_BY_PREFIX.get(m.group(1)) if m else None
                return Emulation(profile=pinned, platform=PLATFORM_BY_FAMILY.get(fam, host))

    logger.warning("未知的模拟身份 {}, 退回默认", profile)
    return Emulation(profile=PROFILES_BY_FAMILY["chrome"][0][2], platform=host)


def matchIdentityPreset(host: str) -> dict | None:
    for preset in cfg.identityPresets.value:
        if not preset.get("isEnabled", True):
            continue
        for pattern in preset.get("hosts", []):
            if pattern.startswith("*."):
                suffix = pattern[2:]
                if host == suffix or host.endswith("." + suffix):
                    return preset
            elif host == pattern:
                return preset
    return None


def buildClient(
    *,
    emulation: Emulation | None = ...,
    headers: dict | None = None,
    userAgent: str | None = None,
    timeout: int | None = None,
) -> Client:
    resolved = toEmulation("") if emulation is ... else emulation
    config: ClientConfig = {"tls_verify": cfg.shouldVerifySsl.value, "redirect": Policy.limited(10)}

    url = proxy()
    if url:
        config["proxies"] = [Proxy.all(url)]

    if resolved is not None:
        config["emulation"] = resolved

    if headers:
        if resolved is not None:
            filtered = {
                k: v for k, v in headers.items()
                if k.lower() != "user-agent" and not k.lower().startswith("sec-ch-ua")
            }
            if userAgent:
                filtered["user-agent"] = userAgent
            config["headers"] = filtered
        else:
            if userAgent:
                headers = {**headers, "user-agent": userAgent}
            elif not any(k.lower() == "user-agent" for k in headers):
                major = PROFILES_BY_FAMILY["chrome"][0][1][0]
                headers = {
                    **headers,
                    "user-agent": f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                                  f"(KHTML, like Gecko) Chrome/{major}.0.0.0 Safari/537.36",
                }
            config["headers"] = headers
    elif userAgent:
        config["headers"] = {"user-agent": userAgent}

    if timeout is not None:
        config["timeout"] = timedelta(seconds=timeout)
    return Client(**config)


def profileFamilies() -> list[str]:
    return [f for f in (
        "chrome", "edge", "firefox", "firefox-android", "opera",
        "safari", "safari-ios", "safari-ipad", "okhttp",
    ) if f in PROFILES_BY_FAMILY]


def profileVersions(family: str) -> list[str]:
    return [name for name, _ver, _profile in PROFILES_BY_FAMILY.get(family, [])]


def matchEmulation(userAgent: str, host: Platform) -> Emulation | None:
    if not userAgent:
        return None

    for family, pattern in (
        ("edge", r"Edg(?:e|A|iOS)?/(\d+)"),
        ("opera", r"OPR/(\d+)"),
        ("okhttp", r"(?i)okhttp/(\d+)"),
        ("firefox", r"Firefox/(\d+)"),
        ("chrome", r"Chrome/(\d+)"),
        ("safari", r"Version/(\d+).+Safari/"),
    ):
        match = re.search(pattern, userAgent)
        if not match:
            continue

        if family in PLATFORM_BY_FAMILY:
            platform = PLATFORM_BY_FAMILY[family]
        elif "Android" in userAgent:
            platform = Platform.Android
        elif any(t in userAgent for t in ("iPhone", "iPad", "iPod")):
            platform = Platform.IOS
        elif "Windows" in userAgent:
            platform = Platform.Windows
        elif "Mac OS X" in userAgent or "Macintosh" in userAgent:
            platform = Platform.MacOS
        elif "Linux" in userAgent:
            platform = Platform.Linux
        else:
            platform = host

        resolved = family
        if family == "safari" and platform == Platform.IOS:
            if "iPad" in userAgent and "safari-ipad" in PROFILES_BY_FAMILY:
                resolved = "safari-ipad"
            elif "safari-ios" in PROFILES_BY_FAMILY:
                resolved = "safari-ios"
        elif family == "firefox" and platform == Platform.Android and "firefox-android" in PROFILES_BY_FAMILY:
            resolved = "firefox-android"

        entries = PROFILES_BY_FAMILY.get(resolved)
        if not entries:
            return None
        major = int(match.group(1))
        profile = next((p for _n, v, p in entries if v[0] <= major), entries[-1][2])
        return Emulation(profile=profile, platform=platform)

    return None
