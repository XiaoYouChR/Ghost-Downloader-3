import asyncio
import platform
import sys
from pathlib import Path
from typing import Any, TYPE_CHECKING
from urllib.parse import urlparse

from app.bases.interfaces import FeaturePack
from app.bases.models import Task, SpecialFileSize
from app.supports.config import activeUserAgent, cfg
from app.supports.utils import buildClient, getProxies, toExecutable, toSafeFilename
from .config import ffmpegConfig, ffmpegPaths
from app.view.components.cards import UniversalTaskCard
from .task import FFmpegResourceStage, FFmpegStage

if TYPE_CHECKING:
    from features.disk_pack.pack import buildToolInstallTask
    from features.http_pack.task import HttpTaskStage
else:
    from disk_pack.pack import buildToolInstallTask
    from http_pack.task import HttpTaskStage


FFMPEG_MERGE_URL = "gd3+ffmpeg://merge"

_FFMPEG_RELEASE_API = "https://api.github.com/repos/BtbN/FFmpeg-Builds/releases/latest"
_FFMPEG_HEADERS = {
    "accept": "application/vnd.github+json",
    "user-agent": activeUserAgent(),
}


def _resourceExtension(name: str, url: str) -> str:
    target = name or urlparse(url).path
    return Path(target).suffix.lstrip(".").lower()


def _windowsTarget() -> tuple[str, str]:
    if sys.platform != "win32":
        raise RuntimeError("一键安装 FFmpeg 仅支持 Windows 平台")

    machine = platform.machine().lower()
    if machine in {"amd64", "x86_64"}:
        return "win64", "x64"
    if machine in {"arm64", "aarch64"}:
        return "winarm64", "arm64"
    raise RuntimeError(f"不支持的 Windows 架构: {platform.machine()}")


def _bestAsset(assets: list[dict[str, Any]], target: str) -> dict[str, Any]:
    candidates: list[tuple[int, dict[str, Any]]] = []
    for asset in assets:
        lowerName = asset["name"].lower()
        if target not in lowerName or not lowerName.endswith(".zip") or "shared" in lowerName:
            continue

        score = 0
        if "master-latest" in lowerName:
            score += 100
        if "-gpl" in lowerName:
            score += 10
        if "-latest-" in lowerName:
            score += 5
        candidates.append((score, asset))

    if not candidates:
        raise RuntimeError(f"未找到适用于当前平台的 FFmpeg 安装包: {target}")
    return max(candidates, key=lambda item: item[0])[1]


async def _fetchLatestRelease(target: str) -> dict[str, Any]:
    async with buildClient(getProxies(), headers=_FFMPEG_HEADERS, timeout=30) as client:
        response = await client.get(_FFMPEG_RELEASE_API)
        response.raise_for_status()
        payload = await response.json()

    assets = payload.get("assets")
    if not isinstance(assets, list):
        raise RuntimeError("GitHub Release 返回了无效的 assets 数据")

    asset = _bestAsset(assets, target)
    downloadUrl = asset["browser_download_url"].strip()
    assetName = asset["name"].strip()
    size = asset["size"]
    if not downloadUrl or not assetName or size <= 0:
        raise RuntimeError("GitHub Release 返回了不完整的 FFmpeg 安装包信息")

    return {
        "name": assetName,
        "url": downloadUrl,
        "size": size,
    }


async def _resourceDownloadTask(item: dict[str, Any], payload: dict[str, Any], path: Path) -> Task:
    from app.services.feature_service import featureService

    url = item["url"].strip()
    if not url.startswith(("http://", "https://")):
        raise RuntimeError("在线合并暂不支持 blob 或非 HTTP 资源")

    resourceTask = await featureService.parse({
        "url": url,
        "filename": (item.get("filename") or "").strip(),
        "headers": item.get("headers") or {},
        "fileSize": item.get("fileSize") or SpecialFileSize.UNKNOWN,
        "supportsRange": bool(item.get("supportsRange")),
        "proxies": payload.get("proxies", getProxies()),
        "path": path,
        "preBlockNum": payload.get("preBlockNum", cfg.preBlockNum.value),
    })
    if not resourceTask.stages:
        raise RuntimeError("解析在线合并源文件失败")
    return resourceTask


async def createMergeTask(payload: dict[str, Any]) -> Task:
    ffmpeg, ffprobe = ffmpegPaths()
    if not ffmpeg or not ffprobe:
        raise RuntimeError("未找到可用的 ffmpeg 和 ffprobe，请先在设置中安装或配置 FFmpeg")

    resources = payload.get("resources") or []
    if len(resources) != 2:
        raise RuntimeError("在线合并暂时只支持 2 个 HTTP 音视频资源")

    path = Path(payload.get("path", cfg.downloadFolder.value))
    videoTask, audioTask = await asyncio.gather(
        _resourceDownloadTask(resources[0], payload, path),
        _resourceDownloadTask(resources[1], payload, path),
    )

    rawTitle = (
        (payload.get("outputTitle") or "").strip()
        or (resources[0].get("pageTitle") or "").strip()
    )
    baseTitle = toSafeFilename(rawTitle, fallback="merged-media")
    outputTitle = baseTitle if baseTitle.lower().endswith(".mp4") else f"{baseTitle}.mp4"

    videoSource: HttpTaskStage = videoTask.stages[0]
    audioSource: HttpTaskStage = audioTask.stages[0]
    videoExt = _resourceExtension(videoTask.title, videoSource.url)
    audioExt = _resourceExtension(audioTask.title, audioSource.url)

    videoStage = _toResourceStage(videoSource, role="video", extension=videoExt, stageIndex=1)
    audioStage = _toResourceStage(audioSource, role="audio", extension=audioExt, stageIndex=2)
    mergeStage = FFmpegStage(
        stageIndex=3,
        videoExtension=videoExt,
        audioExtension=audioExt,
    )

    task = Task(
        title=outputTitle,
        url=videoStage.url,
        packId="ffmpeg",
        fileSize=max(0, videoTask.fileSize) + max(0, audioTask.fileSize),
        path=path,
    )
    task.addStage(videoStage)
    task.addStage(audioStage)
    task.addStage(mergeStage)
    return task


def _toResourceStage(
    httpStage: "HttpTaskStage", *, role: str, extension: str, stageIndex: int,
) -> FFmpegResourceStage:
    return FFmpegResourceStage(
        stageIndex=stageIndex,
        url=httpStage.url,
        fileSize=httpStage.fileSize,
        headers=httpStage.headers,
        proxies=httpStage.proxies,
        blockNum=httpStage.blockNum,
        supportsRange=httpStage.supportsRange,
        role=role,
        extension=extension,
    )


async def createInstallTask() -> Task:
    target, archLabel = _windowsTarget()
    assetInfo = await _fetchLatestRelease(target)
    return await buildToolInstallTask(
        packId="ffmpeg",
        title=f"FFmpeg 安装 ({archLabel})",
        downloadUrl=assetInfo["url"],
        fallbackAssetName=assetInfo["name"],
        fallbackSize=assetInfo["size"],
        installFolder=Path(ffmpegConfig.installFolder.value),
        executableNames=[toExecutable("ffmpeg"), toExecutable("ffprobe")],
        headers=_FFMPEG_HEADERS,
    )


class FFmpegPack(FeaturePack):
    packId = "ffmpeg"
    config = ffmpegConfig

    def matches(self, url: str) -> bool:
        return url.strip() == FFMPEG_MERGE_URL

    async def parse(self, payload: dict) -> Task:
        return await createMergeTask(payload)

    def taskCard(self, task, parent=None):
        from disk_pack.task import InstallTask
        if isinstance(task, InstallTask):
            return UniversalTaskCard(task, parent)
        return super().taskCard(task, parent)
