from __future__ import annotations

import platform
import sys
from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget

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


def isFullUpdateAsset(asset: ReleaseAsset) -> bool:
    """判断是否为完整更新包（.exe/.msi/.dmg/.pkg/.apk）"""
    name = asset.name.lower()
    if sys.platform == "win32":
        return name.endswith((".exe", ".msi"))
    elif sys.platform == "darwin":
        return name.endswith((".dmg", ".pkg"))
    else:
        from app.platform.android import IS_ANDROID
        if IS_ANDROID:
            return name.endswith(".apk")
        return name.endswith(".appimage")


def showReleaseDialog(release: Release, parent: QWidget) -> None:
    from app.view.dialogs.release_info import ReleaseInfoDialog
    dialog = ReleaseInfoDialog(release, parent)
    dialog.accepted.connect(lambda: downloadAsset(dialog.selectedAsset(), parent))
    dialog.open()


def addBestAssetTask(release: Release, parent: QWidget) -> None:
    """为了兼容性保留的旧方法，现在调用新的下载逻辑"""
    downloadBestAsset(release, parent)


def downloadBestAsset(release: Release, parent: QWidget) -> None:
    from qfluentwidgets import InfoBar, InfoBarPosition
    asset = bestAsset(release)
    if asset is None:
        InfoBar.warning(
            parent.tr("未找到适配的安装包"),
            parent.tr("请在版本详情中手动选择"),
            duration=3000, position=InfoBarPosition.BOTTOM_RIGHT, parent=parent,
        )
        showReleaseDialog(release, parent)
        return
    downloadAsset(asset, parent)


def downloadAsset(asset: ReleaseAsset | None, parent: QWidget) -> None:
    """下载应用更新资源

    对于完整更新包（.exe/.msi/.dmg等），使用独立下载模式并显示实时进度。
    对于其他格式（.zip等），退化为普通任务队列下载。
    """
    if asset is None:
        return

    if isFullUpdateAsset(asset):
        # 使用独立下载模式
        from app.services.app_update_service import appUpdateService
        appUpdateService.downloadAppUpdate(asset.downloadUrl, asset.name)
    else:
        # 退化为任务队列
        _downloadAsFallbackTask(asset, parent)


def _downloadAsFallbackTask(asset: ReleaseAsset, parent: QWidget) -> None:
    """将更新包作为普通任务加入下载队列"""
    from qfluentwidgets import InfoBar, InfoBarPosition
    from app.models.task import TaskOptions
    from app.services.coroutine_runner import coroutineRunner
    from app.services.feature_service import featureService
    from app.services.task_service import taskService

    def onParsed(task) -> None:
        taskService.add(task)
        InfoBar.info(
            parent.tr("已加入下载列表"),
            parent.tr("下载完成后请手动安装"),
            duration=3000, position=InfoBarPosition.BOTTOM_RIGHT, parent=parent,
        )

    coroutineRunner.submit(
        featureService.parse(TaskOptions(url=asset.downloadUrl)),
        done=onParsed,
        failed=lambda e: InfoBar.error(
            parent.tr("创建下载任务失败"), str(e),
            duration=3000, position=InfoBarPosition.BOTTOM_RIGHT, parent=parent,
        ),
        owner=parent,
    )


def addAssetTask(asset: ReleaseAsset, parent: QWidget) -> None:
    """为了兼容性保留的旧方法，现在调用新的下载逻辑"""
    downloadAsset(asset, parent)


