import asyncio
import platform
import sys
from email.message import Message
from email.utils import collapse_rfc2231_value
from pathlib import Path
from typing import TYPE_CHECKING, Literal
from urllib.parse import parse_qs, unquote, urlparse
from urllib.request import url2pathname

import m3u8
import niquests
from loguru import logger
from mpegdash.parser import MPEGDASHParser

from app.bases.interfaces import FeaturePack, FileType
from app.bases.models import Task
from app.supports import file_association
from app.supports.config import activeUserAgent, cfg, defaultHeaders
from app.supports.utils import getProxies, splitCookies, toExecutable, toSafeFilename
from app.view.components.cards import UniversalTaskCard
from .cards import M3U8LiveTaskCard, M3U8ResultCard, M3U8TaskCard
from .config import m3u8Config
from .task import M3U8Task, M3U8TaskStage

if TYPE_CHECKING:
    from features.disk_pack.pack import buildToolInstallTask
else:
    from disk_pack.pack import buildToolInstallTask


_M3U8DL_RELEASE_TAG = "v0.5.1-beta"
_M3U8DL_RELEASE_API = f"https://api.github.com/repos/nilaoda/N_m3u8DL-RE/releases/tags/{_M3U8DL_RELEASE_TAG}"
_M3U8DL_RELEASE_HEADERS = {
    "accept": "application/vnd.github+json",
    "user-agent": activeUserAgent(),
}
_KNOWN_SUFFIXES = {
    ".m3u8", ".m3u", ".mpd", ".mp4", ".mkv",
    ".ts", ".webm", ".m4a", ".m4v", ".vtt", ".srt",
}
_MANIFEST_SUFFIXES = {".m3u8", ".m3u", ".mpd"}


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


def loadLocalManifest(source: str) -> Path | None:
    text = str(source).strip()
    if not text:
        return None

    parsed = urlparse(text)
    if parsed.scheme.lower() == "file":
        location = f"//{parsed.netloc}{parsed.path}" if parsed.netloc else parsed.path
        path = Path(url2pathname(unquote(location))).expanduser()
        return path if path.suffix.lower() in _MANIFEST_SUFFIXES else None

    if "://" in text:
        return None

    path = Path(text).expanduser()
    return path if path.suffix.lower() in _MANIFEST_SUFFIXES else None


def _toFrameRate(value) -> float | None:
    if not value:
        return None
    text = str(value)
    if "/" in text:
        num, den = text.split("/")
        return int(num) / int(den) if int(den) else None
    return float(text)


def _isVideoRepresentation(adaptationSet, representation) -> bool:
    if (adaptationSet.content_type or "").lower() == "video":
        return True
    mimeType = (adaptationSet.mime_type or representation.mime_type or "").lower()
    if mimeType.startswith("video"):
        return True
    return bool(representation.id and "video" in representation.id)


def _streamEntry(width: int, height: int, codecs: str | None, frameRate: float | None) -> dict:
    label = [f"{width}×{height}"]
    if codecs:
        label.append(codecs)
    if frameRate:
        label.append(f"{frameRate:.0f}fps")
    selectExpr = [f'res="{width}*"']
    if frameRate:
        selectExpr.append(f'frame="{int(frameRate)}*"')
    return {"label": " · ".join(label), "selectExpr": ":".join(selectExpr)}


def _hlsStreams(body: str) -> list[dict]:
    playlist = m3u8.loads(body)
    streams = []
    for variant in playlist.playlists:
        resolution = variant.stream_info.resolution
        if not resolution:
            continue
        width, height = resolution
        streams.append(_streamEntry(width, height, variant.stream_info.codecs, variant.stream_info.frame_rate))
    return streams


def _mpdStreams(body: str) -> list[dict]:
    mpd = MPEGDASHParser.parse(body)
    if not mpd.periods:
        return []
    streams = []
    for adaptationSet in mpd.periods[0].adaptation_sets:
        for representation in adaptationSet.representations:
            if not representation.width or not _isVideoRepresentation(adaptationSet, representation):
                continue
            streams.append(_streamEntry(
                representation.width,
                representation.height,
                representation.codecs,
                _toFrameRate(representation.frame_rate),
            ))
    return streams


def resolveStreams(manifestType: str, body: str) -> list[dict]:
    # 枚举失败不该阻断下载——auto-select 仍能工作, 仅轨道下拉缺项
    try:
        return _mpdStreams(body) if manifestType == "mpd" else _hlsStreams(body)
    except Exception as e:
        logger.warning("枚举可选视频流失败: {}", repr(e))
        return []


async def _resolveLive(manifestType: str, body: str, baseUrl: str, headers: dict, proxies) -> bool:
    if manifestType == "mpd":
        lowered = body.lower()
        return 'type="dynamic"' in lowered or "type='dynamic'" in lowered

    playlist = m3u8.loads(body, uri=baseUrl)
    if playlist.segments:
        return not playlist.is_endlist
    if not playlist.playlists:
        return "#ext-x-endlist" not in body.lower()

    # master playlist 本身无 ENDLIST, 真伪直播只能看其变体 media playlist
    variantUrl = playlist.playlists[0].absolute_uri or ""
    if not variantUrl.lower().startswith(("http://", "https://")):
        return False
    try:
        requestHeaders, requestCookies = splitCookies(headers)
        async with niquests.AsyncSession(timeout=30, happy_eyeballs=True) as client:
            client.trust_env = False
            response = await client.get(
                variantUrl,
                headers=requestHeaders,
                cookies=requestCookies,
                proxies=proxies,
                verify=cfg.SSLVerify.value,
                allow_redirects=True,
            )
            response.raise_for_status()
            variantBody = response.text
        return not m3u8.loads(variantBody, uri=variantUrl).is_endlist
    except Exception as e:
        logger.warning("取变体清单判活失败, 按点播处理: {}", repr(e))
        return False


class M3U8Pack(FeaturePack):
    packId = "m3u8"
    priority = 80
    config = m3u8Config

    def matches(self, url: str) -> bool:
        if loadLocalManifest(url) is not None:
            return True
        parsedUrl = urlparse(url)
        if parsedUrl.scheme.lower() not in {"http", "https"}:
            return False
        loweredUrl = url.lower()
        return ".m3u" in loweredUrl or ".mpd" in loweredUrl

    def fileTypes(self):
        return [
            FileType(
                extensions=(".m3u8", ".m3u"),
                displayName=self.tr("M3U8 播放列表"),
                mimeType="application/vnd.apple.mpegurl",
                icon="m3u8",
            ),
            FileType(
                extensions=(".mpd",),
                displayName=self.tr("DASH 清单"),
                mimeType="application/dash+xml",
                icon="m3u8",
            ),
        ]

    def taskCard(self, task, parent=None):
        from disk_pack.task import InstallTask
        if isinstance(task, InstallTask):
            return UniversalTaskCard(task, parent)
        if getattr(task, "isLive", False):
            return M3U8LiveTaskCard(task, parent)
        return M3U8TaskCard(task, parent)

    def resultCard(self, task, parent=None):
        return M3U8ResultCard(task, parent)

    def cardChips(self, task) -> list[str]:
        kind = "DASH" if getattr(task, "manifestType", "") == "mpd" else "HLS"
        if not getattr(task, "isLive", False):
            return [f"{kind} · 点播"]
        stage = task.stages[0] if task.stages else None
        recording = "等待中" if getattr(stage, "liveStatus", "") == "Waiting" else "录制中"
        return [f"{kind} · 直播 · {recording}"]

    def setup(self, mainWindow):
        if m3u8Config.associateFileTypes.value:
            file_association.register(self.fileTypes())
        m3u8Config.associateFileTypes.valueChanged.connect(self._onAssociationToggled)

    def _onAssociationToggled(self, enabled: bool):
        if enabled:
            file_association.register(self.fileTypes())
        else:
            file_association.unregister(self.fileTypes())

    async def parse(self, payload: dict) -> Task:
        url = payload["url"].strip()
        rawHeaders = payload.get("headers")
        headers = rawHeaders.copy() if isinstance(rawHeaders, dict) and rawHeaders else defaultHeaders()
        proxies = payload.get("proxies", getProxies())
        path = Path(payload.get("path", cfg.downloadFolder.value))

        localManifest = loadLocalManifest(url)
        if localManifest is not None:
            # N_m3u8DL-RE 的位置参数直接吃本地路径(_buildArgs 透传 task.url), 所以还原成 plain 路径而不留 file://
            url = str(localManifest.resolve())
            body = await asyncio.to_thread(localManifest.read_text, encoding="utf-8", errors="ignore")
            # 工具按输入路径解析相对段 → 落到本地不存在的文件; 只有带绝对 URL 段的清单可下,
            # 这里提前拦截纯相对清单, 避免下到一半才报错
            if "http://" not in body and "https://" not in body:
                raise ValueError("该本地清单只含相对段路径, 缺少 base URL 无法下载, 请改用原始在线链接")
            manifestUrl = url
            loweredHeaders = {}
        else:
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
            manifestUrl = response.url

        manifestType = _manifestType(manifestUrl, loweredHeaders, body)
        isLive = await _resolveLive(manifestType, body, manifestUrl, headers, proxies)
        # 直播恒走 real-time-merge 直出 .ts；点播按输出容器
        extension = "ts" if isLive else m3u8Config.outputFormat.value
        title = _title(manifestUrl, loweredHeaders, extension)
        streams = resolveStreams(manifestType, body)

        task = M3U8Task(
            title=title,
            url=url,
            fileSize=1,
            path=path,
            manifestType=manifestType,
            isLive=isLive,
            streams=streams,
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
            delAfterDone=m3u8Config.delAfterDone.value,
            outputFormat=m3u8Config.outputFormat.value,
            customMuxAfterDone=m3u8Config.customMuxAfterDone.value,
            subtitleFormat=m3u8Config.subtitleFormat.value,
            selectAllAudioSubtitle=m3u8Config.selectAllAudioSubtitle.value,
            maxSpeed=m3u8Config.maxSpeed.value,
            speedUnit=m3u8Config.speedUnit.value,
            adKeyword=m3u8Config.adKeyword.value,
            noDateInfo=m3u8Config.noDateInfo.value,
            keepImageSegments=m3u8Config.keepImageSegments.value,
            decryptionEngine=m3u8Config.decryptionEngine.value,
            decryptionBinaryPath=m3u8Config.decryptionBinaryPath.value,
            mp4RealTimeDecryption=m3u8Config.mp4RealTimeDecryption.value,
            liveKeepSegments=m3u8Config.liveKeepSegments.value,
            livePipeMux=m3u8Config.livePipeMux.value,
            liveFixVtt=m3u8Config.liveFixVtt.value,
            liveWaitTime=m3u8Config.liveWaitTime.value,
            liveTakeCount=m3u8Config.liveTakeCount.value,
        )
        task.addStage(stage)
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
