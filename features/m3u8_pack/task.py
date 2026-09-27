from __future__ import annotations

import asyncio
import os
import re
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path

from loguru import logger

from app.config.cfg import cfg
from app.format import toBytes
from app.models.task import Task, TaskError, TaskStep, TaskStatus
from app.platform.filesystem import toPosixPath
from .config import m3u8Runtime

VOD_PROGRESS_PATTERN = re.compile(
    r"(\d+)/(\d+)\s+(\d+\.\d+)%\s+"
    r"(?:(?:(\d+\.\d+)(KB|MB|GB|B)/(\d+\.\d+)(KB|MB|GB|B))|-)?\s*"
    r"(\d+\.\d+)(GBps|MBps|KBps|Bps)"
)
_DURATION = r"(?:\d{2}h)?\d{2}m\d{2}s"
_SPEED = r"(\d+\.\d+)(GBps|MBps|KBps|Bps)"
LIVE_PROGRESS_PATTERN = re.compile(
    rf"({_DURATION})/({_DURATION})\s+\d+/\d+\s+(Recording|Waiting)\s+(\d+)%\s+(-|{_SPEED})"
)
LIVE_RECORD_PATTERN = re.compile(
    rf"({_DURATION})/({_DURATION})\s+\d+\.\d+(?:KB|MB|GB|B)\s+\d+/\d+\s+(Recording|Waiting)\s+(-|{_SPEED})"
)
IGNORED_OUTPUT_SUFFIXES = {".json", ".txt", ".log", ".tmp", ".ghd"}
DECRYPTION_ENGINES = {
    "FFmpeg": "FFMPEG",
    "MP4Decrypt": "MP4DECRYPT",
    "Shaka Packager": "SHAKA_PACKAGER",
}

ERROR_HINTS = (
    ("response status code does not indicate success: 403",
     "服务器拒绝了请求（403），链接可能已失效（{detail}）"),
    ("response status code does not indicate success: 404",
     "资源不存在（404），链接可能已失效（{detail}）"),
    ("response status code does not indicate success:",
     "服务器返回了错误（{detail}）"),
    ("notsupportedexception",
     "获取到的内容不是有效的播放列表，链接可能已失效（{detail}）"),
    ("filenotfoundexception",
     "缺少依赖程序（{detail}）"),
    ("no such host is known",
     "无法解析域名，请检查网络连接（{detail}）"),
    ("connection refused",
     "连接被拒绝，请检查网络连接（{detail}）"),
    ("the request was canceled due to the configured httpclient.timeout",
     "连接超时，请检查网络连接（{detail}）"),
    ("the ssl connection could not be established",
     "SSL 连接失败，请检查网络连接（{detail}）"),
)

LOG_LINE_PATTERN = re.compile(
    r"\d{2}:\d{2}:\d{2}\.\d{3}\s+(WARN|ERROR)\s*:\s*(.*)"
)
UNHANDLED_PATTERN = re.compile(
    r"Unhandled exception:\s*\S+:\s*(.*)"
)


def parseError(output: str, returncode: int) -> TaskError:
    lowered = output.lower()
    for needle, message in ERROR_HINTS:
        if needle in lowered:
            detail = parseDiagnostic(output)
            return TaskError(message, detail=detail)

    detail = parseDiagnostic(output)
    return TaskError(
        "进程异常退出（{code}）：{detail}",
        code=returncode,
        detail=detail or "N_m3u8DL-RE",
    )


def parseDiagnostic(output: str) -> str:
    last = ""
    for m in LOG_LINE_PATTERN.finditer(output):
        last = m.group(2).strip()
    cut = last.find("Unhandled exception:")
    if cut > 0:
        last = last[:cut].strip()
    if last:
        return last
    m = UNHANDLED_PATTERN.search(output)
    return m.group(1).strip() if m else ""


@dataclass(kw_only=True, eq=False)
class M3U8Task(Task):
    packId: str = "m3u8"
    canEdit = True
    manifestType: str = "m3u8"
    isLive: bool = False
    streams: list[dict] = field(default_factory=list)

    def __post_init__(self):
        super().__post_init__()
        # 直播流不存在断点：PAUSED/RUNNING 只可能是退出竞争或崩溃残留，
        # 录制在进程结束的一刻就已终结，加载时校正为已完成
        if self.isLive and self.status in {TaskStatus.PAUSED, TaskStatus.RUNNING}:
            for step in self.steps:
                if isinstance(step, M3U8TaskStep) and step.status != TaskStatus.COMPLETED:
                    step._findOutputFile()
                    step.status = TaskStatus.COMPLETED
                    step.progress = 100
                    step.speed = 0
                    step.error = None
            self.updateStatus()


@dataclass(kw_only=True)
class M3U8TaskStep(TaskStep):
    headers: dict[str, str] = field(default_factory=dict)
    threadCount: int = 8
    retryCount: int = 3
    requestTimeout: int = 100
    shouldAutoSelect: bool = True
    shouldConcurrentDownload: bool = True
    shouldAppendUrlParams: bool = False
    shouldBinaryMerge: bool = False
    shouldCheckSegmentsCount: bool = True
    shouldDeleteTemp: bool = True
    outputFormat: str = "mp4"
    customMuxAfterDone: str = ""
    subtitleFormat: str = "SRT"
    selectVideo: str = ""
    shouldSelectAllAudioSubtitle: bool = True
    maxSpeed: int = -1
    speedUnit: str = "Mbps"
    adKeyword: str = ""
    shouldOmitDateInfo: bool = False
    shouldKeepImageSegments: bool = False
    decryptionEngine: str = "FFmpeg"
    decryptionBinaryPath: str = ""
    shouldUseMp4RealTimeDecryption: bool = True
    decryptionKeys: list[str] = field(default_factory=list)
    decryptionKeyFile: str = ""
    muxImports: list[str] = field(default_factory=list)
    shouldKeepLiveSegments: bool = False
    shouldUseLivePipeMux: bool = False
    shouldFixLiveVtt: bool = False
    liveWaitTime: int = 0
    liveTakeCount: int = 0
    recordLimit: str = ""
    lastMessage: str = ""
    liveStatus: str = ""
    liveElapsed: str = ""
    liveTotal: str = ""

    @property
    def canPause(self) -> bool:
        return not self.task.isLive

    @property
    def outputPath(self) -> str:
        return toPosixPath(self.task.outputFolder / self.task.name)

    @property
    def _tempFolder(self) -> str:
        return toPosixPath(self.task.partPath / "tmp")

    @property
    def _saveName(self) -> str:
        return Path(self.task.name).stem

    def setOptions(self, options: dict) -> None:
        if "headers" in options:
            self.headers = options["headers"]
        if "selectVideo" in options:
            self.selectVideo = options["selectVideo"]
        if "recordLimit" in options:
            self.recordLimit = options["recordLimit"]
        if "decryptionKeys" in options:
            self.decryptionKeys = options["decryptionKeys"]
        if "decryptionKeyFile" in options:
            self.decryptionKeyFile = options["decryptionKeyFile"]
        if "muxImports" in options:
            self.muxImports = options["muxImports"]

    def terminate(self) -> None:
        self._stopping = True
        if self._process is not None and self._process.returncode is None:
            self._process.terminate()

    def _buildCommand(self) -> list[str]:
        def toBool(v: bool) -> str:
            return "true" if v else "false"

        args = [
            self.task.url,
            f"--save-dir={toPosixPath(self.task.partPath)}",
            f"--save-name={self._saveName}",
            f"--tmp-dir={self._tempFolder}",
            f"--thread-count={self.threadCount}",
            f"--download-retry-count={self.retryCount}",
            f"--http-request-timeout={self.requestTimeout}",
            f"--concurrent-download={toBool(self.shouldConcurrentDownload)}",
            f"--append-url-params={toBool(self.shouldAppendUrlParams)}",
            f"--binary-merge={toBool(self.shouldBinaryMerge)}",
            f"--check-segments-count={toBool(self.shouldCheckSegmentsCount)}",
            f"--del-after-done={toBool(self.shouldDeleteTemp)}",
            f"--sub-format={self.subtitleFormat}",
            "--write-meta-json=false",
            "--no-log=true",
            "--no-ansi-color=true",
            "--disable-update-check=true",
        ]

        if self.shouldSelectAllAudioSubtitle:
            args.append(f"--select-video={self.selectVideo or 'best'}")
            args.append("--select-audio=all")
            args.append("--select-subtitle=all")
        elif self.selectVideo:
            args.append(f"--select-video={self.selectVideo}")
            args.append(f"--auto-select={toBool(self.shouldAutoSelect)}")
        else:
            args.append(f"--auto-select={toBool(self.shouldAutoSelect)}")

        if self.maxSpeed > 0:
            args.append(f"--max-speed={self.maxSpeed}{self.speedUnit}")
        elif cfg.isSpeedLimitEnabled.value:
            args.append(f"--max-speed={int(cfg.speedLimitation.value)}Bps")
        if self.adKeyword:
            args.append(f"--ad-keyword={self.adKeyword}")
        if self.shouldOmitDateInfo:
            args.append("--no-date-info=true")

        from app.config.cfg import proxy
        proxyUrl = proxy()
        if proxyUrl and proxyUrl.startswith("socks5h://"):
            proxyUrl = "socks5://" + proxyUrl[len("socks5h://"):]
        args.append("--use-system-proxy=false")
        if proxyUrl:
            args.append(f"--custom-proxy={proxyUrl}")

        from ffmpeg_pack.config import ffmpegRuntime
        ffmpegPath = ffmpegRuntime.path()
        if ffmpegPath:
            args.append(f"--ffmpeg-binary-path={ffmpegPath}")

        args.append(f"--decryption-engine={DECRYPTION_ENGINES.get(self.decryptionEngine, 'FFMPEG')}")
        args.append(f"--mp4-real-time-decryption={toBool(self.shouldUseMp4RealTimeDecryption)}")
        if self.decryptionBinaryPath:
            args.append(f"--decryption-binary-path={toPosixPath(Path(self.decryptionBinaryPath))}")
        for key in self.decryptionKeys:
            text = key.strip()
            if text:
                args.append(f"--key={text}")
        if self.decryptionKeyFile:
            args.append(f"--key-text-file={toPosixPath(Path(self.decryptionKeyFile))}")

        if self.task.isLive:
            args.append("--live-real-time-merge=true")
            args.append(f"--live-keep-segments={toBool(self.shouldKeepLiveSegments)}")
            args.append(f"--live-pipe-mux={toBool(self.shouldUseLivePipeMux)}")
            if self.shouldFixLiveVtt:
                args.append("--live-fix-vtt-by-audio=true")
            if self.liveWaitTime > 0:
                args.append(f"--live-wait-time={self.liveWaitTime}")
            if self.liveTakeCount > 0:
                args.append(f"--live-take-count={self.liveTakeCount}")
            if self.recordLimit:
                args.append(f"--live-record-limit={self.recordLimit}")
        elif self.customMuxAfterDone:
            args.append(f"--mux-after-done={self.customMuxAfterDone}")
        else:
            muxOption = f"format={self.outputFormat}:muxer=ffmpeg"
            if ffmpegPath:
                muxOption += f":bin_path={ffmpegPath}"
            args.append(f"--mux-after-done={muxOption}")

        for imp in self.muxImports:
            text = imp.strip()
            if text:
                args.append(f"--mux-import={text}")

        for name, value in self.headers.items():
            text = value.strip()
            if text:
                args.extend(["-H", f"{name}: {text}"])

        return args

    def _parseOutputLine(self, line: str):
        text = line.strip()
        if not text:
            return

        self.lastMessage = text[-1000:]

        vodMatch = None
        for m in VOD_PROGRESS_PATTERN.finditer(text):
            vodMatch = m
        if vodMatch:
            self.progress = float(vodMatch.group(3))
            if vodMatch.group(4):
                self.receivedBytes = toBytes(vodMatch.group(4), vodMatch.group(5))
                totalSize = toBytes(vodMatch.group(6), vodMatch.group(7))
                if totalSize > 0:
                    self.task.fileSize = totalSize
            self.speed = toBytes(vodMatch.group(8), vodMatch.group(9))
            return

        liveMatch = None
        for m in LIVE_PROGRESS_PATTERN.finditer(text):
            liveMatch = m
        if liveMatch:
            self.liveElapsed = liveMatch.group(1)
            self.liveTotal = liveMatch.group(2)
            self.liveStatus = liveMatch.group(3)
            self.progress = float(liveMatch.group(4))
            self.speed = 0 if liveMatch.group(5) == "-" else toBytes(liveMatch.group(6), liveMatch.group(7))
            return

        recordMatch = None
        for m in LIVE_RECORD_PATTERN.finditer(text):
            recordMatch = m
        if recordMatch:
            self.liveElapsed = recordMatch.group(1)
            self.liveTotal = recordMatch.group(2)
            self.liveStatus = recordMatch.group(3)
            self.speed = 0 if recordMatch.group(4) == "-" else toBytes(recordMatch.group(5), recordMatch.group(6))

    async def _readOutput(self, stream: asyncio.StreamReader):
        rawChunks = []
        buffer = ""
        while True:
            chunk = await stream.read(4096)
            if not chunk:
                break
            raw = chunk.decode("utf-8", errors="ignore")
            rawChunks.append(raw)
            buffer += raw
            buffer = buffer.replace("\r\n", "\n").replace("\r", "\n")
            lines = buffer.split("\n")
            buffer = lines.pop()
            for line in lines:
                self._parseOutputLine(line)
            # NonAnsiWriter 可能剥掉换行符，进度更新堆积在 buffer 里
            self._parseOutputLine(buffer)
            if len(buffer) > 8192:
                buffer = buffer[-4096:]
        if buffer.strip():
            self._parseOutputLine(buffer)
        self._processOutput = "".join(rawChunks)

    def _findOutputFile(self) -> bool:
        target = Path(self.outputPath)
        if target.is_file() and target.stat().st_size > 0:
            self.task.fileSize = max(self.task.fileSize, target.stat().st_size)
            return True

        prefix = f"{self._saveName.lower()}."
        found = max(
            (c for c in self.task.partPath.glob("*")
             if c.is_file() and c.suffix.lower() not in IGNORED_OUTPUT_SUFFIXES
             and c.name.lower().startswith(prefix)),
            key=lambda c: c.stat().st_mtime,
            default=None,
        )
        if found is None:
            return False
        if found.suffix.lower() != target.suffix.lower():
            raise TaskError("N_m3u8DL-RE 输出了 {actual} 文件，与任务的 {expected} 不符",
                            actual=found.suffix, expected=target.suffix)
        self.task.fileSize = max(self.task.fileSize, found.stat().st_size)
        os.replace(found, target)
        return True

    async def run(self, reportSpeed, waitForSpeedLimit) -> None:
        self._stopping = False
        self._process = None

        execPath = m3u8Runtime.path()
        if not execPath:
            raise TaskError("{name} 未安装，请在设置中安装", name="N_m3u8DL-RE")

        Path(self._tempFolder).mkdir(parents=True, exist_ok=True)

        env = None
        if self.shouldKeepImageSegments:
            env = {**os.environ, "RE_KEEP_IMAGE_SEGMENTS": "1"}

        outputTask = None
        try:
            command = self._buildCommand()
            self._process = await asyncio.create_subprocess_exec(
                execPath, *command,
                cwd=Path(execPath).parent,
                env=env,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            outputTask = asyncio.create_task(self._readOutput(self._process.stdout))

            await self._process.wait()
            await outputTask

            if self._process.returncode != 0 and not self._stopping:
                output = getattr(self, "_processOutput", "")
                if output:
                    logger.warning("N_m3u8DL-RE output:\n{}", output[-8192:])
                raise parseError(output, self._process.returncode)

            if not self._findOutputFile():
                raise TaskError(
                    "未找到输出文件：{detail}",
                    detail=self.lastMessage[-200:] if self.lastMessage else "",
                )
        except asyncio.CancelledError:
            if self._process is not None and self._process.returncode is None:
                self._process.terminate()
                try:
                    await asyncio.wait_for(self._process.wait(), timeout=3)
                except asyncio.TimeoutError:
                    self._process.kill()
                    await self._process.wait()
            if outputTask is not None and not outputTask.done():
                outputTask.cancel()
                with suppress(asyncio.CancelledError):
                    await outputTask
            if self.task.isLive:
                self._findOutputFile()
                self.setStatus(TaskStatus.COMPLETED)
            else:
                self.setStatus(TaskStatus.PAUSED)
            raise
