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
from app.supports.utils import getProxies, toBytes, toExecutable, toPosixPath, toSafeFilename
from .config import m3u8Config, downloaderPath

if TYPE_CHECKING:
    from features.ffmpeg_pack.config import ffmpegPaths
    from features.http_pack.task import HttpTaskStage
    from features.extract_pack.task import ExtractStage
else:
    from extract_pack.task import ExtractStage
    from ffmpeg_pack.config import ffmpegPaths
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


def _stem(name: str) -> str:
    suffix = Path(name).suffix.lower()
    if suffix in _KNOWN_SUFFIXES:
        return name[:-len(suffix)]
    return name


def _toBool(value: bool) -> str:
    return "true" if value else "false"


def _manifestType(url: str, headers: dict[str, str], body: str) -> str:
    loweredUrl = url.lower()
    contentType = headers.get("content-type", "").lower()
    sample = body.lstrip()[:256].lower()

    if ".mpd" in loweredUrl or "dash+xml" in contentType or sample.startswith("<mpd"):
        return "mpd"
    return "m3u8"


def _isLive(manifestType: str, body: str) -> bool:
    loweredBody = body.lower()
    if manifestType == "mpd":
        return 'type="dynamic"' in loweredBody or "type='dynamic'" in loweredBody
    return "#ext-x-endlist" not in loweredBody


def _title(url: str, headers: dict[str, str], extension: str) -> str:
    candidates: list[str] = []

    cd = headers.get("content-disposition", "")
    if cd:
        msg = Message()
        msg["Content-Disposition"] = cd
        params = msg.get_params(header="Content-Disposition")
        paramDict = {key.lower(): value for key, value in params if isinstance(value, str)}
        if "filename*" in paramDict and "'" in paramDict["filename*"]:
            encoding, _, encodedText = paramDict["filename*"].split("'", 2)
            candidates.append(unquote(encodedText, encoding=encoding or "utf-8"))
        elif "filename" in paramDict:
            candidates.append(paramDict["filename"].strip("\"' "))

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


@dataclass(kw_only=True)
class M3U8TaskStage(TaskStage):
    workerType: type = field(init=False, repr=False)
    canPause: bool = field(init=False, default=False)

    outputFile: str = ""
    tempDir: str = ""
    lastMessage: str = ""

    def updateOutputFile(self, taskPath: Path, taskTitle: str):
        self.outputFile = toPosixPath(taskPath / taskTitle)
        self.tempDir = toPosixPath(taskPath / ".gd3_m3u8" / self.task.taskId)


class M3U8Worker(Worker):
    def __init__(self, stage: M3U8TaskStage):
        super().__init__(stage)
        self.stage = stage
        self.task = stage.task

    def _buildArgs(self, downloaderPath: str) -> list[str]:
        meta = self.task.metadata
        saveName = meta.get("saveName", _stem(self.task.title))

        args = [
            self.task.url,
            f"--save-dir={self.task.path}",
            f"--save-name={saveName}",
            f"--tmp-dir={self.stage.tempDir}",
            f"--thread-count={meta.get('threadCount', 16)}",
            f"--download-retry-count={meta.get('retryCount', 3)}",
            f"--http-request-timeout={meta.get('requestTimeout', 10)}",
            f"--auto-select={_toBool(meta.get('autoSelect', True))}",
            f"--concurrent-download={_toBool(meta.get('concurrentDownload', True))}",
            f"--append-url-params={_toBool(meta.get('appendUrlParams', False))}",
            f"--binary-merge={_toBool(meta.get('binaryMerge', False))}",
            f"--check-segments-count={_toBool(meta.get('checkSegmentsCount', True))}",
            "--del-after-done=true",
            "--write-meta-json=false",
            "--no-log=true",
            "--no-ansi-color=true",
            "--disable-update-check=true",
        ]

        proxies = meta.get("proxies")
        proxyUrl = ""
        if isinstance(proxies, dict):
            proxyUrl = next((v for v in proxies.values() if v), "")
        args.append("--use-system-proxy=false")
        if proxyUrl:
            args.append(f"--custom-proxy={proxyUrl}")

        ffmpegPath, _ = ffmpegPaths()
        if ffmpegPath:
            args.append(f"--ffmpeg-binary-path={ffmpegPath}")

        if meta.get("liveRealTimeMerge"):
            args.append("--live-real-time-merge=true")
            args.append(f"--live-keep-segments={_toBool(meta.get('liveKeepSegments', False))}")
            args.append(f"--live-pipe-mux={_toBool(meta.get('livePipeMux', False))}")
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

    def _parseOutputLine(self, line: str):
        text = line.strip()
        if not text:
            return

        self.stage.lastMessage = text[:1000]

        vodMatch = _VOD_PROGRESS_PATTERN.search(text)
        if vodMatch:
            self.stage.progress = float(vodMatch.group(3))
            self.stage.receivedBytes = toBytes(vodMatch.group(4), vodMatch.group(5))
            self.stage.speed = toBytes(vodMatch.group(8), vodMatch.group(9))
            totalSize = toBytes(vodMatch.group(6), vodMatch.group(7))
            if totalSize > 0:
                self.task.fileSize = totalSize
            return

        liveMatch = _LIVE_PROGRESS_PATTERN.search(text)
        if liveMatch:
            self.stage.progress = float(liveMatch.group(4))
            self.stage.speed = 0 if liveMatch.group(5) == "-" else toBytes(liveMatch.group(6), liveMatch.group(7))

    async def supervisor(self, stream: asyncio.StreamReader | None):
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
                self._parseOutputLine(line)

        if buffer.strip():
            self._parseOutputLine(buffer)

    def _updateOutput(self):
        target = Path(self.stage.outputFile)
        if target.is_file():
            self.task.metadata["actualExtension"] = target.suffix.lstrip(".")
            self.task.fileSize = max(self.task.fileSize, target.stat().st_size)
            return

        outputDir = self.task.path
        if not outputDir.is_dir():
            return

        meta = self.task.metadata
        saveName = meta.get("saveName", _stem(self.task.title))
        outputExtension = meta.get("actualExtension") or (
            "ts" if meta.get("liveRealTimeMerge") else meta.get("outputFormat", "mp4")
        )

        prefix = saveName.lower()
        ignoredSuffixes = {".json", ".txt", ".log", ".tmp", ".ghd"}
        candidates: list[Path] = []

        for candidate in outputDir.iterdir():
            if not candidate.is_file():
                continue
            if candidate.suffix.lower() in ignoredSuffixes:
                continue
            if not candidate.name.lower().startswith(prefix):
                continue
            candidates.append(candidate)

        if not candidates:
            return

        expectedSuffix = f".{outputExtension}"
        candidates.sort(
            key=lambda path: (
                path.suffix.lower() != expectedSuffix,
                -path.stat().st_mtime,
            )
        )
        found = candidates[0]
        self.task.metadata["actualExtension"] = found.suffix.lstrip(".")
        self.task.fileSize = max(self.task.fileSize, found.stat().st_size)
        if found.name != self.task.title:
            self.task.setTitle(found.name)

    async def run(self):
        execPath = downloaderPath()
        if not execPath:
            raise RuntimeError("未找到可用的 N_m3u8DL-RE，请先在设置中安装或配置运行时")

        self.task.path.mkdir(parents=True, exist_ok=True)
        Path(self.stage.tempDir).mkdir(parents=True, exist_ok=True)

        process = None
        supervisorTask = None
        try:
            args = self._buildArgs(execPath)
            process = await asyncio.create_subprocess_exec(
                execPath,
                *args,
                cwd=str(Path(execPath).parent),
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            supervisorTask = asyncio.create_task(self.supervisor(process.stdout))

            await process.wait()
            if supervisorTask is not None:
                await supervisorTask

            if process.returncode != 0:
                message = self.stage.lastMessage or f"N_m3u8DL-RE 退出码异常: {process.returncode}"
                raise RuntimeError(message)

            self._updateOutput()
            self.stage.setStatus(TaskStatus.COMPLETED)
        except asyncio.CancelledError:
            self.stage.setStatus(TaskStatus.PAUSED)
            if process is not None and process.returncode is None:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=3)
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()
            if supervisorTask is not None and not supervisorTask.done():
                supervisorTask.cancel()
                with suppress(asyncio.CancelledError):
                    await supervisorTask
            raise
        except Exception as e:
            self.stage.setError(e)
            raise


M3U8TaskStage.workerType = M3U8Worker


async def createInstallTask() -> Task:
    from app.services.feature_service import featureService

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

    asset = None
    for item in assets:
        if target in str(item.get("name") or ""):
            asset = item
            break
    if asset is None:
        raise RuntimeError(f"未找到适用于当前平台的 N_m3u8DL-RE 安装包: {target}")

    downloadUrl = str(asset.get("browser_download_url") or "").strip()
    assetName = str(asset.get("name") or "").strip()
    size = int(asset.get("size") or 0)
    if not downloadUrl or not assetName or size <= 0:
        raise RuntimeError("GitHub Release 返回了不完整的安装包信息")

    installFolder = m3u8Config.installFolder.value
    downloadPayload = {
        "url": downloadUrl,
        "headers": DEFAULT_HEADERS.copy(),
        "proxies": getProxies(),
        "path": Path(installFolder),
    }
    downloadTask = await featureService.parse(downloadPayload)

    if not downloadTask.stages:
        raise RuntimeError("解析 N_m3u8DL-RE 安装包链接后未获取到下载阶段")

    downloadStage: HttpTaskStage = downloadTask.stages[0]
    archiveSize = downloadTask.fileSize if downloadTask.fileSize > 0 else size
    archivePath = toPosixPath(Path(installFolder) / (downloadTask.title or assetName))

    downloadStage.stageIndex = 1
    downloadStage.outputFile = archivePath

    task = Task(
        title=f"N_m3u8DL-RE 安装 ({archLabel})",
        url=downloadUrl,
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
        installFolder=toPosixPath(Path(installFolder)),
        executableNames=[toExecutable("N_m3u8DL-RE")],
    ))
    return task
