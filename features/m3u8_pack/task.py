import asyncio
import re
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar, TYPE_CHECKING

from typing import Literal

from app.bases.interfaces import Worker
from app.bases.models import Task, TaskStage, TaskStatus
from app.supports.utils import removePath, toBytes, toPosixPath
from .config import downloaderPath

if TYPE_CHECKING:
    from app.view.components.cards import ParseSettingCard
    from features.ffmpeg_pack.config import ffmpegPaths
else:
    from ffmpeg_pack.config import ffmpegPaths


_VOD_PROGRESS_PATTERN = re.compile(
    r"(\d+)/(\d+)\s+(\d+\.\d+)%\s+(\d+\.\d+)(KB|MB|GB|B)/(\d+\.\d+)(KB|MB|GB|B)\s+(\d+\.\d+)(GBps|MBps|KBps|Bps)\s+(.+)"
)
_LIVE_PROGRESS_PATTERN = re.compile(
    r"(\d{2}m\d{2}s)/(\d{2}m\d{2}s)\s+\d+/\d+\s+(Recording|Waiting)\s+(\d+)%\s+(-|(\d+\.\d+)(GBps|MBps|KBps|Bps))"
)
_IGNORED_OUTPUT_SUFFIXES = {".json", ".txt", ".log", ".tmp", ".ghd"}


def _toBool(value: bool) -> str:
    return "true" if value else "false"


@dataclass(kw_only=True)
class M3U8TaskStage(TaskStage):
    workerType: type = field(init=False, repr=False)
    canPause: bool = field(init=False, default=True)

    actualExtension: str = ""
    lastMessage: str = ""

    headers: dict[str, str] = field(default_factory=dict)
    proxies: dict[str, str] = field(default_factory=dict)

    threadCount: int = 16
    retryCount: int = 3
    requestTimeout: int = 10
    autoSelect: bool = True
    concurrentDownload: bool = True
    appendUrlParams: bool = False
    binaryMerge: bool = False
    checkSegmentsCount: bool = True

    outputFormat: str = "mp4"
    liveRealTimeMerge: bool = False
    liveKeepSegments: bool = False
    livePipeMux: bool = False

    @property
    def outputFile(self) -> str:
        return toPosixPath(Path(self.task.path) / self.task.title)

    @property
    def tempDir(self) -> str:
        return toPosixPath(Path(self.task.path) / ".gd3_m3u8" / self.task.taskId)

    @property
    def saveName(self) -> str:
        return Path(self.task.title).stem

    def cleanup(self):
        removePath(Path(self.tempDir))


@dataclass(kw_only=True, eq=False)
class M3U8Task(Task):
    packId: str = "m3u8"
    supportsEdit: ClassVar[bool] = True

    manifestType: Literal["m3u8", "mpd"] = "m3u8"
    isLive: bool = False

    @property
    def stage(self) -> "M3U8TaskStage":
        return self.stages[0]

    @property
    def headers(self) -> dict:
        return self.stage.headers

    @property
    def proxies(self) -> dict | None:
        return self.stage.proxies

    def editorCards(self, parent) -> list["ParseSettingCard"]:
        from app.view.components.add_task_dialog import SelectFolderCard
        from app.view.components.edit_task_cards import HeadersEditCard, ProxiesEditCard
        from qfluentwidgets import FluentIcon

        return [
            HeadersEditCard(FluentIcon.GLOBE, parent.tr("请求标头"), parent, initial=self.headers),
            ProxiesEditCard(FluentIcon.CERTIFICATE, parent.tr("代理服务器"), parent, initial=self.proxies),
            SelectFolderCard(FluentIcon.DOWNLOAD, parent.tr("下载到"), parent, initial=self.path),
        ]

    def applySettings(self, payload):
        super().applySettings(payload)
        if "headers" in payload:
            self.stage.headers = payload["headers"]
        if "proxies" in payload:
            self.stage.proxies = payload["proxies"]

    def cleanup(self):
        super().cleanup()
        # N_m3u8DL-RE 在 task.path 留下同前缀的中间产物（.m3u8、.ts、log 等），
        # 用前缀匹配兜底删除；输出文件本身在 super().cleanup() 里已经处理。
        outputDirectory = Path(self.path)
        if not outputDirectory.exists():
            return
        prefix = f"{self.title}."
        outputName = Path(self.outputFolder).name
        for candidate in outputDirectory.iterdir():
            if candidate.name == outputName:
                continue
            if candidate.is_file() and candidate.name.startswith(prefix):
                candidate.unlink(missing_ok=True)


class M3U8Worker(Worker):
    def __init__(self, stage: M3U8TaskStage):
        super().__init__(stage)
        self.stage = stage

    def _buildArgs(self) -> list[str]:
        stage = self.stage
        args = [
            stage.task.url,
            f"--save-dir={toPosixPath(stage.task.path)}",
            f"--save-name={stage.saveName}",
            f"--tmp-dir={stage.tempDir}",
            f"--thread-count={stage.threadCount}",
            f"--download-retry-count={stage.retryCount}",
            f"--http-request-timeout={stage.requestTimeout}",
            f"--auto-select={_toBool(stage.autoSelect)}",
            f"--concurrent-download={_toBool(stage.concurrentDownload)}",
            f"--append-url-params={_toBool(stage.appendUrlParams)}",
            f"--binary-merge={_toBool(stage.binaryMerge)}",
            f"--check-segments-count={_toBool(stage.checkSegmentsCount)}",
            "--del-after-done=true",
            "--write-meta-json=false",
            "--no-log=true",
            "--no-ansi-color=true",
            "--disable-update-check=true",
        ]

        proxyUrl = next((v for v in stage.proxies.values() if v), "")
        # N_m3u8DL-RE 的 .NET HttpClient 不识别 socks5h scheme，等价转为 socks5
        if proxyUrl.startswith("socks5h://"):
            proxyUrl = "socks5://" + proxyUrl[len("socks5h://"):]
        args.append("--use-system-proxy=false")
        if proxyUrl:
            args.append(f"--custom-proxy={proxyUrl}")

        ffmpegPath, _ = ffmpegPaths()
        if ffmpegPath:
            args.append(f"--ffmpeg-binary-path={ffmpegPath}")

        if stage.liveRealTimeMerge:
            args.append("--live-real-time-merge=true")
            args.append(f"--live-keep-segments={_toBool(stage.liveKeepSegments)}")
            args.append(f"--live-pipe-mux={_toBool(stage.livePipeMux)}")
        else:
            muxOption = f"format={stage.outputFormat}:muxer=ffmpeg"
            if ffmpegPath:
                muxOption += f":bin_path={ffmpegPath}"
            args.append(f"--mux-after-done={muxOption}")

        for name, value in stage.headers.items():
            text = value.strip()
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
                self.stage.task.fileSize = totalSize
            return

        liveMatch = _LIVE_PROGRESS_PATTERN.search(text)
        if liveMatch:
            self.stage.progress = float(liveMatch.group(4))
            self.stage.speed = 0 if liveMatch.group(5) == "-" else toBytes(liveMatch.group(6), liveMatch.group(7))

    async def supervisor(self, stream: asyncio.StreamReader):
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
        if target.is_file() and target.stat().st_size > 0:
            self.stage.actualExtension = target.suffix.lstrip(".")
            self.stage.task.fileSize = max(self.stage.task.fileSize, target.stat().st_size)
            return
        target.unlink(missing_ok=True)

        outputDir = self.stage.task.path
        if not outputDir.is_dir():
            return

        fallbackExtension = "ts" if self.stage.liveRealTimeMerge else self.stage.outputFormat
        expectedSuffix = f".{self.stage.actualExtension or fallbackExtension}"
        prefix = self.stage.saveName.lower()

        candidates = [
            candidate
            for candidate in outputDir.iterdir()
            if candidate.is_file()
            and candidate.suffix.lower() not in _IGNORED_OUTPUT_SUFFIXES
            and candidate.name.lower().startswith(prefix)
        ]
        if not candidates:
            return

        candidates.sort(
            key=lambda path: (
                path.suffix.lower() != expectedSuffix,
                -path.stat().st_mtime,
            )
        )
        found = candidates[0]
        self.stage.actualExtension = found.suffix.lstrip(".")
        self.stage.task.fileSize = max(self.stage.task.fileSize, found.stat().st_size)
        if found.name != self.stage.task.title:
            self.stage.task.setTitle(found.name)

    async def run(self):
        execPath = downloaderPath()
        if not execPath:
            raise RuntimeError("未找到可用的 N_m3u8DL-RE，请先在设置中安装或配置运行时")

        self.stage.task.path.mkdir(parents=True, exist_ok=True)
        Path(self.stage.tempDir).mkdir(parents=True, exist_ok=True)
        # 占位以便后续同名任务被 deduplicateFilename 检测到——_updateOutput 会清掉这个 0 字节文件
        Path(self.stage.outputFile).touch(exist_ok=True)

        process = None
        supervisorTask = None
        try:
            args = self._buildArgs()
            process = await asyncio.create_subprocess_exec(
                execPath,
                *args,
                cwd=Path(execPath).parent,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            supervisorTask = asyncio.create_task(self.supervisor(process.stdout))

            await process.wait()
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
