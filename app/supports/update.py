import platform
import sys
from typing import Any

import niquests
from PySide6.QtCore import QVersionNumber

from app.supports.config import DEFAULT_HEADERS, VERSION, cfg, isLessThanWin10
from app.supports.utils import getProxies

RELEASE_API_URL = "https://api.github.com/repos/XiaoYouChR/Ghost-Downloader-3/releases/latest"
RELEASE_HEADERS = {
    "accept": "application/vnd.github+json",
    "user-agent": DEFAULT_HEADERS["user-agent"],
}


def _toVersionNumber(version: str) -> QVersionNumber:
    return QVersionNumber.fromString(str(version or "").strip().lstrip("vV"))


def releaseVersion(releaseData: dict[str, Any]) -> str:
    for key in ("tag_name", "name"):
        value = str(releaseData.get(key) or "").strip()
        if value:
            return value
    return "Unknown"


def hasNewerRelease(releaseData: dict[str, Any]) -> bool:
    return _toVersionNumber(VERSION) < _toVersionNumber(releaseVersion(releaseData))



def _platformTokens() -> list[str]:
    if sys.platform == "win32":
        if isLessThanWin10():
            return ["windows7", "windows"]
        return ["windows"]
    if sys.platform == "darwin":
        return ["macos", "darwin", "mac"]
    return ["linux"]


def _archTokens() -> list[str]:
    machine = platform.machine().lower()
    if machine in {"amd64", "x86_64"}:
        return ["x86_64", "amd64", "x64"]
    if machine in {"arm64", "aarch64"}:
        return ["arm64", "aarch64"]
    if machine in {"x86", "i386", "i686"}:
        return ["x86", "i386", "i686"]
    return [machine] if machine else []


def _platformAssetScore(assetName: str) -> int:
    lowerName = assetName.lower()
    platformTokens = _platformTokens()
    archTokens = _archTokens()

    platformScore = 0
    for index, token in enumerate(platformTokens):
        if token in lowerName:
            platformScore = max(platformScore, 40 - index * 10)

    if platformScore == 0 or not any(token in lowerName for token in archTokens):
        return -1

    score = platformScore + 20
    if sys.platform == "win32":
        if "setup" in lowerName and lowerName.endswith(".exe"):
            score += 100
        elif lowerName.endswith(".msi"):
            score += 90
        elif lowerName.endswith(".zip"):
            score += 20
    elif sys.platform == "darwin":
        if lowerName.endswith(".dmg"):
            score += 100
        elif lowerName.endswith(".pkg"):
            score += 90
        elif lowerName.endswith(".zip"):
            score += 30
    else:
        if lowerName.endswith(".appimage"):
            score += 100
        elif lowerName.endswith(".deb") or lowerName.endswith(".rpm"):
            score += 90
        elif lowerName.endswith(".tar.xz"):
            score += 80
        elif lowerName.endswith(".tar.gz") or lowerName.endswith(".zip"):
            score += 50

    return score


def selectCurrentPlatformAsset(releaseData: dict[str, Any]) -> dict[str, Any] | None:
    candidates: list[tuple[int, int, dict[str, Any]]] = []
    for asset in releaseData.get("assets", []):
        assetName = str(asset.get("name") or "").strip()
        score = _platformAssetScore(assetName)
        if score < 0:
            continue

        downloadCount = int(asset.get("download_count") or 0)
        candidates.append((score, downloadCount, asset))

    if not candidates:
        return None

    return max(candidates, key=lambda item: (item[0], item[1]))[2]


async def fetchLatestRelease() -> dict[str, Any]:
    session = niquests.AsyncSession(
        headers=RELEASE_HEADERS,
        timeout=30,
        happy_eyeballs=True,
    )
    session.trust_env = False

    try:
        response = await session.get(
            RELEASE_API_URL,
            proxies=getProxies(),
            verify=cfg.SSLVerify.value,
            allow_redirects=True,
        )
        try:
            response.raise_for_status()
            payload = response.json()
        finally:
            response.close()
    finally:
        await session.close()

    return payload
