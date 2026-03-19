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
from app.services.core_service import coreService
from app.supports.config import DEFAULT_HEADERS, cfg
from app.supports.utils import getProxies
from .config import m3u8Config, resolveM3U8DownloaderExecutable

if TYPE_CHECKING:
    from features.ffmpeg_pack.config import resolveFFmpegExecutables
    from features.http_pack.task import HttpTaskStage, HttpWorker, httpConfig
    from features.extract_pack.task import ExtractStage, ExtractWorker
else:
    try:
        from extract_pack.task import ExtractStage, ExtractWorker
        from ffmpeg_pack.config import resolveFFmpegExecutables
        from http_pack.task import HttpTaskStage, HttpWorker, httpConfig
    except ImportError:
        from features.extract_pack.task import ExtractStage, ExtractWorker
        from features.ffmpeg_pack.config import resolveFFmpegExecutables
        from features.http_pack.task import HttpTaskStage, HttpWorker, httpConfig


_KNOWN_SUFFIXES = {
    ".m3u8",
    ".m3u",
    ".mpd",
    ".mp4",
    ".mkv",
    ".ts",
    ".webm",
    ".m4a",
    ".m4v",
    ".vtt",
    ".srt",
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


def _sanitizeName(name: str) -> str:
    cleaned = re.sub(r'[\x00-\x1f\\/:*?"<>|]+', "_", str(name or "")).strip().rstrip(".")
    return cleaned or "stream"


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
        name = _stripKnownSuffix(_sanitizeName(Path(candidate).name))
        if name:
            return f"{name}.{extension}"

    return f"stream.{extension}"


def _bytesFromUnit(value: str, unit: str) -> int:
    scale = {
        "B": 1,
        "KB": 1024,
        "MB": 1024 ** 2,
        "GB": 1024 ** 3,
        "Bps": 1,
        "KBps": 1024,
        "MBps": 1024 ** 2,
        "GBps": 1024 ** 3,
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


@dataclass
class M3U8TaskStage(TaskStage):
    resolvePath: str
    tempDir: str
    lastMessage: str = field(default="")


@dataclass
class M3U8Task(Task):
    headers: dict = field(default_factory=DEFAULT_HEADERS.copy)
    proxies: dict | None = field(default_factory=getProxies)
    threadCount: int = field(default_factory=lambda: m3u8Config.threadCount.value)
    retryCount: int = field(default_factory=lambda: m3u8Config.retryCount.value)
    requestTimeout: int = field(default_factory=lambda: m3u8Config.requestTimeout.value)
    autoSelect: bool = field(default_factory=lambda: m3u8Config.autoSelect.value)
    concurrentDownload: bool = field(default_factory=lambda: m3u8Config.concurrentDownload.value)
    appendUrlParams: bool = field(default_factory=lambda: m3u8Config.appendUrlParams.value)
    binaryMerge: bool = field(default_factory=lambda: m3u8Config.binaryMerge.value)
    checkSegmentsCount: bool = field(default_factory=lambda: m3u8Config.checkSegmentsCount.value)
    outputFormat: str = field(default_factory=lambda: m3u8Config.outputFormat.value)
    liveRealTimeMerge: bool = field(default_factory=lambda: m3u8Config.liveRealTimeMerge.value)
    liveKeepSegments: bool = field(default_factory=lambda: m3u8Config.liveKeepSegments.value)
    livePipeMux: bool = field(default_factory=lambda: m3u8Config.livePipeMux.value)
    manifestType: str = field(default="m3u8")
    isLive: bool = field(default=False)
    actualExtension: str = field(default="")

    def __post_init__(self):
        self.title = self._normalizeTitle(self.title)
        super().__post_init__()
        self.syncStagePaths()

    @property
    def outputExtension(self) -> str:
        if self.actualExtension:
            return self.actualExtension
        if self.liveRealTimeMerge:
            return "ts"
        return self.outputFormat

    @property
    def saveName(self) -> str:
        suffix = f".{self.outputExtension.lower()}"
        if self.title.lower().endswith(suffix):
            return self.title[:-len(suffix)]
        return _stripKnownSuffix(self.title)

    @property
    def tempDir(self) -> str:
        return _normalizePath(Path(self.path) / ".gd3_m3u8" / self.taskId)

    def _normalizeTitle(self, title: str) -> str:
        name = _sanitizeName(Path(str(title).strip() or "stream").name)
        suffix = f".{self.outputExtension.lower()}"
        if name.lower().endswith(suffix):
            return name
        name = _stripKnownSuffix(name)
        return f"{name}.{self.outputExtension}"

    def setTitle(self, title: str):
        self.title = self._normalizeTitle(title)
        self.syncStagePaths()

    def syncStagePaths(self):
        resolvePath = _normalizePath(Path(self.path) / self.title)
        tempDir = self.tempDir
        for stage in self.stages:
            if isinstance(stage, M3U8TaskStage):
                stage.resolvePath = resolvePath
                stage.tempDir = tempDir

    def applyPayloadToTask(self, payload: dict[str, Any]):
        super().applyPayloadToTask(payload)

        headers = payload.get("headers")
        if isinstance(headers, dict):
            self.headers = headers.copy()

        if "proxies" in payload:
            proxies = payload.get("proxies")
        else:
            proxies = self.proxies
        if isinstance(proxies, dict) or proxies is None:
            self.proxies = proxies

        self.syncStagePaths()

    async def run(self):
        self.stages.sort(key=lambda stage: stage.stageIndex)
        currentStage = None
        try:
            for stage in self.stages:
                if self.status != TaskStatus.RUNNING:
                    break
                if stage.status == TaskStatus.COMPLETED:
                    continue

                currentStage = stage
                if isinstance(stage, M3U8TaskStage):
                    await M3U8Worker(stage).run()
                    continue

                raise TypeError(f"不支持的 M3U8TaskStage: {type(stage).__name__}")
        except asyncio.CancelledError:
            logger.info(f"{self.title} 停止下载")
            raise
        except Exception as e:
            if currentStage is not None and not currentStage.error:
                currentStage.setError(e)
            logger.opt(exception=e).error("{} 下载失败", self.title)
            raise

    def __hash__(self):
        return hash(self.taskId)


class M3U8Worker(Worker):
    def __init__(self, stage: M3U8TaskStage):
        super().__init__(stage)
        self.stage = stage
        self.task: M3U8Task = getattr(stage, "_task")

    def _buildArguments(self, downloaderPath: str) -> list[str]:
        args = [
            self.task.url,
            f"--save-dir={self.task.path}",
            f"--save-name={self.task.saveName}",
            f"--tmp-dir={self.stage.tempDir}",
            f"--thread-count={self.task.threadCount}",
            f"--download-retry-count={self.task.retryCount}",
            f"--http-request-timeout={self.task.requestTimeout}",
            f"--auto-select={_boolText(self.task.autoSelect)}",
            f"--concurrent-download={_boolText(self.task.concurrentDownload)}",
            f"--append-url-params={_boolText(self.task.appendUrlParams)}",
            f"--binary-merge={_boolText(self.task.binaryMerge)}",
            f"--check-segments-count={_boolText(self.task.checkSegmentsCount)}",
            "--del-after-done=true",
            "--write-meta-json=false",
            "--no-log=true",
            "--no-ansi-color=true",
            "--disable-update-check=true",
        ]

        proxyUrl = _pickProxy(self.task.proxies)
        args.append("--use-system-proxy=false")
        if proxyUrl:
            args.append(f"--custom-proxy={proxyUrl}")

        ffmpegPath, _ = resolveFFmpegExecutables()
        if ffmpegPath:
            args.append(f"--ffmpeg-binary-path={ffmpegPath}")

        if self.task.liveRealTimeMerge:
            args.append("--live-real-time-merge=true")
            args.append(f"--live-keep-segments={_boolText(self.task.liveKeepSegments)}")
            args.append(f"--live-pipe-mux={_boolText(self.task.livePipeMux)}")
        else:
            muxOption = f"format={self.task.outputFormat}:muxer=ffmpeg"
            if ffmpegPath:
                muxOption += f":bin_path={ffmpegPath}"
            args.append(f"--mux-after-done={muxOption}")

        for name, value in self.task.headers.items():
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
        target = Path(self.stage.resolvePath)
        if target.is_file():
            return target

        outputDir = Path(self.task.path)
        if not outputDir.is_dir():
            return None

        candidates: list[Path] = []
        expectedSuffix = f".{self.task.outputExtension.lower()}"
        prefix = self.task.saveName.lower()
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

        self.task.actualExtension = candidate.suffix.lstrip(".")
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
            self.stage.setStatus(TaskStatus.FAILED)
            raise RuntimeError("未找到可用的 N_m3u8DL-RE，请先在设置中安装或配置运行时")

        Path(self.task.path).mkdir(parents=True, exist_ok=True)
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


async def parse(payload: dict) -> M3U8Task:
    url = str(payload["url"]).strip()
    headers = payload.get("headers", DEFAULT_HEADERS)
    proxies = payload.get("proxies", getProxies())
    path = Path(payload.get("path", cfg.downloadFolder.value))

    client = niquests.AsyncSession(headers=headers, timeout=30, happy_eyeballs=True)
    client.trust_env = False

    try:
        response = await client.get(
            url,
            proxies=proxies,
            verify=cfg.SSLVerify.value,
            allow_redirects=True,
        )
        try:
            response.raise_for_status()
            body = response.text
            loweredHeaders = {key.lower(): value for key, value in response.headers.items()}
            manifestType = _deriveManifestType(str(response.url), loweredHeaders, body)
            isLive = _detectLive(manifestType, body)
            title = _deriveDefaultTitle(
                str(response.url),
                loweredHeaders,
                "ts" if m3u8Config.liveRealTimeMerge.value else m3u8Config.outputFormat.value,
            )
        finally:
            response.close()
    finally:
        await client.close()

    task = M3U8Task(
        title=title,
        url=url,
        fileSize=1,
        headers=headers.copy() if isinstance(headers, dict) else DEFAULT_HEADERS.copy(),
        proxies=proxies,
        path=path,
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
        manifestType=manifestType,
        isLive=isLive,
    )
    task.addStage(
        M3U8TaskStage(
            stageIndex=1,
            resolvePath="",
            tempDir="",
        )
    )
    task.syncStagePaths()
    return task


@dataclass(kw_only=True)
class M3U8InstallTask(Task):
    url: str
    assetName: str
    headers: dict = field(default_factory=DEFAULT_HEADERS.copy)
    proxies: dict | None = field(default_factory=getProxies)
    blockNum: int = field(default_factory=lambda: httpConfig.preBlockNum.value)
    installFolder: str
    archiveSize: int = field(default=0)
    archivePath: str = field(default="")
    executablePath: str = field(default="")

    @property
    def resolvePath(self) -> str:
        return self.executablePath or self.archivePath or _normalizePath(Path(self.installFolder) / self.title)

    def __post_init__(self):
        super().__post_init__()
        self.syncStagePaths()

    def syncStagePaths(self):
        installDir = Path(self.installFolder)
        self.path = installDir
        self.archivePath = _normalizePath(installDir / self.assetName)
        if not self.executablePath:
            self.executablePath = _normalizePath(installDir / _executableName("N_m3u8DL-RE"))

        for stage in self.stages:
            if isinstance(stage, HttpTaskStage):
                stage.resolvePath = self.archivePath
            elif isinstance(stage, ExtractStage):
                stage.archivePath = self.archivePath
                stage.installFolder = _normalizePath(installDir)

    async def run(self):
        self.stages.sort(key=lambda stage: stage.stageIndex)
        currentStage = None
        try:
            for stage in self.stages:
                if self.status != TaskStatus.RUNNING:
                    break
                if stage.status == TaskStatus.COMPLETED:
                    continue

                currentStage = stage
                if isinstance(stage, HttpTaskStage):
                    await HttpWorker(stage).run()
                    continue

                if isinstance(stage, ExtractStage):
                    await ExtractWorker(stage).run()
                    self.executablePath = stage.extractedExecutables[_executableName("N_m3u8DL-RE")]
                    continue

                raise TypeError(f"不支持的 M3U8InstallTaskStage: {type(stage).__name__}")
        except asyncio.CancelledError:
            logger.info(f"{self.title} 停止安装")
            raise
        except Exception as e:
            if currentStage is not None and not currentStage.error:
                currentStage.setError(e)
            logger.opt(exception=e).error("{} 安装失败", self.title)
            raise

    def __hash__(self):
        return hash(self.taskId)


async def createInstallTask() -> M3U8InstallTask:
    assetInfo = await _requestReleaseAsset()
    _, archLabel = _detectRuntimeTarget()
    installFolder = m3u8Config.installFolder.value
    downloadTask = await coreService._parseUrl(
        {
            "url": assetInfo["url"],
            "headers": DEFAULT_HEADERS.copy(),
            "proxies": getProxies(),
            "path": Path(installFolder),
        }
    )

    if not downloadTask.stages:
        raise RuntimeError("解析 N_m3u8DL-RE 安装包链接后未获取到下载阶段")

    downloadStage = downloadTask.stages[0]
    if not isinstance(downloadStage, HttpTaskStage):
        raise TypeError(f"解析出的下载阶段类型无效: {type(downloadStage).__name__}")

    archiveSize = downloadTask.fileSize if downloadTask.fileSize > 0 else assetInfo["size"]
    assetName = downloadTask.title or str(assetInfo["name"])

    task = M3U8InstallTask(
        title=f"N_m3u8DL-RE 安装 ({archLabel})",
        url=downloadTask.url,
        assetName=assetName,
        fileSize=archiveSize,
        headers=downloadTask.headers.copy(),
        proxies=downloadTask.proxies,
        blockNum=downloadTask.blockNum,
        installFolder=installFolder,
        archiveSize=archiveSize,
    )

    downloadStage.stageIndex = 1
    task.addStage(downloadStage)
    task.addStage(
        ExtractStage(
            stageIndex=2,
            archivePath="",
            installFolder="",
            executableNames=[_executableName("N_m3u8DL-RE")],
        )
    )
    task.syncStagePaths()
    setattr(task, "_featurePackName", "m3u8_pack")
    return task
