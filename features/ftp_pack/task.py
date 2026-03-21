import asyncio
import os
import re
from asyncio import CancelledError, TaskGroup
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from struct import pack, unpack
from typing import Any
from urllib.parse import ParseResult, unquote, urlparse, urlunparse

import aioftp
from loguru import logger

from app.bases.interfaces import Worker
from app.bases.models import SpecialFileSize, Task, TaskStage, TaskStatus
from app.supports.config import cfg
from app.supports.sysio import ftruncate, pwrite
from app.supports.utils import getProxies


FTP_CONNECTION_TIMEOUT = 15
FTP_SOCKET_TIMEOUT = 30
FTP_PATH_TIMEOUT = 30
FTP_CHUNK_SIZE = 65536
FTP_RETRY_DELAY = 5


def _sanitizeName(name: str) -> str:
    cleaned = re.sub(r'[\x00-\x1f\\/:*?"<>|]+', "_", str(name or "")).strip().rstrip(".")
    return cleaned or "ftp_download"


def _parsePositiveSize(value: Any) -> int:
    try:
        size = int(value)
    except (TypeError, ValueError):
        return SpecialFileSize.UNKNOWN
    return size if size > 0 else SpecialFileSize.UNKNOWN


def _pickProxyUrl(proxies: dict | None) -> str:
    if not isinstance(proxies, dict):
        return ""
    for key in ("ftp", "https", "http"):
        value = str(proxies.get(key) or "").strip()
        if value:
            return value
    return ""


def _buildClientKwargs(proxies: dict | None) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "connection_timeout": FTP_CONNECTION_TIMEOUT,
        "socket_timeout": FTP_SOCKET_TIMEOUT,
        "path_timeout": FTP_PATH_TIMEOUT,
    }

    proxyUrl = _pickProxyUrl(proxies)
    if not proxyUrl:
        return kwargs

    parsedProxy = urlparse(proxyUrl)
    if parsedProxy.scheme not in {"socks4", "socks5"}:
        raise ValueError("FTP 下载目前仅支持 SOCKS4/SOCKS5 代理或直连")
    if not parsedProxy.hostname or not parsedProxy.port:
        raise ValueError("代理配置无效")

    kwargs.update(
        {
            "socks_host": parsedProxy.hostname,
            "socks_port": parsedProxy.port,
            "socks_version": 4 if parsedProxy.scheme == "socks4" else 5,
        }
    )
    if parsedProxy.username:
        kwargs["username"] = unquote(parsedProxy.username)
    if parsedProxy.password:
        kwargs["password"] = unquote(parsedProxy.password)
    return kwargs


@dataclass
class FtpConnectionInfo:
    host: str
    port: int = 21
    username: str = "anonymous"
    password: str = "anon@"
    sourcePath: str = "/"


@dataclass
class FtpRemoteFile:
    index: int
    remotePath: str
    relativePath: str
    size: int
    selected: bool = True
    downloadedBytes: int = 0
    completed: bool = False

    def __post_init__(self):
        self.remotePath = str(PurePosixPath(self.remotePath))
        self.relativePath = str(PurePosixPath(self.relativePath))


@dataclass(kw_only=True)
class FtpTaskStage(TaskStage):
    fileIndex: int
    remotePath: str
    fileSize: int
    resolvePath: str
    supportsRange: bool = field(default=True)
    accelerated: bool = field(default=False)


@dataclass(kw_only=True)
class FtpTask(Task):
    connectionInfo: FtpConnectionInfo | dict[str, Any]
    sourceType: str = field(default="file")
    files: list[FtpRemoteFile | dict[str, Any]] = field(default_factory=list)
    proxies: dict | None = field(default_factory=getProxies)
    blockNum: int = field(default_factory=lambda: cfg.preBlockNum.value)

    def __post_init__(self):
        if isinstance(self.connectionInfo, dict):
            self.connectionInfo = FtpConnectionInfo(**self.connectionInfo)
        self.files = [
            item if isinstance(item, FtpRemoteFile) else FtpRemoteFile(**item)
            for item in self.files
        ]
        self.title = _sanitizeName(self.title)
        super().__post_init__()
        self._recalculateSelection()
        self._syncFileProgress()
        self.syncStagePaths()

    @property
    def totalFileCount(self) -> int:
        return len(self.files)

    @property
    def selectedFileCount(self) -> int:
        return sum(1 for file in self.files if file.selected)

    @property
    def isDirectorySource(self) -> bool:
        return self.sourceType == "dir"

    @property
    def hasUnselectedFiles(self) -> bool:
        return self.selectedFileCount < self.totalFileCount

    @property
    def resolvePath(self) -> str:
        return str(Path(self.path) / self.title)

    @property
    def selectedStages(self) -> list["FtpTaskStage"]:
        stages: list[FtpTaskStage] = []
        for stage in self.stages:
            if not isinstance(stage, FtpTaskStage):
                continue
            file = self.fileByIndex(stage.fileIndex)
            if file is not None and file.selected:
                stages.append(stage)
        return stages

    def fileByIndex(self, index: int) -> FtpRemoteFile | None:
        for file in self.files:
            if file.index == index:
                return file
        return None

    def syncStagePaths(self):
        rootPath = Path(self.path) / self.title
        for stage in self.stages:
            if not isinstance(stage, FtpTaskStage):
                continue

            file = self.fileByIndex(stage.fileIndex)
            if file is None:
                continue

            if self.isDirectorySource:
                stage.resolvePath = str(rootPath / Path(*PurePosixPath(file.relativePath).parts))
            else:
                stage.resolvePath = str(rootPath)

    def setTitle(self, title: str):
        self.title = _sanitizeName(title)
        self.syncStagePaths()

    def _recalculateSelection(self):
        self.fileSize = sum(file.size for file in self.files if file.selected)

    def _syncFileProgress(self):
        stageByFileIndex = {
            stage.fileIndex: stage
            for stage in self.stages
            if isinstance(stage, FtpTaskStage)
        }

        for file in self.files:
            stage = stageByFileIndex.get(file.index)
            if stage is None:
                file.downloadedBytes = 0
                file.completed = False
                continue

            file.downloadedBytes = max(0, int(stage.receivedBytes))
            file.completed = stage.status == TaskStatus.COMPLETED
            if file.completed and file.size > 0:
                file.downloadedBytes = max(file.downloadedBytes, file.size)

    def updateSelectedFiles(self, selectedIndexes: set[int]):
        if not selectedIndexes:
            raise ValueError("至少需要选择一个文件")

        changed = False
        for file in self.files:
            selected = file.index in selectedIndexes
            if file.selected != selected:
                changed = True
            file.selected = selected

        if not changed:
            return

        self._recalculateSelection()
        self._syncFileProgress()
        self.syncStatusFromStages()

    def syncStatusFromStages(self) -> TaskStatus:
        self._syncFileProgress()
        selectedStages = self.selectedStages
        if not selectedStages:
            self.status = TaskStatus.WAITING
            return self.status

        stageStatus = [stage.status for stage in selectedStages]
        if any(status == TaskStatus.FAILED for status in stageStatus):
            self.status = TaskStatus.FAILED
        elif all(status == TaskStatus.COMPLETED for status in stageStatus):
            self.status = TaskStatus.COMPLETED
        elif any(status == TaskStatus.RUNNING for status in stageStatus):
            self.status = TaskStatus.RUNNING
        elif all(status == TaskStatus.PAUSED for status in stageStatus):
            self.status = TaskStatus.PAUSED
        else:
            self.status = TaskStatus.WAITING

        return self.status

    def setStatus(self, status: TaskStatus) -> TaskStatus:
        selectedStageIds = {stage.stageId for stage in self.selectedStages}
        for stage in self.stages:
            if stage.stageId not in selectedStageIds:
                continue
            if stage.status == TaskStatus.COMPLETED:
                continue
            if status == TaskStatus.RUNNING and stage.status == TaskStatus.FAILED:
                stage.reset(notifyTask=False)
            stage.setStatus(status, notifyTask=False)

        return self.syncStatusFromStages()

    def reset(self) -> TaskStatus:
        for file in self.files:
            file.downloadedBytes = 0
            file.completed = False
        for stage in self.stages:
            stage.reset(notifyTask=False)
        return self.syncStatusFromStages()

    def reopenForAdditionalFiles(self) -> bool:
        if self.status != TaskStatus.COMPLETED:
            return False

        pendingSelectedStages = [
            stage for stage in self.selectedStages if stage.status != TaskStatus.COMPLETED
        ]
        if not pendingSelectedStages:
            return False

        for stage in pendingSelectedStages:
            stage.setStatus(TaskStatus.PAUSED, notifyTask=False)

        self._syncFileProgress()
        self.syncStatusFromStages()
        return True

    def applyPayloadToTask(self, payload: dict[str, Any]):
        super().applyPayloadToTask(payload)
        if "proxies" in payload:
            self.proxies = payload.get("proxies")
        blockNum = payload.get("preBlockNum")
        if isinstance(blockNum, int):
            self.blockNum = blockNum
        self.syncStagePaths()

    def canPause(self) -> bool:
        selectedStages = self.selectedStages
        return bool(selectedStages) and all(stage.supportsRange for stage in selectedStages)

    async def run(self):
        self.stages.sort(key=lambda stage: stage.stageIndex)
        currentStage = None
        try:
            for stage in self.stages:
                if self.status != TaskStatus.RUNNING:
                    break
                if not isinstance(stage, FtpTaskStage):
                    continue

                file = self.fileByIndex(stage.fileIndex)
                if file is None or not file.selected:
                    continue
                if stage.status == TaskStatus.COMPLETED:
                    continue

                currentStage = stage
                await FtpWorker(stage).run()
        except CancelledError:
            logger.info(f"{self.title} 停止下载")
            raise
        except Exception as e:
            if currentStage is not None and not currentStage.error:
                currentStage.setError(e)
            logger.opt(exception=e).error("{} 下载失败", self.title)
            raise

    def __hash__(self):
        return hash(self.taskId)


@dataclass
class FtpSubworker:
    start: int
    progress: int
    end: int


class FtpWorker(Worker):
    def __init__(self, stage: FtpTaskStage):
        super().__init__(stage)
        self.stage = stage
        self.task: FtpTask = getattr(stage, "_task")
        self.speedHistory: list[int] = []
        self.accelCheckTime = 0.0

    async def _connectClient(self) -> aioftp.Client:
        client = aioftp.Client(**_buildClientKwargs(self.task.proxies))
        try:
            await client.connect(
                self.task.connectionInfo.host,
                self.task.connectionInfo.port,
            )
            await client.login(
                self.task.connectionInfo.username,
                self.task.connectionInfo.password,
            )
            return client
        except Exception:
            client.close()
            raise

    async def _closeTransfer(self, client: aioftp.Client | None, stream):
        with suppress(Exception):
            if stream is not None:
                stream.close()
        if client is not None:
            client.close()

    def reassignSubworker(self):
        if self.stage.fileSize <= 0:
            return

        slowestSubworker = max(
            self.subworkers,
            key=lambda subworker: subworker.end - subworker.progress,
        )
        remainingBytes = slowestSubworker.end - slowestSubworker.progress
        if remainingBytes < cfg.maxReassignSize.value * 1048576:
            return

        base = remainingBytes // 2
        remainder = remainingBytes % 2
        slowestSubworker.end = slowestSubworker.progress + base + remainder
        newSubworker = FtpSubworker(
            slowestSubworker.end + 1,
            slowestSubworker.end + 1,
            slowestSubworker.end + base,
        )
        self.subworkers.insert(
            self.subworkers.index(slowestSubworker) + 1,
            newSubworker,
        )
        self.taskGroup.create_task(self.handleSubworker(newSubworker))

    async def _transferRange(self, subworker: FtpSubworker):
        client = None
        stream = None
        try:
            client = await self._connectClient()
            stream = await client.download_stream(
                PurePosixPath(self.stage.remotePath),
                offset=subworker.progress,
            )

            remaining = subworker.end - subworker.progress + 1
            while remaining > 0:
                chunk = await stream.read(min(FTP_CHUNK_SIZE, remaining))
                if not chunk:
                    raise RuntimeError("FTP 数据流提前结束")

                await cfg.checkSpeedLimitation()
                pwrite(self.fileHandle, chunk, subworker.progress)
                subworker.progress += len(chunk)
                remaining -= len(chunk)
                cfg.globalSpeed += len(chunk)
        finally:
            await self._closeTransfer(client, stream)

    async def _transferUnknown(self, subworker: FtpSubworker):
        client = None
        stream = None
        try:
            client = await self._connectClient()
            stream = await client.download_stream(
                PurePosixPath(self.stage.remotePath),
                offset=subworker.progress,
            )

            while True:
                chunk = await stream.read(FTP_CHUNK_SIZE)
                if not chunk:
                    return

                await cfg.checkSpeedLimitation()
                pwrite(self.fileHandle, chunk, subworker.progress)
                subworker.progress += len(chunk)
                cfg.globalSpeed += len(chunk)
        finally:
            await self._closeTransfer(client, stream)

    async def _transferWholeFile(self, subworker: FtpSubworker):
        client = None
        stream = None
        try:
            client = await self._connectClient()
            stream = await client.download_stream(PurePosixPath(self.stage.remotePath))

            ftruncate(self.fileHandle, 0)
            subworker.progress = 0

            while True:
                chunk = await stream.read(FTP_CHUNK_SIZE)
                if not chunk:
                    ftruncate(self.fileHandle, subworker.progress)
                    return

                await cfg.checkSpeedLimitation()
                pwrite(self.fileHandle, chunk, subworker.progress)
                subworker.progress += len(chunk)
                cfg.globalSpeed += len(chunk)
        finally:
            await self._closeTransfer(client, stream)

    async def handleSubworker(self, subworker: FtpSubworker):
        if subworker.end == SpecialFileSize.UNKNOWN:
            while True:
                try:
                    await self._transferUnknown(subworker)
                    return
                except Exception as e:
                    logger.opt(exception=e).error(
                        "{} 的未知大小分片 {} 连接中断，5 秒后重试",
                        self.stage.resolvePath,
                        subworker,
                    )
                    await asyncio.sleep(FTP_RETRY_DELAY)
        elif subworker.end == SpecialFileSize.NOT_SUPPORTED:
            while True:
                try:
                    await self._transferWholeFile(subworker)
                    return
                except Exception as e:
                    logger.opt(exception=e).error(
                        "{} 不支持断点续传，已从头开始重试",
                        self.stage.resolvePath,
                    )
                    await asyncio.sleep(FTP_RETRY_DELAY)
        else:
            while subworker.progress <= subworker.end:
                try:
                    await self._transferRange(subworker)
                    break
                except Exception as e:
                    logger.opt(exception=e).error(
                        "{} 的分片 {} 连接中断，5 秒后重试",
                        self.stage.resolvePath,
                        subworker,
                    )
                    await asyncio.sleep(FTP_RETRY_DELAY)

            if subworker.progress > subworker.end:
                subworker.progress = subworker.end + 1

            self.reassignSubworker()

    def checkIfAutoAcceleration(self):
        if self.stage.accelerated or not cfg.autoSpeedUp.value:
            return

        self.speedHistory.append(self.stage.speed)
        if len(self.speedHistory) > 5:
            self.speedHistory.pop(0)
        if len(self.speedHistory) < 5:
            return

        avgSpeed = sum(self.speedHistory) / len(self.speedHistory)
        if avgSpeed == 0:
            return

        maxDeviation = max(
            abs(speed - avgSpeed) / avgSpeed for speed in self.speedHistory
        )
        if maxDeviation > 0.15:
            return

        if self.accelCheckTime == 0:
            self.accelInitialWorkers = len(self.subworkers)
            self.accelInitialSpeed = avgSpeed
            self.accelCheckTime = asyncio.get_event_loop().time()

            for _ in range(4):
                self.reassignSubworker()
        else:
            elapsedTime = asyncio.get_event_loop().time() - self.accelCheckTime
            if elapsedTime <= 5:
                return

            currentWorkers = len(self.subworkers)
            workerIncreaseRatio = (
                (currentWorkers - self.accelInitialWorkers) / self.accelInitialWorkers
            )
            speedIncreaseRatio = (
                (avgSpeed - self.accelInitialSpeed) / self.accelInitialSpeed
            )

            if speedIncreaseRatio < 0.8 * workerIncreaseRatio:
                self.stage.accelerated = True
                logger.info(
                    "FTP 自动加速已禁用，subworker 增加比: {:.2%}, 速度提升比: {:.2%}",
                    workerIncreaseRatio,
                    speedIncreaseRatio,
                )
            else:
                self.accelCheckTime = 0
                logger.info(
                    "继续 FTP 自动加速，subworker 增加比: {:.2%}, 速度提升比: {:.2%}",
                    workerIncreaseRatio,
                    speedIncreaseRatio,
                )

    async def supervisor(self):
        recordFileHandle = None
        if self.stage.supportsRange:
            recordFileHandle = open(Path(self.stage.resolvePath + ".ghd"), "wb")
        try:
            self.stage.receivedBytes = sum(
                subworker.progress - subworker.start for subworker in self.subworkers
            )
            while True:
                if recordFileHandle is not None:
                    data = tuple(
                        value
                        for subworker in self.subworkers
                        for value in (
                            subworker.start,
                            subworker.progress,
                            subworker.end,
                        )
                    )
                    recordFileHandle.seek(0)
                    recordFileHandle.write(pack("<" + "Q" * len(data), *data))
                    recordFileHandle.flush()
                    recordFileHandle.truncate()

                receivedBytes = sum(
                    subworker.progress - subworker.start
                    for subworker in self.subworkers
                )
                self.stage.speed = receivedBytes - self.stage.receivedBytes
                self.stage.receivedBytes = receivedBytes
                if self.stage.fileSize > 0:
                    self.stage.progress = (receivedBytes / self.stage.fileSize) * 100
                else:
                    self.stage.progress = 0

                self.checkIfAutoAcceleration()
                await asyncio.sleep(1)
        except CancelledError:
            logger.info(f"{self.stage.resolvePath} 停止下载")
        except Exception as e:
            logger.opt(exception=e).error(
                "{} 的监控协程异常退出",
                self.stage.resolvePath,
            )
        finally:
            if recordFileHandle is not None:
                recordFileHandle.close()

    def restoreProgress(self) -> bool:
        recordFile = Path(self.stage.resolvePath + ".ghd")
        if not recordFile.exists():
            return False

        try:
            with open(recordFile, "rb") as f:
                while True:
                    data = f.read(24)
                    if not data:
                        break
                    start, progress, end = unpack("<QQQ", data)
                    self.subworkers.append(FtpSubworker(start, progress, end))
            return True
        except Exception as e:
            logger.opt(exception=e).error("恢复 FTP 下载分片失败 {}", self.stage.resolvePath)
            self.subworkers.clear()
            return False

    def generateSubworkers(self):
        if not self.stage.supportsRange:
            self.subworkers.append(FtpSubworker(0, 0, SpecialFileSize.NOT_SUPPORTED))
            return

        if self.stage.fileSize <= 0:
            self.subworkers.append(FtpSubworker(0, 0, SpecialFileSize.UNKNOWN))
            return

        step = self.stage.fileSize // self.task.blockNum
        if step <= 0:
            self.subworkers.append(FtpSubworker(0, 0, max(0, self.stage.fileSize - 1)))
            return

        start = 0
        for _ in range(self.task.blockNum - 1):
            end = start + step - 1
            self.subworkers.append(FtpSubworker(start, start, end))
            start = end + 1

        self.subworkers.append(FtpSubworker(start, start, self.stage.fileSize - 1))

    def _cleanupRecordFile(self):
        target = Path(self.stage.resolvePath + ".ghd")
        try:
            if target.is_file() or target.is_symlink():
                target.unlink()
        except Exception as e:
            logger.opt(exception=e).error("failed to cleanup temporary file {}", target)

    async def run(self):
        self.taskGroup = TaskGroup()
        self.subworkers: list[FtpSubworker] = []
        shouldCleanupRecordFile = False
        Path(self.stage.resolvePath).parent.mkdir(parents=True, exist_ok=True)

        restored = False
        if self.stage.supportsRange:
            restored = self.restoreProgress()
        else:
            self._cleanupRecordFile()

        if not restored:
            logger.info("正在为 {} 生成 FTP 下载分片", self.stage.resolvePath)
            self.generateSubworkers()
        else:
            logger.info("从进度文件恢复 FTP 下载分片 {}", self.stage.resolvePath)

        openMode = os.O_RDWR | os.O_CREAT
        if not self.stage.supportsRange:
            openMode |= os.O_TRUNC
        self.fileHandle = os.open(self.stage.resolvePath, openMode, 0o666)

        if not restored and self.stage.fileSize > 0:
            try:
                ftruncate(self.fileHandle, self.stage.fileSize)
            except Exception as e:
                logger.opt(exception=e).error("{} 预分配文件大小失败", self.stage.resolvePath)

        supervisor = asyncio.create_task(self.supervisor())

        try:
            async with self.taskGroup:
                for subworker in self.subworkers:
                    self.taskGroup.create_task(self.handleSubworker(subworker))

            self.stage.setStatus(TaskStatus.COMPLETED)
            shouldCleanupRecordFile = True
            logger.info("{} 下载完成", self.stage.resolvePath)
        except CancelledError:
            self.stage.setStatus(TaskStatus.PAUSED)
            raise
        except Exception as e:
            self.stage.setError(e)
            logger.opt(exception=e).error("{} 下载阶段失败", self.stage.resolvePath)
            raise
        finally:
            if not supervisor.done():
                supervisor.cancel()
                with suppress(asyncio.CancelledError):
                    await supervisor
            os.close(self.fileHandle)
            if shouldCleanupRecordFile:
                self._cleanupRecordFile()


async def _openClient(connectionInfo: FtpConnectionInfo, proxies: dict | None) -> aioftp.Client:
    client = aioftp.Client(**_buildClientKwargs(proxies))
    try:
        await client.connect(connectionInfo.host, connectionInfo.port)
        await client.login(connectionInfo.username, connectionInfo.password)
        return client
    except Exception:
        client.close()
        raise


async def _closeClient(client: aioftp.Client | None):
    if client is None:
        return
    try:
        await client.quit()
    except Exception:
        client.close()


def _sanitizeDisplayUrl(parsed: ParseResult) -> str:
    host = parsed.hostname or ""
    if parsed.port:
        host = f"{host}:{parsed.port}"
    if parsed.username:
        host = f"{parsed.username}@{host}"

    return urlunparse(
        (
            parsed.scheme,
            host,
            parsed.path,
            parsed.params,
            parsed.query,
            parsed.fragment,
        )
    )


def _displayTitleForSource(path: PurePosixPath, *, host: str, sourceType: str) -> str:
    if sourceType == "file" and path.name:
        return _sanitizeName(path.name)
    if path.name:
        return _sanitizeName(path.name)
    return _sanitizeName(host)


async def _probeRangeSupport(client: aioftp.Client) -> bool:
    try:
        await client.command("TYPE I", "200")
        await client.command("REST 1", "350")
        return True
    except Exception as e:
        logger.info("FTP 服务器不支持 REST 断点续传: {}", repr(e))
        return False


def _relativeRemotePath(remotePath: PurePosixPath, rootPath: PurePosixPath) -> str:
    try:
        return str(remotePath.relative_to(rootPath))
    except ValueError:
        return remotePath.name


async def parse(payload: dict) -> FtpTask:
    url = str(payload["url"]).strip()
    parsedUrl = urlparse(url)
    if parsedUrl.scheme.lower() != "ftp":
        raise ValueError("不是有效的 FTP 链接")
    if not parsedUrl.hostname:
        raise ValueError("FTP 链接缺少主机名")

    sourcePath = PurePosixPath(unquote(parsedUrl.path or "/"))
    connectionInfo = FtpConnectionInfo(
        host=parsedUrl.hostname,
        port=parsedUrl.port or 21,
        username=unquote(parsedUrl.username or "anonymous"),
        password=unquote(parsedUrl.password or "anon@"),
        sourcePath=str(sourcePath),
    )
    proxies = payload.get("proxies", getProxies())
    path = Path(payload.get("path", cfg.downloadFolder.value))
    blockNum = payload.get("preBlockNum", cfg.preBlockNum.value)

    client = await _openClient(connectionInfo, proxies)
    try:
        sourceInfo = await client.stat(sourcePath)
        sourceType = sourceInfo["type"]
        if sourceType not in {"file", "dir"}:
            raise ValueError("当前 FTP 路径既不是普通文件，也不是目录")

        supportsRange = await _probeRangeSupport(client)
        files: list[FtpRemoteFile] = []
        stages: list[FtpTaskStage] = []

        if sourceType == "file":
            files.append(
                FtpRemoteFile(
                    index=0,
                    remotePath=str(sourcePath),
                    relativePath=sourcePath.name or "ftp_file",
                    size=_parsePositiveSize(sourceInfo.get("size")),
                )
            )
        else:
            entries = [item async for item in client.list(sourcePath, recursive=True)]
            index = 0
            for remotePath, info in entries:
                if info["type"] != "file":
                    continue
                files.append(
                    FtpRemoteFile(
                        index=index,
                        remotePath=str(remotePath),
                        relativePath=_relativeRemotePath(remotePath, sourcePath),
                        size=_parsePositiveSize(info.get("size")),
                    )
                )
                index += 1

            if not files:
                raise ValueError("该 FTP 目录中没有可下载的普通文件")

        for file in files:
            stages.append(
                FtpTaskStage(
                    stageIndex=len(stages) + 1,
                    fileIndex=file.index,
                    remotePath=file.remotePath,
                    fileSize=file.size,
                    resolvePath="",
                    supportsRange=supportsRange,
                )
            )

        task = FtpTask(
            title=_displayTitleForSource(
                sourcePath,
                host=connectionInfo.host,
                sourceType=sourceType,
            ),
            url=_sanitizeDisplayUrl(parsedUrl),
            fileSize=sum(file.size for file in files if file.selected),
            path=path,
            stages=stages,
            connectionInfo=connectionInfo,
            sourceType=sourceType,
            files=files,
            proxies=proxies,
            blockNum=blockNum if isinstance(blockNum, int) else cfg.preBlockNum.value,
        )
        task.syncStagePaths()
        return task
    finally:
        await _closeClient(client)
