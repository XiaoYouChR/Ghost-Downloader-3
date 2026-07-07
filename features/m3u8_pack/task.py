from __future__ import annotations

import asyncio
import os
import re
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path

from app.config.cfg import cfg
from app.format import toBytes
from app.models.task import Task, TaskError, TaskStep, TaskStatus
from app.platform.filesystem import deletePath, toPosixPath
from .config import m3u8Runtime

VOD_PROGRESS_PATTERN = re.compile(
    r"(\d+)/(\d+)\s+(\d+\.\d+)%\s+(\d+\.\d+)(KB|MB|GB|B)/(\d+\.\d+)(KB|MB|GB|B)\s+(\d+\.\d+)(GBps|MBps|KBps|Bps)\s+(.+)"
)
LIVE_PROGRESS_PATTERN = re.compile(
    r"(\d{2}m\d{2}s)/(\d{2}m\d{2}s)\s+\d+/\d+\s+(Recording|Waiting)\s+(\d+)%\s+(-|(\d+\.\d+)(GBps|MBps|KBps|Bps))"
)
IGNORED_OUTPUT_SUFFIXES = {".json", ".txt", ".log", ".tmp", ".ghd"}
DECRYPTION_ENGINES = {
    "FFmpeg": "FFMPEG",
    "MP4Decrypt": "MP4DECRYPT",
    "Shaka Packager": "SHAKA_PACKAGER",
}


@dataclass(kw_only=True, eq=False)
class M3U8Task(Task):
    packId: str = "m3u8"
    canEdit = True
    manifestType: str = "m3u8"
    isLive: bool = False
    streams: list[dict] = field(default_factory=list)

    def _move(self, newFolder: Path) -> None:
        from shutil import move
        oldTemp = self.outputFolder / ".gd3_m3u8" / self.taskId
        if oldTemp.exists():
            newTemp = newFolder / ".gd3_m3u8" / self.taskId
            newTemp.parent.mkdir(parents=True, exist_ok=True)
            move(str(oldTemp), str(newTemp))
        super()._move(newFolder)


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
    actualExtension: str = ""

    @property
    def canPause(self) -> bool:
        return not self.task.isLive

    @property
    def outputPath(self) -> str:
        return toPosixPath(self.task.outputFolder / self.task.name)

    @property
    def _tempFolder(self) -> str:
        return toPosixPath(self.task.outputFolder / ".gd3_m3u8" / self.task.taskId)

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

    def moveFiles(self, oldFolder: Path, newFolder: Path) -> None:
        from shutil import move
        super().moveFiles(oldFolder, newFolder)
        rawPath = self.outputPath
        if rawPath:
            ghdPath = Path(f"{rawPath}.ghd")
            if ghdPath.exists():
                try:
                    relPath = Path(rawPath).relative_to(oldFolder)
                    newGhd = newFolder / f"{relPath}.ghd"
                    newGhd.parent.mkdir(parents=True, exist_ok=True)
                    move(str(ghdPath), str(newGhd))
                except ValueError:
                    pass
        oldTemp = Path(self._tempFolder)
        if oldTemp.is_dir():
            newTemp = newFolder / ".gd3_m3u8" / self.task.taskId
            newTemp.parent.mkdir(parents=True, exist_ok=True)
            move(str(oldTemp), str(newTemp))

    def deleteFiles(self) -> bool:
        tempFolder = Path(self._tempFolder)
        ok = deletePath(tempFolder)
        try:
            tempFolder.parent.rmdir()
        except OSError:
            pass
        outputDir = self.task.outputFolder
        if not outputDir.is_dir():
            return ok
        prefix = f"{self._saveName}."
        for candidate in outputDir.iterdir():
            if candidate.is_file() and candidate.name.startswith(prefix) and candidate.name != self.task.name:
                try:
                    candidate.unlink(missing_ok=True)
                except OSError:
                    ok = False
        return ok

    def _buildCommand(self) -> list[str]:
        def toBool(v: bool) -> str:
            return "true" if v else "false"

        args = [
            self.task.url,
            f"--save-dir={toPosixPath(self.task.outputFolder)}",
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

        self.lastMessage = text[:1000]

        vodMatch = VOD_PROGRESS_PATTERN.search(text)
        if vodMatch:
            self.progress = float(vodMatch.group(3))
            self.receivedBytes = toBytes(vodMatch.group(4), vodMatch.group(5))
            self.speed = toBytes(vodMatch.group(8), vodMatch.group(9))
            totalSize = toBytes(vodMatch.group(6), vodMatch.group(7))
            if totalSize > 0:
                self.task.fileSize = totalSize
            return

        liveMatch = LIVE_PROGRESS_PATTERN.search(text)
        if liveMatch:
            self.liveElapsed = liveMatch.group(1)
            self.liveTotal = liveMatch.group(2)
            self.liveStatus = liveMatch.group(3)
            self.progress = float(liveMatch.group(4))
            self.speed = 0 if liveMatch.group(5) == "-" else toBytes(liveMatch.group(6), liveMatch.group(7))

    async def _readOutput(self, stream: asyncio.StreamReader):
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

    def _findOutputFile(self):
        Path(f"{self.outputPath}.ghd").unlink(missing_ok=True)
        target = Path(self.outputPath)
        if target.is_file() and target.stat().st_size > 0:
            self.actualExtension = target.suffix.lstrip(".")
            self.task.fileSize = max(self.task.fileSize, target.stat().st_size)
            return
        target.unlink(missing_ok=True)

        outputDir = self.task.outputFolder
        if not outputDir.is_dir():
            return

        fallbackExt = "ts" if self.task.isLive else self.outputFormat
        expectedSuffix = f".{self.actualExtension or fallbackExt}"
        prefix = self._saveName.lower()

        candidates = [
            c for c in outputDir.iterdir()
            if c.is_file()
            and c.suffix.lower() not in IGNORED_OUTPUT_SUFFIXES
            and c.name.lower().startswith(prefix)
        ]
        if not candidates:
            return

        candidates.sort(key=lambda p: (p.suffix.lower() != expectedSuffix, -p.stat().st_mtime))
        found = candidates[0]
        self.actualExtension = found.suffix.lstrip(".")
        self.task.fileSize = max(self.task.fileSize, found.stat().st_size)
        if found.name != self.task.name:
            self.task.setName(found.name)

    async def run(self) -> None:
        self._stopping = False
        self._process = None

        execPath = m3u8Runtime.path()
        if not execPath:
            raise TaskError("{name} 未安装，请在设置中安装", name="N_m3u8DL-RE")

        self.task.outputFolder.mkdir(parents=True, exist_ok=True)
        Path(self._tempFolder).mkdir(parents=True, exist_ok=True)
        Path(f"{self.outputPath}.ghd").touch(exist_ok=True)

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
                raise TaskError(
                    "进程异常退出（{code}）：{detail}",
                    code=self._process.returncode,
                    detail=self.lastMessage or "N_m3u8DL-RE",
                )

            self._findOutputFile()
            self.setStatus(TaskStatus.COMPLETED)
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
