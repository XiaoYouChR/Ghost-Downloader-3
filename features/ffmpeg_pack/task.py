import asyncio
import platform
import shutil
import sys
import zipfile
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TYPE_CHECKING

import niquests
from loguru import logger

from app.bases.interfaces import Worker
from app.bases.models import Task, TaskStage, TaskStatus
from app.supports.config import DEFAULT_HEADERS, cfg
from app.supports.utils import getProxies
from .config import (
    ffmpegConfig,
    resolveFFmpegExecutables,
    setPreferredFFmpegExecutables,
)

if TYPE_CHECKING:
    from features.http_pack.task import HttpTaskStage, HttpWorker
else:
    from http_pack.task import HttpTaskStage, HttpWorker


_FFMPEG_RELEASE_API = "https://api.github.com/repos/BtbN/FFmpeg-Builds/releases/latest"
_FFMPEG_HEADERS = {
    "accept": "application/vnd.github+json",
    "user-agent": DEFAULT_HEADERS["user-agent"],
}


def _executableName(name: str) -> str:
    return f"{name}.exe" if sys.platform == "win32" else name


def _normalizePath(path: Path | str) -> str:
    return str(Path(path)).replace("\\", "/")


def _detectWindowsTarget() -> tuple[str, str]:
    if sys.platform != "win32":
        raise RuntimeError("一键安装 FFmpeg 仅支持 Windows 平台")

    machine = platform.machine().lower()
    if machine in {"amd64", "x86_64"}:
        return "win64", "x64"
    if machine in {"arm64", "aarch64"}:
        return "winarm64", "arm64"
    raise RuntimeError(f"不支持的 Windows 架构: {platform.machine()}")


def _selectReleaseAsset(assets: list[dict[str, Any]]) -> dict[str, Any]:
    target, _ = _detectWindowsTarget()
    candidates: list[tuple[int, dict[str, Any]]] = []
    for asset in assets:
        name = str(asset.get("name") or "")
        lowerName = name.lower()
        if target not in lowerName or not lowerName.endswith(".zip") or "shared" in lowerName:
            continue

        score = 0
        if "master-latest" in lowerName:
            score += 100
        if "-gpl" in lowerName:
            score += 10
        if "-latest-" in lowerName:
            score += 5
        candidates.append((score, asset))

    if not candidates:
        raise RuntimeError(f"未找到适用于当前平台的 FFmpeg 安装包: {target}")

    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


async def _requestLatestReleaseAsset() -> dict[str, Any]:
    client = niquests.AsyncSession(headers=_FFMPEG_HEADERS, timeout=30, happy_eyeballs=True)
    client.trust_env = False

    try:
        response = await client.get(
            _FFMPEG_RELEASE_API,
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
        raise RuntimeError("GitHub Release 返回了不完整的 FFmpeg 安装包信息")

    return {
        "name": assetName,
        "url": downloadUrl,
        "size": size,
    }


@dataclass
class FFmpegStage(TaskStage):
    videoPath: str
    audioPath: str
    resolvePath: str
    cleanupSource: bool = field(default=True)


class FFmpegWorker(Worker):
    def __init__(self, stage: FFmpegStage):
        super().__init__(stage)
        self.stage = stage

    @staticmethod
    def _parseDuration(value: Any) -> float:
        try:
            duration = float(value)
        except (TypeError, ValueError):
            return 0.0

        if duration > 0:
            return duration
        return 0.0

    async def _probeDuration(self, ffprobe: str, path: str) -> float:
        process = await asyncio.create_subprocess_exec(
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            message = stderr.decode("utf-8", errors="ignore").strip()
            logger.warning(f"ffprobe 获取时长失败: {path}, {message or process.returncode}")
            return 0.0

        return self._parseDuration(stdout.decode("utf-8", errors="ignore").strip())

    async def _probeVideoDuration(self, ffprobe: str) -> float:
        return await self._probeDuration(ffprobe, self.stage.videoPath)

    async def _readProgress(self, stream: asyncio.StreamReader | None, totalDuration: float):
        if stream is None:
            return

        while True:
            rawLine = await stream.readline()
            if not rawLine:
                break

            line = rawLine.decode("utf-8", errors="ignore").strip()
            if not line:
                continue

            if line.startswith("out_time_us=") and totalDuration > 0:
                currentDuration = self._parseDuration(line.removeprefix("out_time_us=")) / 1_000_000
                if currentDuration <= 0:
                    continue
                self.stage.progress = min(99.5, max(0.0, currentDuration / totalDuration * 100))
            elif line == "progress=end":
                self.stage.progress = 100

    async def run(self):
        ffmpeg, ffprobe = resolveFFmpegExecutables()
        if not ffmpeg or not ffprobe:
            self.stage.setStatus(TaskStatus.FAILED)
            raise RuntimeError("未找到可用的 ffmpeg 和 ffprobe，请先在设置中安装或配置 FFmpeg")

        outputPath = Path(self.stage.resolvePath)
        outputPath.parent.mkdir(parents=True, exist_ok=True)

        process = None
        progressTask = None
        try:
            self.stage.progress = 0
            self.stage.speed = 0
            self.stage.receivedBytes = 0
            totalDuration = await self._probeVideoDuration(ffprobe)
            process = await asyncio.create_subprocess_exec(
                ffmpeg,
                "-y",
                "-v",
                "error",
                "-nostats",
                "-progress",
                "pipe:1",
                "-i",
                self.stage.videoPath,
                "-i",
                self.stage.audioPath,
                "-c",
                "copy",
                self.stage.resolvePath,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            progressTask = asyncio.create_task(self._readProgress(process.stdout, totalDuration))

            await process.wait()
            await progressTask
            if process.returncode != 0:
                raise RuntimeError(f"ffmpeg 退出码异常: {process.returncode}")

            self.stage.setStatus(TaskStatus.COMPLETED)
            if self.stage.cleanupSource:
                self._cleanupSourceFiles()
        except asyncio.CancelledError:
            self.stage.setStatus(TaskStatus.PAUSED)
            if process is not None and process.returncode is None:
                process.kill()
                await process.wait()
            if progressTask is not None and not progressTask.done():
                progressTask.cancel()
                with suppress(asyncio.CancelledError):
                    await progressTask
            raise
        except Exception as e:
            self.stage.setError(e)
            raise

    def _cleanupSourceFiles(self):
        for rawPath in (self.stage.videoPath, self.stage.audioPath):
            target = Path(rawPath)
            for path in (target, Path(rawPath + ".ghd")):
                try:
                    if path.is_file() or path.is_symlink():
                        path.unlink()
                except FileNotFoundError:
                    continue
                except Exception as e:
                    logger.opt(exception=e).error("failed to cleanup temporary file {}", path)


@dataclass
class FFmpegExtractStage(TaskStage):
    archivePath: str
    installFolder: str
    ffmpegPath: str
    ffprobePath: str
    cleanupArchive: bool = field(default=True)


class FFmpegExtractWorker(Worker):
    chunkSize = 1048576

    def __init__(self, stage: FFmpegExtractStage):
        super().__init__(stage)
        self.stage = stage

    def _removePath(self, path: Path):
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path, ignore_errors=True)
        else:
            with suppress(FileNotFoundError):
                path.unlink()

    def _updateTaskFileSize(self, extractedSize: int):
        task = getattr(self.stage, "_task", None)
        if task is None:
            return

        archiveSize = int(getattr(task, "archiveSize", 0) or 0)
        task.fileSize = max(archiveSize + extractedSize, archiveSize)

    def _resolveExtractedRoot(self, tempDir: Path) -> Path:
        children = list(tempDir.iterdir())
        if len(children) == 1 and children[0].is_dir():
            return children[0]
        return tempDir

    def _findExecutable(self, root: Path, name: str) -> Path | None:
        directPath = root / "bin" / name
        if directPath.is_file():
            return directPath

        for candidate in root.rglob(name):
            if candidate.is_file():
                return candidate

        return None

    async def _extractArchive(self, archivePath: Path, tempDir: Path, totalSize: int):
        extractedBytes = 0
        speedBytes = 0
        speedTime = asyncio.get_running_loop().time()

        with zipfile.ZipFile(archivePath) as archive:
            infos = [info for info in archive.infolist() if not info.is_dir()]
            for info in infos:
                targetPath = tempDir / info.filename
                targetPath.parent.mkdir(parents=True, exist_ok=True)

                with archive.open(info, "r") as source, open(targetPath, "wb") as target:
                    while True:
                        chunk = source.read(self.chunkSize)
                        if not chunk:
                            break

                        target.write(chunk)
                        extractedBytes += len(chunk)
                        self.stage.receivedBytes = extractedBytes
                        if totalSize > 0:
                            self.stage.progress = min(99.5, max(0.0, extractedBytes / totalSize * 100))

                        now = asyncio.get_running_loop().time()
                        if now - speedTime >= 0.5:
                            self.stage.speed = int((extractedBytes - speedBytes) / (now - speedTime))
                            speedBytes = extractedBytes
                            speedTime = now
                            await asyncio.sleep(0)

    def _installExtractedFiles(self, extractedRoot: Path, installDir: Path, archiveName: str, tempDirName: str) -> tuple[str, str]:
        for child in installDir.iterdir():
            if child.name in {archiveName, tempDirName}:
                continue
            self._removePath(child)

        for child in list(extractedRoot.iterdir()):
            target = installDir / child.name
            if target.exists():
                self._removePath(target)
            shutil.move(str(child), str(target))

        ffmpegPath = self._findExecutable(installDir, _executableName("ffmpeg"))
        ffprobePath = self._findExecutable(installDir, _executableName("ffprobe"))
        if ffmpegPath is None or ffprobePath is None:
            raise RuntimeError("安装包解压完成，但未找到 ffmpeg 或 ffprobe 可执行文件")

        return _normalizePath(ffmpegPath), _normalizePath(ffprobePath)

    async def run(self):
        if sys.platform != "win32":
            self.stage.setStatus(TaskStatus.FAILED)
            raise RuntimeError("当前平台不支持 FFmpeg 一键安装")

        archivePath = Path(self.stage.archivePath)
        if not archivePath.is_file():
            self.stage.setStatus(TaskStatus.FAILED)
            raise FileNotFoundError(f"未找到 FFmpeg 安装包: {archivePath}")

        installDir = Path(self.stage.installFolder)
        tempDir = installDir / ".extracting"

        try:
            self.stage.progress = 0
            self.stage.speed = 0
            self.stage.receivedBytes = 0

            installDir.mkdir(parents=True, exist_ok=True)
            if tempDir.exists():
                shutil.rmtree(tempDir, ignore_errors=True)
            tempDir.mkdir(parents=True, exist_ok=True)

            with zipfile.ZipFile(archivePath) as archive:
                extractSize = sum(info.file_size for info in archive.infolist() if not info.is_dir())

            self._updateTaskFileSize(extractSize)
            await self._extractArchive(archivePath, tempDir, extractSize)

            extractedRoot = self._resolveExtractedRoot(tempDir)
            ffmpegPath, ffprobePath = self._installExtractedFiles(
                extractedRoot,
                installDir,
                archivePath.name,
                tempDir.name,
            )

            task = getattr(self.stage, "_task", None)
            if task is not None:
                task.ffmpegPath = ffmpegPath
                task.ffprobePath = ffprobePath

            cfg.set(ffmpegConfig.installFolder, _normalizePath(installDir))
            setPreferredFFmpegExecutables(ffmpegPath, ffprobePath)

            if self.stage.cleanupArchive and archivePath.exists():
                archivePath.unlink()

            self.stage.ffmpegPath = ffmpegPath
            self.stage.ffprobePath = ffprobePath
            self.stage.setStatus(TaskStatus.COMPLETED)
        except asyncio.CancelledError:
            self.stage.setStatus(TaskStatus.PAUSED)
            raise
        except Exception as e:
            self.stage.setError(e)
            raise
        finally:
            if tempDir.exists():
                shutil.rmtree(tempDir, ignore_errors=True)


@dataclass(kw_only=True)
class FFmpegInstallTask(Task):
    url: str
    assetName: str
    headers: dict = field(default_factory=lambda: _FFMPEG_HEADERS.copy())
    proxies: dict = field(default_factory=getProxies)
    blockNum: int = field(default=8)
    installFolder: str
    archiveSize: int = field(default=0)
    archivePath: str = field(default="")
    ffmpegPath: str = field(default="")
    ffprobePath: str = field(default="")

    @property
    def resolvePath(self) -> str:
        return self.ffmpegPath or self.archivePath or str(Path(self.installFolder) / self.title)

    def __post_init__(self):
        super().__post_init__()
        self.syncStagePaths()

    def syncStagePaths(self):
        installDir = Path(self.installFolder)
        self.path = installDir
        self.archivePath = _normalizePath(installDir / self.assetName)
        self.ffmpegPath = _normalizePath(installDir / "bin" / _executableName("ffmpeg"))
        self.ffprobePath = _normalizePath(installDir / "bin" / _executableName("ffprobe"))

        for stage in self.stages:
            if isinstance(stage, HttpTaskStage):
                stage.resolvePath = self.archivePath
            elif isinstance(stage, FFmpegExtractStage):
                stage.archivePath = self.archivePath
                stage.installFolder = _normalizePath(installDir)
                stage.ffmpegPath = self.ffmpegPath
                stage.ffprobePath = self.ffprobePath

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

                if isinstance(stage, FFmpegExtractStage):
                    await FFmpegExtractWorker(stage).run()
                    continue

                raise TypeError(f"不支持的 FFmpegInstallTaskStage: {type(stage).__name__}")
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


async def createWindowsInstallTask() -> FFmpegInstallTask:
    assetInfo = await _requestLatestReleaseAsset()
    _, archLabel = _detectWindowsTarget()
    installFolder = ffmpegConfig.installFolder.value
    installPath = Path(installFolder)

    task = FFmpegInstallTask(
        title=f"FFmpeg 安装 ({archLabel})",
        url=assetInfo["url"],
        assetName=assetInfo["name"],
        fileSize=assetInfo["size"],
        headers=_FFMPEG_HEADERS.copy(),
        proxies=getProxies(),
        path=installPath,
        installFolder=installFolder,
        archiveSize=assetInfo["size"],
    )

    downloadStage = HttpTaskStage(
        stageIndex=1,
        url=task.url,
        fileSize=assetInfo["size"],
        headers=task.headers.copy(),
        proxies=task.proxies,
        resolvePath=task.archivePath,
        blockNum=task.blockNum,
    )
    extractStage = FFmpegExtractStage(
        stageIndex=2,
        archivePath=task.archivePath,
        installFolder=task.installFolder,
        ffmpegPath=task.ffmpegPath,
        ffprobePath=task.ffprobePath,
    )

    task.addStage(downloadStage)
    task.addStage(extractStage)
    task.syncStagePaths()
    return task
