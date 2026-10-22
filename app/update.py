from __future__ import annotations

import sys

from app.platform.arch import MACHINE_ARCH
from app.sources import Release, ReleaseAsset, Repo, fetchLatestRelease, probeDownloadUrl

APP_REPO = Repo("XiaoYouChR/Ghost-Downloader-3", mirrors={"gitcode": "XiaoYouChR/Ghost-Downloader-3"})


def parseVersion(s: str) -> tuple[int, ...]:
    segments: list[int] = []
    acc, hasDigit = 0, False
    for ch in s.lstrip("vV"):
        if ch.isdigit():
            acc = acc * 10 + int(ch)
            hasDigit = True
        elif ch == "." and hasDigit:
            segments.append(acc)
            acc, hasDigit = 0, False
        else:
            break
    if hasDigit:
        segments.append(acc)
    while segments and segments[-1] == 0:
        segments.pop()
    return tuple(segments)


def isNewer(current: str, latest: str) -> bool:
    return parseVersion(latest) > parseVersion(current)


async def fetchRelease() -> Release:
    return await fetchLatestRelease(APP_REPO)


async def fetchAssetUrl(version: str, name: str) -> str:
    return await probeDownloadUrl(APP_REPO, version, name)


async def fetchBestAssetUrl() -> str | None:
    release = await fetchRelease()
    asset = bestAsset(release)
    if asset is None:
        return None
    return await fetchAssetUrl(release.version, asset.name)


def bestAsset(release: Release) -> ReleaseAsset | None:
    best, bestScore = None, -1
    for asset in release.assets:
        score = assetScore(asset.name)
        if score > bestScore:
            best, bestScore = asset, score
    return best if bestScore >= 0 else None

def assetScore(name: str) -> int:
    from app.platform.android import IS_ANDROID

    lower = name.lower()

    if sys.platform == "win32":
        from app.platform.windows import isLessThanWin10
        platformKw = ["windows7", "windows"] if isLessThanWin10() else ["windows"]
    elif sys.platform == "darwin":
        platformKw = ["macos", "darwin", "mac"]
    elif IS_ANDROID:
        platformKw = ["android"]
    else:
        platformKw = ["linux"]

    archKw = ["x86_64", "amd64", "x64"] if MACHINE_ARCH == "x86_64" else ["arm64", "aarch64"]

    platformScore = 0
    for i, kw in enumerate(platformKw):
        if kw in lower:
            platformScore = max(platformScore, 40 - i * 10)

    if platformScore == 0 or not any(kw in lower for kw in archKw):
        return -1

    score = platformScore + 20
    if sys.platform == "win32":
        if "setup" in lower and lower.endswith(".exe"):
            score += 100
        elif lower.endswith(".msi"):
            score += 90
        elif lower.endswith(".zip"):
            score += 20
    elif sys.platform == "darwin":
        if lower.endswith(".dmg"):
            score += 100
        elif lower.endswith(".pkg"):
            score += 90
        elif lower.endswith(".zip"):
            score += 30
    elif IS_ANDROID:
        if lower.endswith(".apk"):
            score += 100
    else:
        if lower.endswith(".appimage"):
            score += 100
        elif lower.endswith((".deb", ".rpm")):
            score += 90
        elif lower.endswith(".tar.xz"):
            score += 80
        elif lower.endswith((".tar.gz", ".zip")):
            score += 50

    return score
