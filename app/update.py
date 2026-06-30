from __future__ import annotations

import platform
import sys
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QVersionNumber

from app.client import buildClient
from app.config.cfg import cfg, proxy
from app.config.constants import VERSION

RELEASE_API = "https://api.github.com/repos/XiaoYouChR/Ghost-Downloader-3/releases/latest"


@dataclass(frozen=True)
class ReleaseAsset:
    name: str
    size: int
    downloadCount: int
    downloadUrl: str


@dataclass(frozen=True)
class Release:
    version: str
    publishedAt: str
    body: str
    pageUrl: str
    prerelease: bool
    assets: list[ReleaseAsset]

    @classmethod
    def fromResponse(cls, data: dict[str, Any]) -> Release:
        version = ""
        for key in ("tag_name", "name"):
            value = str(data.get(key) or "").strip()
            if value:
                version = value
                break

        assets = [
            ReleaseAsset(
                name=a.get("name", ""),
                size=a.get("size", 0),
                downloadCount=a.get("download_count", 0),
                downloadUrl=a.get("browser_download_url", ""),
            )
            for a in data.get("assets", [])
        ]

        return cls(
            version=version or "Unknown",
            publishedAt=data.get("published_at", ""),
            body=data.get("body", ""),
            pageUrl=data.get("html_url", ""),
            prerelease=data.get("prerelease", False),
            assets=assets,
        )


async def fetchRelease() -> Release:
    client = buildClient(headers={"accept": "application/vnd.github+json"})
    try:
        response = await client.get(RELEASE_API)
        response.raise_for_status()
        data = await response.json()
        return Release.fromResponse(data)
    finally:
        client.close()


def isOutdated(release: Release) -> bool:
    current = QVersionNumber.fromString(VERSION.lstrip("vV"))
    latest = QVersionNumber.fromString(release.version.lstrip("vV"))
    return current < latest


def bestAsset(release: Release) -> ReleaseAsset | None:
    best, bestScore = None, -1
    for asset in release.assets:
        score = assetScore(asset.name)
        if score > bestScore:
            best, bestScore = asset, score
    return best if bestScore >= 0 else None


def assetScore(name: str) -> int:
    lower = name.lower()

    if sys.platform == "win32":
        from app.platform.windows import isLessThanWin10
        platformKw = ["windows7", "windows"] if isLessThanWin10() else ["windows"]
    elif sys.platform == "darwin":
        platformKw = ["macos", "darwin", "mac"]
    else:
        platformKw = ["linux"]

    machine = platform.machine().lower()
    archKw = (
        ["x86_64", "amd64", "x64"] if machine in {"amd64", "x86_64"} else
        ["arm64", "aarch64"] if machine in {"arm64", "aarch64"} else
        ["x86", "i386", "i686"] if machine in {"x86", "i386", "i686"} else
        [machine] if machine else []
    )

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
