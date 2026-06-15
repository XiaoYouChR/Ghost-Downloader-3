import asyncio
import platform
import sys
from pathlib import Path
from urllib.parse import urlparse

import niquests

from app.bases.interfaces import FeaturePack
from app.bases.models import Task
from app.supports.config import activeUserAgent, cfg, defaultHeaders
from app.supports.utils import getProxies, toExecutable, toPosixPath, toSafeFilename
from .config import downloaderPath, ytDlpConfig
from .task import YtDlpInstallStage, YtDlpTask, YtDlpTaskStage

_YTDLP_RELEASE_API = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"
_YTDLP_RELEASE_HEADERS = {
    "accept": "application/vnd.github+json",
    "user-agent": activeUserAgent(),
}
_YOUTUBE_HOSTS = ("youtube.com", "youtu.be")


def _assetName() -> str:
    # yt-dlp serves a self-contained executable per platform — pick the one yt-dlp itself names.
    machine = platform.machine().lower()
    if sys.platform == "win32":
        return "yt-dlp.exe"
    if sys.platform == "darwin":
        return "yt-dlp_macos"
    if machine in {"arm64", "aarch64"}:
        return "yt-dlp_linux_aarch64"
    return "yt-dlp_linux"


async def _probeTitle(url: str, proxies: dict) -> str:
    execPath = downloaderPath()
    if not execPath:
        return ""
    args = [url, "--no-playlist", "--skip-download", "--no-warnings", "--print", "%(title)s"]
    proxyUrl = next((v for v in proxies.values() if v), "")
    if proxyUrl:
        args.extend(["--proxy", proxyUrl])
    try:
        process = await asyncio.create_subprocess_exec(
            execPath, *args,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=20)
    except asyncio.TimeoutError:
        process.kill()
        return ""
    except OSError:
        return ""
    if process.returncode != 0:
        return ""
    lines = stdout.decode("utf-8", errors="ignore").strip().splitlines()
    return lines[0].strip() if lines else ""


class YtDlpPack(FeaturePack):
    packId = "ytdlp"
    # Below http (100) so YouTube watch pages route here instead of being grabbed as HTML.
    priority = 70
    config = ytDlpConfig

    def matches(self, url: str) -> bool:
        host = (urlparse(url).hostname or "").lower()
        return any(host == h or host.endswith(f".{h}") for h in _YOUTUBE_HOSTS)

    async def parse(self, payload: dict) -> Task:
        url = payload["url"].strip()
        proxies = payload.get("proxies", getProxies())
        path = Path(payload.get("path", cfg.downloadFolder.value))
        rawHeaders = payload.get("headers")
        headers = rawHeaders.copy() if isinstance(rawHeaders, dict) and rawHeaders else {}

        # Best-effort title for the dialog/card. The real filename + size land back from
        # yt-dlp at download time (-o %(title)s + after_move filepath), so a blocked probe
        # just falls back to the placeholder and the task still enqueues.
        probedTitle = await _probeTitle(url, proxies)
        title = toSafeFilename(probedTitle) if probedTitle else "YouTube 视频"

        task = YtDlpTask(title=f"{title}.mp4", url=url, fileSize=1, path=path)
        task.addStage(YtDlpTaskStage(
            stageIndex=1,
            videoFormat=ytDlpConfig.videoFormat.value,
            headers=headers,
            proxies=proxies if isinstance(proxies, dict) else {},
        ))
        return task


async def createInstallTask() -> Task:
    from app.services.feature_service import featureService
    from disk_pack.task import InstallTask

    assetName = _assetName()
    installFolder = Path(ytDlpConfig.installFolder.value)
    binaryPath = installFolder / toExecutable("yt-dlp")

    async with niquests.AsyncSession(headers=_YTDLP_RELEASE_HEADERS, timeout=30, happy_eyeballs=True) as client:
        client.trust_env = False
        response = await client.get(
            _YTDLP_RELEASE_API,
            proxies=getProxies(),
            verify=cfg.SSLVerify.value,
            allow_redirects=True,
        )
        response.raise_for_status()
        payload = response.json()

    assets = payload.get("assets")
    if not isinstance(assets, list):
        raise RuntimeError("GitHub Release 返回了无效的 assets 数据")

    asset = next((item for item in assets if item.get("name") == assetName), None)
    if asset is None:
        raise RuntimeError(f"未找到适用于当前平台的 yt-dlp 安装包: {assetName}")

    downloadUrl = asset["browser_download_url"].strip()
    size = asset["size"]
    if not downloadUrl or size <= 0:
        raise RuntimeError("GitHub Release 返回了不完整的安装包信息")

    # Reuse http_pack to download the single binary straight to its final path, then chmod.
    downloadTask = await featureService.parse({
        "url": downloadUrl,
        "headers": defaultHeaders(),
        "proxies": getProxies(),
        "path": installFolder,
    })
    if not downloadTask.stages:
        raise RuntimeError("解析 yt-dlp 下载链接后未获取到下载阶段")
    downloadStage = downloadTask.stages[0]
    downloadStage.stageIndex = 1
    downloadStage.outputFile = toPosixPath(binaryPath)

    task = InstallTask(
        title=f"yt-dlp 安装 ({assetName})",
        url=downloadUrl,
        packId="ytdlp",
        fileSize=size,
        path=installFolder,
        usesSlot=False,
        installFolder=str(installFolder),
    )
    task.addStage(downloadStage)
    task.addStage(YtDlpInstallStage(stageIndex=2, binaryPath=toPosixPath(binaryPath)))
    return task
