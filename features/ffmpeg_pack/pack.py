import platform
import sys
from pathlib import Path
from typing import Any, TYPE_CHECKING
from urllib.parse import urlparse

import niquests
from loguru import logger

from app.bases.interfaces import FeaturePack
from app.bases.models import Task, SpecialFileSize
from app.supports.config import DEFAULT_HEADERS, cfg
from app.supports.utils import getProxies, toExecutable, toPosixPath, toSafeFilename
from .config import ffmpegConfig, ffmpegPaths
from .task import FFmpegStage

if TYPE_CHECKING:
    from features.http_pack.task import HttpTaskStage
    from features.extract_pack.task import ExtractStage
else:
    from http_pack.task import HttpTaskStage
    from extract_pack.task import ExtractStage


FFMPEG_MERGE_URL = "gd3+ffmpeg://merge"

_FFMPEG_RELEASE_API = "https://api.github.com/repos/BtbN/FFmpeg-Builds/releases/latest"
_FFMPEG_HEADERS = {
    "accept": "application/vnd.github+json",
    "user-agent": DEFAULT_HEADERS["user-agent"],
}



def _resourceExtension(name: str, url: str) -> str:
    fileName = Path(name).name if name else Path(urlparse(url).path).name
    return Path(fileName).suffix.lstrip(".").lower()


def _mergeOutputTitle(title: str) -> str:
    baseTitle = toSafeFilename(title, fallback="merged-media")
    if baseTitle.lower().endswith(".mp4"):
        return baseTitle
    return f"{baseTitle}.mp4"


def _detectWindowsTarget() -> tuple[str, str]:
    if sys.platform != "win32":
        raise RuntimeError("一键安装 FFmpeg 仅支持 Windows 平台")

    machine = platform.machine().lower()
    if machine in {"amd64", "x86_64"}:
        return "win64", "x64"
    if machine in {"arm64", "aarch64"}:
        return "winarm64", "arm64"
    raise RuntimeError(f"不支持的 Windows 架构: {platform.machine()}")


def _selectReleaseAsset(assets: list[dict[str, Any]]) -> dict[str, Any]:
    target, _ = _detectWindowsTarget()
    candidates: list[tuple[int, dict[str, Any]]] = []
    for asset in assets:
        name = str(asset.get("name") or "")
        lowerName = name.lower()
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

    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


async def _requestLatestReleaseAsset() -> dict[str, Any]:
    client = niquests.AsyncSession(headers=_FFMPEG_HEADERS, timeout=30, happy_eyeballs=True)
    client.trust_env = False

    try:
        response = await client.get(
            _FFMPEG_RELEASE_API,
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
        await client.close()

    assets = payload.get("assets")
    if not isinstance(assets, list):
        raise RuntimeError("GitHub Release 返回了无效的 assets 数据")

    asset = _selectReleaseAsset(assets)
    downloadUrl = str(asset.get("browser_download_url") or "").strip()
    assetName = str(asset.get("name") or "").strip()
    size = int(asset.get("size") or 0)
    if not downloadUrl or not assetName or size <= 0:
        raise RuntimeError("GitHub Release 返回了不完整的 FFmpeg 安装包信息")

    return {
        "name": assetName,
        "url": downloadUrl,
        "size": size,
    }


async def createMergeTask(payload: dict[str, Any], title: str = "") -> Task:
    ffmpeg, ffprobe = ffmpegPaths()
    if not ffmpeg or not ffprobe:
        raise RuntimeError("未找到可用的 ffmpeg 和 ffprobe，请先在设置中安装或配置 FFmpeg")

    from app.services.feature_service import featureService

    resources = payload.get("resources") or []
    if len(resources) != 2:
        raise RuntimeError("在线合并暂时只支持 2 个 HTTP 音视频资源")

    parsedResources: list[tuple[dict[str, Any], Task]] = []
    for item in resources:
        url = str(item.get("url") or "").strip()
        if not url.startswith(("http://", "https://")):
            raise RuntimeError("在线合并暂不支持 blob 或非 HTTP 资源")

        resourcePayload = {
            "url": url,
            "filename": str(item.get("filename") or "").strip(),
            "headers": item.get("headers") or {},
            "size": item.get("size") or 0,
            "supportsRange": bool(item.get("supportsRange")),
            "proxies": payload.get("proxies", getProxies()),
            "path": Path(payload.get("path", cfg.downloadFolder.value)),
            "preBlockNum": payload.get("preBlockNum", cfg.preBlockNum.value),
        }

        if resourcePayload["filename"]:
            resourcePayload["fileSize"] = resourcePayload.pop("size") or SpecialFileSize.UNKNOWN
            resourceTask = featureService.build(resourcePayload)
        else:
            resourceTask = await featureService.resolve(resourcePayload)

        if not resourceTask.stages:
            raise RuntimeError("解析在线合并源文件失败")

        parsedResources.append((item, resourceTask))

    outputTitle = _mergeOutputTitle(
        title
        or str(payload.get("outputTitle") or "").strip()
        or str(parsedResources[0][0].get("pageTitle") or "").strip()
        or "merged-media"
    )

    videoTask = parsedResources[0][1]
    audioTask = parsedResources[1][1]
    videoStage: HttpTaskStage = videoTask.stages[0]
    audioStage: HttpTaskStage = audioTask.stages[0]

    videoExt = _resourceExtension(videoTask.title, videoStage.url)
    audioExt = _resourceExtension(audioTask.title, audioStage.url)
    path = Path(payload.get("path", cfg.downloadFolder.value))
    finalPath = path / outputTitle
    videoPath = finalPath.with_name(f"{finalPath.stem}.video{f'.{videoExt}' if videoExt else ''}")
    audioPath = finalPath.with_name(f"{finalPath.stem}.audio{f'.{audioExt}' if audioExt else ''}")

    videoStage.stageIndex = 1
    videoStage.outputFile = str(videoPath)
    audioStage.stageIndex = 2
    audioStage.outputFile = str(audioPath)

    task = Task(
        title=outputTitle,
        url=videoStage.url,
        packId="ffmpeg",
        fileSize=max(0, videoTask.fileSize) + max(0, audioTask.fileSize),
        path=path,
        metadata={
            "proxies": payload.get("proxies", getProxies()),
            "blockNum": payload.get("preBlockNum", cfg.preBlockNum.value),
            "videoFileName": videoTask.title,
            "audioFileName": audioTask.title,
        },
    )
    task.addStage(videoStage)
    task.addStage(audioStage)
    task.addStage(FFmpegStage(
        stageIndex=3,
        videoPath=str(videoPath),
        audioPath=str(audioPath),
        outputFile=str(finalPath),
    ))
    return task


async def createInstallTask() -> Task:
    from app.services.feature_service import featureService

    assetInfo = await _requestLatestReleaseAsset()
    _, archLabel = _detectWindowsTarget()
    installFolder = ffmpegConfig.installFolder.value

    downloadPayload = {
        "url": assetInfo["url"],
        "headers": _FFMPEG_HEADERS.copy(),
        "proxies": getProxies(),
        "path": Path(installFolder),
    }
    downloadTask = await featureService.resolve(downloadPayload)

    if not downloadTask.stages:
        raise RuntimeError("解析 FFmpeg 下载链接后未获取到下载阶段")

    downloadStage: HttpTaskStage = downloadTask.stages[0]
    archiveSize = downloadTask.fileSize if downloadTask.fileSize > 0 else assetInfo["size"]
    assetName = downloadTask.title or str(assetInfo["name"])
    archivePath = toPosixPath(Path(installFolder) / assetName)

    downloadStage.stageIndex = 1
    downloadStage.outputFile = archivePath

    task = Task(
        title=f"FFmpeg 安装 ({archLabel})",
        url=downloadTask.url,
        packId="ffmpeg",
        fileSize=archiveSize,
        path=Path(installFolder),
        usesSlot=False,
        metadata={
            "archiveSize": archiveSize,
            "installFolder": installFolder,
            "assetName": assetName,
        },
    )
    task.addStage(downloadStage)
    task.addStage(ExtractStage(
        stageIndex=2,
        archivePath=archivePath,
        installFolder=toPosixPath(Path(installFolder)),
        executableNames=[toExecutable("ffmpeg"), toExecutable("ffprobe")],
    ))
    return task


class FFmpegPack(FeaturePack):
    packId = "ffmpeg"
    config = ffmpegConfig

    def matches(self, url: str) -> bool:
        return str(url).strip() == FFMPEG_MERGE_URL

    async def resolve(self, payload: dict) -> dict:
        return {"_task": await createMergeTask(payload)}

    def build(self, payload: dict) -> Task:
        return payload["_task"]
