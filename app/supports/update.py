import platform
import sys
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QVersionNumber

from app.supports.config import VERSION, cfg, isLessThanWin10
from app.supports.utils import buildClient, getProxies

RELEASE_API_URL = "https://api.github.com/repos/XiaoYouChR/Ghost-Downloader-3/releases/latest"
# UA 由 buildClient 供
RELEASE_HEADERS = {
    "accept": "application/vnd.github+json",
}


def _toVersionNumber(version: str) -> QVersionNumber:
    return QVersionNumber.fromString(str(version or "").strip().lstrip("vV"))


def toVersion(releaseData: dict[str, Any]) -> str:
    for key in ("tag_name", "name"):
        value = str(releaseData.get(key) or "").strip()
        if value:
            return value
    return "Unknown"


def isOutdated(releaseData: dict[str, Any]) -> bool:
    return _toVersionNumber(VERSION) < _toVersionNumber(toVersion(releaseData))



def _platformKeywords() -> list[str]:
    if sys.platform == "win32":
        if isLessThanWin10():
            return ["windows7", "windows"]
        return ["windows"]
    if sys.platform == "darwin":
        return ["macos", "darwin", "mac"]
    return ["linux"]


def _archKeywords() -> list[str]:
    machine = platform.machine().lower()
    if machine in {"amd64", "x86_64"}:
        return ["x86_64", "amd64", "x64"]
    if machine in {"arm64", "aarch64"}:
        return ["arm64", "aarch64"]
    if machine in {"x86", "i386", "i686"}:
        return ["x86", "i386", "i686"]
    return [machine] if machine else []


def _installerScore(installerName: str) -> int:
    lowerName = installerName.lower()
    platformKeywords = _platformKeywords()
    archKeywords = _archKeywords()

    platformScore = 0
    for index, keyword in enumerate(platformKeywords):
        if keyword in lowerName:
            platformScore = max(platformScore, 40 - index * 10)

    if platformScore == 0 or not any(keyword in lowerName for keyword in archKeywords):
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


def bestInstaller(releaseData: dict[str, Any]) -> dict[str, Any] | None:
    best, bestScore = None, -1
    for installer in releaseData.get("assets", []):
        score = _installerScore(str(installer.get("name") or "").strip())
        if score > bestScore:
            best, bestScore = installer, score
    return best


@dataclass
class UpdateState:
    outdated: bool
    latestVersion: str
    releaseData: dict[str, Any]
    installer: dict[str, Any] | None


async def fetchRelease() -> dict[str, Any]:
    async with buildClient(getProxies(), headers=RELEASE_HEADERS, timeout=30) as session:
        response = await session.get(RELEASE_API_URL)
        response.raise_for_status()
        return await response.json()


async def checkUpdate() -> UpdateState:
    data = await fetchRelease()
    return UpdateState(
        outdated=isOutdated(data),
        latestVersion=toVersion(data),
        releaseData=data,
        installer=bestInstaller(data),
    )
