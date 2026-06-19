import asyncio
import sys
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar, TYPE_CHECKING

from app.bases.interfaces import Worker
from app.bases.models import SpecialFileSize, Task, TaskStage, TaskStatus
from app.supports.utils import removePath, toPosixPath
from .config import downloaderPath

if TYPE_CHECKING:
    from features.ffmpeg_pack.config import ffmpegPaths
else:
    from ffmpeg_pack.config import ffmpegPaths


_PROGRESS_SENTINEL = "#GD3PROG#"
_FINAL_SENTINEL = "#GD3FILE#"
_PROGRESS_TEMPLATE = (
    f"download:{_PROGRESS_SENTINEL}"
    "%(progress.downloaded_bytes)s|%(progress.total_bytes)s|"
    "%(progress.total_bytes_estimate)s|%(progress.speed)s"
)
_FINAL_TEMPLATE = f"after_move:{_FINAL_SENTINEL}%(filepath)s"
_OUTPUT_TEMPLATE = "%(title)s.%(ext)s"

DEFAULT_VIDEO_FORMAT = "bv*+ba/b"


def _toInt(value: str) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


_ERROR_HINTS = (
    ("is not available in your country", "该视频在当前地区不可用，可在设置里配置代理后重试"),
    ("video unavailable", "视频不可用（可能已被删除或设为私有）"),
    ("private video", "私有视频，需要有权限账号的 cookies"),
    ("members-only", "会员专享视频，需要对应会员账号的 cookies"),
    ("confirm your age", "年龄限制视频，需要登录账号的 cookies"),
    ("confirm you're not a bot", "YouTube 要求人机验证，请在设置里配置 cookies"),
    ("requested format is not available", "请求的画质不可用，请改用其它格式"),
    ("http error 403", "下载被拒绝（403），链接可能已过期，请重试"),
)


def _toFriendlyError(message: str) -> str:
    lowered = message.lower()
    for needle, hint in _ERROR_HINTS:
        if needle in lowered:
            return hint
    return message


def _networkArgs(proxies: dict | None, headers: dict | None) -> list[str]:
    args: list[str] = []
    proxyUrl = next((v for v in (proxies or {}).values() if v), "")
    if proxyUrl:
        args.extend(["--proxy", proxyUrl])
    for name, value in (headers or {}).items():
        text = str(value).strip()
        if text:
            args.extend(["--add-header", f"{name}:{text}"])
    return args


async def probeMediaInfo(url: str, proxies: dict | None, videoFormat: str, headers: dict | None = None) -> tuple[str, int]:
    """探测真实标题与选定画质的预估总大小；受限/超时回落 ("", UNKNOWN)。"""
    execPath = downloaderPath()
    if not execPath:
        return "", SpecialFileSize.UNKNOWN

    args = [
        url, "-f", videoFormat, "--no-playlist", "--skip-download", "--no-warnings",
        "--print", "%(title)s", "--print", "%(filesize_approx)s",
        *_networkArgs(proxies, headers),
    ]
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
        with suppress(Exception):
            await process.wait()
        return "", SpecialFileSize.UNKNOWN
    except OSError:
        return "", SpecialFileSize.UNKNOWN

    if process.returncode != 0:
        return "", SpecialFileSize.UNKNOWN

    lines = stdout.decode("utf-8", errors="ignore").strip().splitlines()
    title = lines[0].strip() if lines else ""
    size = _toInt(lines[1]) if len(lines) > 1 else SpecialFileSize.UNKNOWN
    return title, size


@dataclass(kw_only=True)
class YtDlpTaskStage(TaskStage):
    workerType: type = field(init=False, repr=False)

    videoFormat: str = DEFAULT_VIDEO_FORMAT
    headers: dict[str, str] = field(default_factory=dict)
    proxies: dict[str, str] = field(default_factory=dict)
    lastMessage: str = ""

    @property
    def tempDir(self) -> str:
        return toPosixPath(Path(self.task.path) / ".gd3_ytdlp" / self.task.taskId)

    def cleanup(self):
        removePath(Path(self.tempDir))


@dataclass(kw_only=True, eq=False)
class YtDlpTask(Task):
    packId: str = "ytdlp"
    supportsEdit: ClassVar[bool] = True

    @property
    def stage(self) -> "YtDlpTaskStage":
        return self.stages[0]

    def editorCards(self, parent):
        from qfluentwidgets import FluentIcon

        from app.view.components.add_task_dialog import SelectFolderCard

        return [
            SelectFolderCard(FluentIcon.DOWNLOAD, parent.tr("下载到"), parent, initial=self.path),
        ]

    def applySettings(self, payload: dict):
        super().applySettings(payload)
        if "videoFormat" in payload:
            self.stage.videoFormat = payload["videoFormat"]


class YtDlpWorker(Worker):
    def __init__(self, stage: YtDlpTaskStage):
        super().__init__(stage)
        self.stage = stage
        self._finalPath = ""
        self._streamBytes: dict[int, int] = {}

    def _buildArgs(self) -> list[str]:
        stage = self.stage
        args = [
            stage.task.url,
            "-f", stage.videoFormat,
            "-o", _OUTPUT_TEMPLATE,
            "-P", f"home:{toPosixPath(stage.task.path)}",
            "-P", f"temp:{stage.tempDir}",
            "--no-playlist",
            "--newline",
            "--no-color",
            "--no-simulate",
            "--progress",
            "--progress-template", _PROGRESS_TEMPLATE,
            "--print", _FINAL_TEMPLATE,
            *_networkArgs(stage.proxies, stage.headers),
        ]
        ffmpegPath, _ = ffmpegPaths()
        if ffmpegPath:
            args.extend(["--ffmpeg-location", ffmpegPath])
        return args

    def _parseOutputLine(self, line: str):
        text = line.strip()
        if not text:
            return
        if text.startswith(_FINAL_SENTINEL):
            self._finalPath = text[len(_FINAL_SENTINEL):].strip()
            return
        if text.startswith(_PROGRESS_SENTINEL):
            parts = text[len(_PROGRESS_SENTINEL):].split("|")
            if len(parts) >= 4:
                downloaded = _toInt(parts[0])
                total = _toInt(parts[1]) or _toInt(parts[2])
                self.stage.speed = _toInt(parts[3])
                if total > 0:
                    self._streamBytes[total] = downloaded
                    received = sum(self._streamBytes.values())
                    self.stage.task.fileSize = max(self.stage.task.fileSize, sum(self._streamBytes.keys()))
                    self.stage.receivedBytes = received
                    if self.stage.task.fileSize > 0:
                        self.stage.progress = min(99.5, received / self.stage.task.fileSize * 100)
            return
        self.stage.lastMessage = text[:1000]

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

    def _applyFinalFile(self):
        if not self._finalPath:
            return
        path = Path(self._finalPath)
        if not path.is_file():
            return
        size = path.stat().st_size
        if size <= 0:
            return
        self.stage.task.fileSize = max(self.stage.task.fileSize, size)
        if path.name != self.stage.task.title:
            self.stage.task.setTitle(path.name)

    async def run(self):
        execPath = downloaderPath()
        if not execPath:
            raise RuntimeError("未找到可用的 yt-dlp，请先在设置中安装或配置运行时")

        self.stage.task.path.mkdir(parents=True, exist_ok=True)
        process = None
        supervisorTask = None
        try:
            process = await asyncio.create_subprocess_exec(
                execPath,
                *self._buildArgs(),
                cwd=Path(execPath).parent,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            supervisorTask = asyncio.create_task(self.supervisor(process.stdout))

            await process.wait()
            await supervisorTask

            if process.returncode != 0:
                raise RuntimeError(_toFriendlyError(self.stage.lastMessage) or f"yt-dlp 退出码异常: {process.returncode}")

            self._applyFinalFile()
            self.stage.cleanup()
            self.stage.setStatus(TaskStatus.COMPLETED)
        except asyncio.CancelledError:
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
            self.stage.setStatus(TaskStatus.PAUSED)
            raise
        except Exception as e:
            self.stage.setError(e)
            raise


@dataclass(kw_only=True)
class YtDlpInstallStage(TaskStage):
    workerType: type = field(init=False, repr=False)
    canPause: bool = field(init=False, default=False)

    binaryPath: str


class YtDlpInstallWorker(Worker):
    def __init__(self, stage: YtDlpInstallStage):
        super().__init__(stage)
        self.stage = stage

    async def run(self):
        path = Path(self.stage.binaryPath)
        try:
            if not path.is_file():
                raise FileNotFoundError(f"未找到已下载的 yt-dlp: {path}")
            if sys.platform != "win32":
                path.chmod(path.stat().st_mode | 0o755)
            self.stage.setStatus(TaskStatus.COMPLETED)
        except asyncio.CancelledError:
            self.stage.setStatus(TaskStatus.PAUSED)
            raise
        except Exception as e:
            self.stage.setError(e)
            raise


YtDlpTaskStage.workerType = YtDlpWorker
YtDlpInstallStage.workerType = YtDlpInstallWorker
