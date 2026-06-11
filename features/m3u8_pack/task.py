import asyncio
import os
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
_DECRYPTION_ENGINES = {
    "FFmpeg": "FFMPEG",
    "MP4Decrypt": "MP4DECRYPT",
    "Shaka Packager": "SHAKA_PACKAGER",
}


def _toBool(value: bool) -> str:
    return "true" if value else "false"


@dataclass(kw_only=True)
class M3U8TaskStage(TaskStage):
    workerType: type = field(init=False, repr=False)

    actualExtension: str = ""
    lastMessage: str = ""
    liveStatus: str = ""
    liveElapsed: str = ""
    liveTotal: str = ""

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
    delAfterDone: bool = True

    outputFormat: str = "mp4"
    customMuxAfterDone: str = ""
    subtitleFormat: str = "SRT"
    selectVideo: str = ""
    selectAllAudioSubtitle: bool = True
    maxSpeed: int = -1
    speedUnit: str = "Mbps"
    adKeyword: str = ""
    noDateInfo: bool = False
    keepImageSegments: bool = False

    decryptionEngine: str = "FFmpeg"
    decryptionBinaryPath: str = ""
    mp4RealTimeDecryption: bool = True
    decryptionKeys: list[str] = field(default_factory=list)
    keyTextFile: str = ""

    muxImports: list[str] = field(default_factory=list)

    # 直播（real-time-merge 对直播恒开，不设字段）
    liveKeepSegments: bool = False
    livePipeMux: bool = False
    liveFixVtt: bool = False
    liveWaitTime: int = 0
    liveTakeCount: int = 0
    recordLimit: str = ""

    @property
    def canPause(self) -> bool:
        # 直播无暂停语义——只有「停止并定案」
        return not self.task.isLive

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
    # parse() 时枚举的可选视频流 [{"label","selectExpr"}]；只服务于轨道下拉, 不持久化
    streams: list = field(default_factory=list, repr=False)

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
        from qfluentwidgets import FluentIcon

        from app.view.components.add_task_dialog import SelectFolderCard
        from app.view.components.edit_task_cards import HeadersEditCard, ProxiesEditCard
        from .cards import (
            M3U8DecryptionEditCard,
            M3U8MuxImportEditCard,
            M3U8RecordLimitEditCard,
            M3U8TrackEditCard,
        )

        cards: list["ParseSettingCard"] = [
            HeadersEditCard(FluentIcon.GLOBE, parent.tr("请求标头"), parent, initial=self.headers),
            ProxiesEditCard(FluentIcon.CERTIFICATE, parent.tr("代理服务器"), parent, initial=self.proxies),
        ]
        if len(self.streams) > 1:
            cards.append(M3U8TrackEditCard(
                FluentIcon.VIDEO, parent.tr("视频轨道"), parent,
                streams=self.streams, initial=self.stage.selectVideo,
            ))
        if self.isLive:
            cards.append(M3U8RecordLimitEditCard(
                FluentIcon.STOP_WATCH, parent.tr("录制时长上限"), parent,
                initial=self.stage.recordLimit,
            ))
        cards += [
            M3U8DecryptionEditCard(
                FluentIcon.VPN, parent.tr("解密密钥"), parent,
                keys=self.stage.decryptionKeys, keyTextFile=self.stage.keyTextFile,
            ),
            M3U8MuxImportEditCard(
                FluentIcon.MUSIC, parent.tr("导入音轨/字幕"), parent,
                initial=self.stage.muxImports,
            ),
            SelectFolderCard(FluentIcon.DOWNLOAD, parent.tr("下载到"), parent, initial=self.path),
        ]
        return cards

    def editorSchema(self) -> list[dict]:
        # 数据驱动编辑卡 schema（对齐 editorCards 的字段）：标头/代理/轨道/录制时长/解密/导入/目录。
        # 应用走 applySettings 就地改 stage（免重解析，躲开重新枚举流）；combo 选项来自 parse 时枚举的 streams。
        schema = [
            {"kind": "headers", "label": "请求标头", "field": "headers", "value": dict(self.headers)},
            {"kind": "proxies", "label": "代理服务器", "field": "proxies",
             "value": (next(iter(self.proxies.values())) if self.proxies else "")},
        ]
        if len(self.streams) > 1:
            schema.append({
                "kind": "combo", "label": "视频轨道", "field": "selectVideo",
                "value": self.stage.selectVideo,
                "options": [{"label": "自动 (最佳)", "value": ""}]
                + [{"label": s["label"], "value": s["selectExpr"]} for s in self.streams],
            })
        if self.isLive:
            schema.append({
                "kind": "lineedit", "label": "录制时长上限", "field": "recordLimit",
                "value": self.stage.recordLimit, "placeholder": "如 00:30:00，留空不限",
            })
        schema += [
            {"kind": "lines", "label": "解密密钥", "field": "decryptionKeys",
             "value": list(self.stage.decryptionKeys), "placeholder": "每行一个 KID:KEY"},
            {"kind": "file", "label": "密钥文件", "field": "keyTextFile", "value": self.stage.keyTextFile},
            {"kind": "lines", "label": "导入音轨/字幕", "field": "muxImports",
             "value": list(self.stage.muxImports), "placeholder": "每行一个 path,name=...,lang=..."},
            {"kind": "folder", "label": "下载到", "field": "path", "value": str(self.path)},
        ]
        return schema

    def applySettings(self, payload):
        super().applySettings(payload)
        if "headers" in payload:
            self.stage.headers = payload["headers"]
        if "proxies" in payload:
            self.stage.proxies = payload["proxies"]
        if "selectVideo" in payload:
            self.stage.selectVideo = payload["selectVideo"]
        if "recordLimit" in payload:
            self.stage.recordLimit = payload["recordLimit"]
        if "decryptionKeys" in payload:
            self.stage.decryptionKeys = payload["decryptionKeys"]
        if "keyTextFile" in payload:
            self.stage.keyTextFile = payload["keyTextFile"]
        if "muxImports" in payload:
            self.stage.muxImports = payload["muxImports"]

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
            f"--concurrent-download={_toBool(stage.concurrentDownload)}",
            f"--append-url-params={_toBool(stage.appendUrlParams)}",
            f"--binary-merge={_toBool(stage.binaryMerge)}",
            f"--check-segments-count={_toBool(stage.checkSegmentsCount)}",
            f"--del-after-done={_toBool(stage.delAfterDone)}",
            f"--sub-format={stage.subtitleFormat}",
            "--write-meta-json=false",
            "--no-log=true",
            "--no-ansi-color=true",
            "--disable-update-check=true",
        ]

        # 拿全部音轨/字幕时需绕开 auto-select 对其的"仅最佳"——显式选视频(最佳或所选)+全部音字幕
        if stage.selectAllAudioSubtitle:
            args.append(f"--select-video={stage.selectVideo or 'best'}")
            args.append("--select-audio=all")
            args.append("--select-subtitle=all")
        elif stage.selectVideo:
            args.append(f"--select-video={stage.selectVideo}")
            args.append(f"--auto-select={_toBool(stage.autoSelect)}")
        else:
            args.append(f"--auto-select={_toBool(stage.autoSelect)}")

        if stage.maxSpeed > 0:
            args.append(f"--max-speed={stage.maxSpeed}{stage.speedUnit}")
        if stage.adKeyword:
            args.append(f"--ad-keyword={stage.adKeyword}")
        if stage.noDateInfo:
            args.append("--no-date-info=true")

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

        args.append(f"--decryption-engine={_DECRYPTION_ENGINES.get(stage.decryptionEngine, 'FFMPEG')}")
        args.append(f"--mp4-real-time-decryption={_toBool(stage.mp4RealTimeDecryption)}")
        if stage.decryptionBinaryPath:
            args.append(f"--decryption-binary-path={toPosixPath(Path(stage.decryptionBinaryPath))}")
        for key in stage.decryptionKeys:
            text = key.strip()
            if text:
                args.append(f"--key={text}")
        if stage.keyTextFile:
            args.append(f"--key-text-file={toPosixPath(Path(stage.keyTextFile))}")

        if stage.task.isLive:
            # 直播恒开 real-time-merge：硬杀停止时文件已落盘可用
            args.append("--live-real-time-merge=true")
            args.append(f"--live-keep-segments={_toBool(stage.liveKeepSegments)}")
            args.append(f"--live-pipe-mux={_toBool(stage.livePipeMux)}")
            if stage.liveFixVtt:
                args.append("--live-fix-vtt-by-audio=true")
            if stage.liveWaitTime > 0:
                args.append(f"--live-wait-time={stage.liveWaitTime}")
            if stage.liveTakeCount > 0:
                args.append(f"--live-take-count={stage.liveTakeCount}")
            if stage.recordLimit:
                args.append(f"--live-record-limit={stage.recordLimit}")
        elif stage.customMuxAfterDone:
            args.append(f"--mux-after-done={stage.customMuxAfterDone}")
        else:
            muxOption = f"format={stage.outputFormat}:muxer=ffmpeg"
            if ffmpegPath:
                muxOption += f":bin_path={ffmpegPath}"
            args.append(f"--mux-after-done={muxOption}")

        for imp in stage.muxImports:
            text = imp.strip()
            if text:
                args.append(f"--mux-import={text}")

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
            self.stage.liveElapsed = liveMatch.group(1)
            self.stage.liveTotal = liveMatch.group(2)
            self.stage.liveStatus = liveMatch.group(3)
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
        # 进程已结束, 占位旁标去重使命完成——清掉(暂停/失败不走这里, 旁标留作并发去重)
        Path(f"{self.stage.outputFile}.ghd").unlink(missing_ok=True)
        target = Path(self.stage.outputFile)
        if target.is_file() and target.stat().st_size > 0:
            self.stage.actualExtension = target.suffix.lstrip(".")
            self.stage.task.fileSize = max(self.stage.task.fileSize, target.stat().st_size)
            return
        target.unlink(missing_ok=True)

        outputDir = self.stage.task.path
        if not outputDir.is_dir():
            return

        fallbackExtension = "ts" if self.stage.task.isLive else self.stage.outputFormat
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
        # 用 .ghd 旁标占位, 让后续同名任务被 deduplicateFilename 检测到; 不占用产物名,
        # 否则 N_m3u8DL-RE 发现同名已存在会把产物写成 <name>.copy.<ext>
        Path(f"{self.stage.outputFile}.ghd").touch(exist_ok=True)

        env = None
        if self.stage.keepImageSegments:
            env = {**os.environ, "RE_KEEP_IMAGE_SEGMENTS": "1"}

        process = None
        supervisorTask = None
        try:
            args = self._buildArgs()
            process = await asyncio.create_subprocess_exec(
                execPath,
                *args,
                cwd=Path(execPath).parent,
                env=env,
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
            if self.stage.task.isLive:
                # 直播无暂停语义：硬杀后 real-time-merge 的文件已落盘，收尾标完成
                self._updateOutput()
                self.stage.setStatus(TaskStatus.COMPLETED)
            else:
                self.stage.setStatus(TaskStatus.PAUSED)
            raise
        except Exception as e:
            self.stage.setError(e)
            raise


M3U8TaskStage.workerType = M3U8Worker
