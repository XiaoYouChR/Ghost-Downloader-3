import asyncio
import platform
import re
import sys
from contextlib import suppress
from dataclasses import dataclass, field
from email.message import Message
from pathlib import Path
from typing import Any, TYPE_CHECKING
from urllib.parse import parse_qs, unquote, urlparse

import niquests
from loguru import logger

from app.bases.interfaces import Worker
from app.bases.models import Task, TaskStage, TaskStatus
from app.supports.config import DEFAULT_HEADERS, cfg
from app.supports.utils import getProxies, sanitizeFilename, splitRequestHeadersAndCookies
from .config import m3u8Config, resolveM3U8DownloaderExecutable

if TYPE_CHECKING:
    from features.ffmpeg_pack.config import resolveFFmpegExecutables
    from features.http_pack.task import HttpTaskStage
    from features.extract_pack.task import ExtractStage
else:
    from extract_pack.task import ExtractStage
    from ffmpeg_pack.config import resolveFFmpegExecutables
    from http_pack.task import HttpTaskStage


_KNOWN_SUFFIXES = {
    ".m3u8", ".m3u", ".mpd", ".mp4", ".mkv",
    ".ts", ".webm", ".m4a", ".m4v", ".vtt", ".srt",
}
_VOD_PROGRESS_PATTERN = re.compile(
    r"(\d+)/(\d+)\s+(\d+\.\d+)%\s+(\d+\.\d+)(KB|MB|GB|B)/(\d+\.\d+)(KB|MB|GB|B)\s+(\d+\.\d+)(GBps|MBps|KBps|Bps)\s+(.+)"
)
_LIVE_PROGRESS_PATTERN = re.compile(
    r"(\d{2}m\d{2}s)/(\d{2}m\d{2}s)\s+\d+/\d+\s+(Recording|Waiting)\s+(\d+)%\s+(-|(\d+\.\d+)(GBps|MBps|KBps|Bps))"
)
_M3U8DL_RELEASE_TAG = "v0.5.1-beta"
_M3U8DL_RELEASE_API = f"https://api.github.com/repos/nilaoda/N_m3u8DL-RE/releases/tags/{_M3U8DL_RELEASE_TAG}"
_M3U8DL_RELEASE_HEADERS = {
    "accept": "application/vnd.github+json",
    "user-agent": DEFAULT_HEADERS["user-agent"],
}


def _normalizePath(path: Path | str) -> str:
    return str(Path(path)).replace("\\", "/")


def _stripKnownSuffix(name: str) -> str:
    suffix = Path(name).suffix.lower()
    if suffix in _KNOWN_SUFFIXES:
        return name[:-len(suffix)]
    return name


def _parseContentDispositionName(headers: dict[str, str]) -> str:
    cd = headers.get("content-disposition", "")
    if not cd:
        return ""

    msg = Message()
    msg["Content-Disposition"] = cd
    params = msg.get_params(header="Content-Disposition")
    paramDict = {key.lower(): value for key, value in params if isinstance(value, str)}

    if "filename*" in paramDict and "'" in paramDict["filename*"]:
        encoding, _, encodedText = paramDict["filename*"].split("'", 2)
        return unquote(encodedText, encoding=encoding or "utf-8")
    if "filename" in paramDict:
        return paramDict["filename"].strip("\"' ")
    return ""


def _deriveManifestType(url: str, headers: dict[str, str], body: str) -> str:
    loweredUrl = url.lower()
    contentType = headers.get("content-type", "").lower()
    sample = body.lstrip()[:256].lower()

    if ".mpd" in loweredUrl or "dash+xml" in contentType or sample.startswith("<mpd"):
        return "mpd"
    return "m3u8"


def _detectLive(manifestType: str, body: str) -> bool:
    loweredBody = body.lower()
    if manifestType == "mpd":
        return 'type="dynamic"' in loweredBody or "type='dynamic'" in loweredBody
    return "#ext-x-endlist" not in loweredBody


def _deriveDefaultTitle(url: str, headers: dict[str, str], extension: str) -> str:
    candidates: list[str] = []
    if name := _parseContentDispositionName(headers):
        candidates.append(name)

    parsedUrl = urlparse(url)
    query = parse_qs(parsedUrl.query)
    for key in ("filename", "file", "name", "title"):
        values = query.get(key)
        if values:
            candidates.append(values[0])

    if parsedUrl.path:
        candidates.append(unquote(Path(parsedUrl.path).name))

    for candidate in candidates:
        name = _stripKnownSuffix(sanitizeFilename(candidate, fallback="stream"))
        if name:
            return f"{name}.{extension}"

    return f"stream.{extension}"


def _bytesFromUnit(value: str, unit: str) -> int:
    scale = {
        "B": 1, "KB": 1024, "MB": 1024 ** 2, "GB": 1024 ** 3,
        "Bps": 1, "KBps": 1024, "MBps": 1024 ** 2, "GBps": 1024 ** 3,
    }
    return int(float(value) * scale[unit])


def _boolText(value: bool) -> str:
    return "true" if value else "false"


def _pickProxy(proxies: dict | None) -> str:
    if not isinstance(proxies, dict):
        return ""
    for key in ("https", "http"):
        value = str(proxies.get(key) or "").strip()
        if value:
            return value
    return ""


def _executableName(name: str) -> str:
    return f"{name}.exe" if sys.platform == "win32" else name


def _detectRuntimeTarget() -> tuple[str, str]:
    machine = platform.machine().lower()

    if sys.platform == "win32":
        if machine in {"amd64", "x86_64"}:
            return "win-x64", "Windows x64"
        if machine in {"arm64", "aarch64"}:
            return "win-arm64", "Windows ARM64"
        return "win-NT6.0-x86", "Windows x86"

    if sys.platform == "darwin":
        if machine in {"arm64", "aarch64"}:
            return "osx-arm64", "macOS Apple Silicon"
        return "osx-x64", "macOS Intel"

    if sys.platform == "linux":
        libcName = platform.libc_ver()[0].lower()
        if machine in {"arm64", "aarch64"}:
            return ("linux-musl-arm64", "Linux musl ARM64") if libcName == "musl" else ("linux-arm64", "Linux ARM64")
        return ("linux-musl-x64", "Linux musl x64") if libcName == "musl" else ("linux-x64", "Linux x64")

    raise RuntimeError(f"当前平台暂不支持一键安装 N_m3u8DL-RE: {sys.platform}")


def _selectReleaseAsset(assets: list[dict[str, Any]]) -> dict[str, Any]:
    target, _ = _detectRuntimeTarget()
    for asset in assets:
        name = str(asset.get("name") or "")
        if target in name:
            return asset
    raise RuntimeError(f"未找到适用于当前平台的 N_m3u8DL-RE 安装包: {target}")


async def _requestReleaseAsset() -> dict[str, Any]:
    client = niquests.AsyncSession(headers=_M3U8DL_RELEASE_HEADERS, timeout=30, happy_eyeballs=True)
    client.trust_env = False

    try:
        response = await client.get(
            _M3U8DL_RELEASE_API,
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
        raise RuntimeError("GitHub Release 返回了不完整的安装包信息")

    return {
        "name": assetName,
        "url": downloadUrl,
        "size": size,
    }


@dataclass(kw_only=True)
class M3U8TaskStage(TaskStage):
    workerType: type = field(init=False, repr=False)
    canPause: bool = field(init=False, default=False)

    outputFile: str = ""
    tempDir: str = ""
    lastMessage: str = ""

    def updateOutputFile(self, taskPath: Path, taskTitle: str):
        meta = self.task.metadata
        outputExtension = meta.get("actualExtension") or (
            "ts" if meta.get("liveRealTimeMerge") else meta.get("outputFormat", "mp4")
        )
        suffix = f".{outputExtension.lower()}"
        if taskTitle.lower().endswith(suffix):
            saveName = taskTitle[:-len(suffix)]
        else:
            saveName = _stripKnownSuffix(taskTitle)

        self.outputFile = _normalizePath(taskPath / taskTitle)
        self.tempDir = _normalizePath(taskPath / ".gd3_m3u8" / self.task.taskId)


class M3U8Worker(Worker):
    def __init__(self, stage: M3U8TaskStage):
        super().__init__(stage)
        self.stage = stage
        self.task = stage.task

    def _buildArguments(self, downloaderPath: str) -> list[str]:
        meta = self.task.metadata
        outputExtension = meta.get("actualExtension") or (
            "ts" if meta.get("liveRealTimeMerge") else meta.get("outputFormat", "mp4")
        )
        suffix = f".{outputExtension.lower()}"
        title = self.task.title
        if title.lower().endswith(suffix):
            saveName = title[:-len(suffix)]
        else:
            saveName = _stripKnownSuffix(title)

        args = [
            self.task.url,
            f"--save-dir={self.task.path}",
            f"--save-name={saveName}",
            f"--tmp-dir={self.stage.tempDir}",
            f"--thread-count={meta.get('threadCount', 16)}",
            f"--download-retry-count={meta.get('retryCount', 3)}",
            f"--http-request-timeout={meta.get('requestTimeout', 10)}",
            f"--auto-select={_boolText(meta.get('autoSelect', True))}",
            f"--concurrent-download={_boolText(meta.get('concurrentDownload', True))}",
            f"--append-url-params={_boolText(meta.get('appendUrlParams', False))}",
            f"--binary-merge={_boolText(meta.get('binaryMerge', False))}",
            f"--check-segments-count={_boolText(meta.get('checkSegmentsCount', True))}",
            "--del-after-done=true",
            "--write-meta-json=false",
            "--no-log=true",
            "--no-ansi-color=true",
            "--disable-update-check=true",
        ]

        proxies = meta.get("proxies")
        proxyUrl = _pickProxy(proxies)
        args.append("--use-system-proxy=false")
        if proxyUrl:
            args.append(f"--custom-proxy={proxyUrl}")

        ffmpegPath, _ = resolveFFmpegExecutables()
        if ffmpegPath:
            args.append(f"--ffmpeg-binary-path={ffmpegPath}")

        if meta.get("liveRealTimeMerge"):
            args.append("--live-real-time-merge=true")
            args.append(f"--live-keep-segments={_boolText(meta.get('liveKeepSegments', False))}")
            args.append(f"--live-pipe-mux={_boolText(meta.get('livePipeMux', False))}")
        else:
            outputFormat = meta.get("outputFormat", "mp4")
            muxOption = f"format={outputFormat}:muxer=ffmpeg"
            if ffmpegPath:
                muxOption += f":bin_path={ffmpegPath}"
            args.append(f"--mux-after-done={muxOption}")

        headers = meta.get("headers", {})
        for name, value in headers.items():
            if value is None:
                continue
            text = str(value).strip()
            if not text:
                continue
            args.extend(["-H", f"{name}: {text}"])

        return args

    def _handleOutputLine(self, line: str):
        text = line.strip()
        if not text:
            return

        self.stage.lastMessage = text[:1000]

        vodMatch = _VOD_PROGRESS_PATTERN.search(text)
        if vodMatch:
            progress = float(vodMatch.group(3))
            currentSize = _bytesFromUnit(vodMatch.group(4), vodMatch.group(5))
            totalSize = _bytesFromUnit(vodMatch.group(6), vodMatch.group(7))
            speed = _bytesFromUnit(vodMatch.group(8), vodMatch.group(9))
            self.stage.progress = progress
            self.stage.receivedBytes = currentSize
            self.stage.speed = speed
            if totalSize > 0:
                self.task.fileSize = totalSize
            return

        liveMatch = _LIVE_PROGRESS_PATTERN.search(text)
        if liveMatch:
            self.stage.progress = float(liveMatch.group(4))
            self.stage.speed = 0 if liveMatch.group(5) == "-" else _bytesFromUnit(liveMatch.group(6), liveMatch.group(7))

    async def _readOutput(self, stream: asyncio.StreamReader | None):
        if stream is None:
            return

        buffer = ""
        while True:
            chunk = await stream.read(4096)
            if not chunk:
                break

            buffer += chunk.decode("utf-8", errors="ignore")
            buffer = buffer.replace("\r\n", "\n").replace("\r", "\n")
            lines = buffer.split("\n")
            buffer = lines.pop()
            for line in lines:
                self._handleOutputLine(line)

        if buffer.strip():
            self._handleOutputLine(buffer)

    def _resolveFinalOutput(self) -> Path | None:
        target = Path(self.stage.outputFile)
        if target.is_file():
            return target

        outputDir = self.task.path
        if not outputDir.is_dir():
            return None

        meta = self.task.metadata
        outputExtension = meta.get("actualExtension") or (
            "ts" if meta.get("liveRealTimeMerge") else meta.get("outputFormat", "mp4")
        )
        suffix = f".{outputExtension.lower()}"
        title = self.task.title
        if title.lower().endswith(suffix):
            saveName = title[:-len(suffix)]
        else:
            saveName = _stripKnownSuffix(title)

        candidates: list[Path] = []
        prefix = saveName.lower()
        ignoredSuffixes = {".json", ".txt", ".log", ".tmp", ".ghd"}

        for candidate in outputDir.iterdir():
            if not candidate.is_file():
                continue
            if candidate.suffix.lower() in ignoredSuffixes:
                continue
            if not candidate.name.lower().startswith(prefix):
                continue
            candidates.append(candidate)

        if not candidates:
            return None

        expectedSuffix = f".{outputExtension}"
        candidates.sort(
            key=lambda path: (
                path.suffix.lower() != expectedSuffix,
                -path.stat().st_mtime,
            )
        )
        return candidates[0]

    def _syncFinalOutput(self):
        candidate = self._resolveFinalOutput()
        if candidate is None:
            return

        self.task.metadata["actualExtension"] = candidate.suffix.lstrip(".")
        self.task.fileSize = max(self.task.fileSize, candidate.stat().st_size)
        if candidate.name != self.task.title:
            self.task.setTitle(candidate.name)

    async def _stopProcess(self, process: asyncio.subprocess.Process):
        if process.returncode is not None:
            return

        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=3)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()

    async def run(self):
        downloaderPath = resolveM3U8DownloaderExecutable()
        if not downloaderPath:
            raise RuntimeError("未找到可用的 N_m3u8DL-RE，请先在设置中安装或配置运行时")

        self.task.path.mkdir(parents=True, exist_ok=True)
        Path(self.stage.tempDir).mkdir(parents=True, exist_ok=True)

        process = None
        outputTask = None
        try:
            args = self._buildArguments(downloaderPath)
            process = await asyncio.create_subprocess_exec(
                downloaderPath,
                *args,
                cwd=str(Path(downloaderPath).parent),
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            outputTask = asyncio.create_task(self._readOutput(process.stdout))

            await process.wait()
            if outputTask is not None:
                await outputTask

            if process.returncode != 0:
                message = self.stage.lastMessage or f"N_m3u8DL-RE 退出码异常: {process.returncode}"
                raise RuntimeError(message)

            self._syncFinalOutput()
            self.stage.setStatus(TaskStatus.COMPLETED)
        except asyncio.CancelledError:
            self.stage.setStatus(TaskStatus.PAUSED)
            if process is not None:
                await self._stopProcess(process)
            if outputTask is not None and not outputTask.done():
                outputTask.cancel()
                with suppress(asyncio.CancelledError):
                    await outputTask
            raise
        except Exception as e:
            self.stage.setError(e)
            raise


M3U8TaskStage.workerType = M3U8Worker


async def createInstallTask() -> Task:
    from app.services.feature_service import featureService

    assetInfo = await _requestReleaseAsset()
    _, archLabel = _detectRuntimeTarget()
    installFolder = m3u8Config.installFolder.value

    downloadPayload = {
        "url": assetInfo["url"],
        "headers": DEFAULT_HEADERS.copy(),
        "proxies": getProxies(),
        "path": Path(installFolder),
    }
    downloadTask = await featureService.resolve(downloadPayload)

    if not downloadTask.stages:
        raise RuntimeError("解析 N_m3u8DL-RE 安装包链接后未获取到下载阶段")

    downloadStage: HttpTaskStage = downloadTask.stages[0]
    archiveSize = downloadTask.fileSize if downloadTask.fileSize > 0 else assetInfo["size"]
    assetName = downloadTask.title or str(assetInfo["name"])
    archivePath = _normalizePath(Path(installFolder) / assetName)

    downloadStage.stageIndex = 1
    downloadStage.outputFile = archivePath

    task = Task(
        title=f"N_m3u8DL-RE 安装 ({archLabel})",
        url=assetInfo["url"],
        packId="m3u8",
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
        installFolder=_normalizePath(Path(installFolder)),
        executableNames=[_executableName("N_m3u8DL-RE")],
    ))
    return task
