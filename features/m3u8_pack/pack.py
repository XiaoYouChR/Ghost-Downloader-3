import platform
import sys
from email.message import Message
from email.utils import collapse_rfc2231_value
from pathlib import Path
from typing import TYPE_CHECKING, Literal
from urllib.parse import parse_qs, unquote, urlparse

import niquests

from app.bases.interfaces import FeaturePack
from app.bases.models import Task
from app.supports.config import DEFAULT_HEADERS, cfg
from app.supports.utils import getProxies, splitCookies, toExecutable, toSafeFilename
from .config import m3u8Config
from .task import M3U8TaskStage

if TYPE_CHECKING:
    from features.disk_pack.pack import buildToolInstallTask
else:
    from disk_pack.pack import buildToolInstallTask


_M3U8DL_RELEASE_TAG = "v0.5.1-beta"
_M3U8DL_RELEASE_API = f"https://api.github.com/repos/nilaoda/N_m3u8DL-RE/releases/tags/{_M3U8DL_RELEASE_TAG}"
_M3U8DL_RELEASE_HEADERS = {
    "accept": "application/vnd.github+json",
    "user-agent": DEFAULT_HEADERS["user-agent"],
}
_KNOWN_SUFFIXES = {
    ".m3u8", ".m3u", ".mpd", ".mp4", ".mkv",
    ".ts", ".webm", ".m4a", ".m4v", ".vtt", ".srt",
}


def _stem(name: str) -> str:
    suffix = Path(name).suffix
    if suffix.lower() in _KNOWN_SUFFIXES:
        return name[:-len(suffix)]
    return name


def _manifestType(url: str, headers: dict[str, str], body: str) -> Literal["m3u8", "mpd"]:
    loweredUrl = url.lower()
    contentType = headers.get("content-type", "").lower()
    sample = body.lstrip()[:256].lower()
    if ".mpd" in loweredUrl or "dash+xml" in contentType or sample.startswith("<mpd"):
        return "mpd"
    return "m3u8"


def _title(url: str, headers: dict[str, str], extension: str) -> str:
    candidates: list[str] = []

    cd = headers.get("content-disposition", "")
    if cd:
        msg = Message()
        msg["Content-Disposition"] = cd
        params = msg.get_params(header="Content-Disposition")
        paramDict = {key.lower(): value for key, value in params}
        fileName = collapse_rfc2231_value(
            paramDict.get("filename") or paramDict.get("filename*") or ""
        ).strip("\"' ")
        if fileName:
            candidates.append(fileName)

    parsedUrl = urlparse(url)
    query = parse_qs(parsedUrl.query)
    for key in ("filename", "file", "name", "title"):
        values = query.get(key)
        if values:
            candidates.append(values[0])

    if parsedUrl.path:
        candidates.append(unquote(Path(parsedUrl.path).name))

    for candidate in candidates:
        name = _stem(toSafeFilename(candidate, fallback="stream"))
        if name:
            return f"{name}.{extension}"

    return f"stream.{extension}"


class M3U8Pack(FeaturePack):
    packId = "m3u8"
    priority = 80
    config = m3u8Config

    def matches(self, url: str) -> bool:
        parsedUrl = urlparse(url)
        if parsedUrl.scheme.lower() not in {"http", "https"}:
            return False
        loweredUrl = url.lower()
        return ".m3u" in loweredUrl or ".mpd" in loweredUrl

    async def parse(self, payload: dict) -> Task:
        url = payload["url"].strip()
        rawHeaders = payload.get("headers", DEFAULT_HEADERS)
        headers = rawHeaders.copy() if isinstance(rawHeaders, dict) else DEFAULT_HEADERS.copy()
        proxies = payload.get("proxies", getProxies())
        path = Path(payload.get("path", cfg.downloadFolder.value))
        requestHeaders, requestCookies = splitCookies(headers)

        async with niquests.AsyncSession(timeout=30, happy_eyeballs=True) as client:
            client.trust_env = False
            response = await client.get(
                url,
                headers=requestHeaders,
                cookies=requestCookies,
                proxies=proxies,
                verify=cfg.SSLVerify.value,
                allow_redirects=True,
            )
            response.raise_for_status()
            body = response.text
            loweredHeaders = {key.lower(): value for key, value in response.headers.items()}

        manifestType = _manifestType(response.url, loweredHeaders, body)
        loweredBody = body.lower()
        if manifestType == "mpd":
            isLive = 'type="dynamic"' in loweredBody or "type='dynamic'" in loweredBody
        else:
            isLive = "#ext-x-endlist" not in loweredBody
        extension = "ts" if m3u8Config.liveRealTimeMerge.value else m3u8Config.outputFormat.value
        title = _title(response.url, loweredHeaders, extension)

        task = Task(
            title=title,
            url=url,
            packId=self.packId,
            fileSize=1,
            path=path,
            metadata={
                "manifestType": manifestType,
                "isLive": isLive,
            },
        )

        stage = M3U8TaskStage(
            stageIndex=1,
            headers=headers,
            proxies=proxies if isinstance(proxies, dict) else {},
            threadCount=m3u8Config.threadCount.value,
            retryCount=m3u8Config.retryCount.value,
            requestTimeout=m3u8Config.requestTimeout.value,
            autoSelect=m3u8Config.autoSelect.value,
            concurrentDownload=m3u8Config.concurrentDownload.value,
            appendUrlParams=m3u8Config.appendUrlParams.value,
            binaryMerge=m3u8Config.binaryMerge.value,
            checkSegmentsCount=m3u8Config.checkSegmentsCount.value,
            outputFormat=m3u8Config.outputFormat.value,
            liveRealTimeMerge=m3u8Config.liveRealTimeMerge.value,
            liveKeepSegments=m3u8Config.liveKeepSegments.value,
            livePipeMux=m3u8Config.livePipeMux.value,
        )
        task.addStage(stage)
        stage.updateOutputFile(path, title)
        return task


async def createInstallTask() -> Task:
    machine = platform.machine().lower()
    if sys.platform == "win32":
        if machine in {"amd64", "x86_64"}:
            target, archLabel = "win-x64", "Windows x64"
        elif machine in {"arm64", "aarch64"}:
            target, archLabel = "win-arm64", "Windows ARM64"
        else:
            target, archLabel = "win-NT6.0-x86", "Windows x86"
    elif sys.platform == "darwin":
        if machine in {"arm64", "aarch64"}:
            target, archLabel = "osx-arm64", "macOS Apple Silicon"
        else:
            target, archLabel = "osx-x64", "macOS Intel"
    elif sys.platform == "linux":
        libcName = platform.libc_ver()[0].lower()
        if machine in {"arm64", "aarch64"}:
            target, archLabel = ("linux-musl-arm64", "Linux musl ARM64") if libcName == "musl" else ("linux-arm64", "Linux ARM64")
        else:
            target, archLabel = ("linux-musl-x64", "Linux musl x64") if libcName == "musl" else ("linux-x64", "Linux x64")
    else:
        raise RuntimeError(f"当前平台暂不支持一键安装 N_m3u8DL-RE: {sys.platform}")

    async with niquests.AsyncSession(headers=_M3U8DL_RELEASE_HEADERS, timeout=30, happy_eyeballs=True) as client:
        client.trust_env = False
        response = await client.get(
            _M3U8DL_RELEASE_API,
            proxies=getProxies(),
            verify=cfg.SSLVerify.value,
            allow_redirects=True,
        )
        response.raise_for_status()
        payload = response.json()

    assets = payload.get("assets")
    if not isinstance(assets, list):
        raise RuntimeError("GitHub Release 返回了无效的 assets 数据")

    asset = next((item for item in assets if target in item["name"]), None)
    if asset is None:
        raise RuntimeError(f"未找到适用于当前平台的 N_m3u8DL-RE 安装包: {target}")

    downloadUrl = asset["browser_download_url"].strip()
    assetName = asset["name"].strip()
    size = asset["size"]
    if not downloadUrl or not assetName or size <= 0:
        raise RuntimeError("GitHub Release 返回了不完整的安装包信息")

    return await buildToolInstallTask(
        packId="m3u8",
        title=f"N_m3u8DL-RE 安装 ({archLabel})",
        downloadUrl=downloadUrl,
        fallbackAssetName=assetName,
        fallbackSize=size,
        installFolder=Path(m3u8Config.installFolder.value),
        executableNames=[toExecutable("N_m3u8DL-RE")],
    )
