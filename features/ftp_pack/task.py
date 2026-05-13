import asyncio
import os
import ssl
from asyncio import CancelledError
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from struct import pack, unpack
from typing import Any
from urllib.parse import unquote, urlparse

import aioftp
from loguru import logger

from app.bases.interfaces import Worker
from app.bases.models import SpecialFileSize, Task, TaskStage, TaskStatus
from app.supports.config import cfg
from app.supports.sysio import ftruncate, pwrite
from app.supports.utils import getProxies, toSafeFilename


FTP_CONNECTION_TIMEOUT = 15
FTP_SOCKET_TIMEOUT = 30
FTP_PATH_TIMEOUT = 30
FTP_CHUNK_SIZE = 65536
FTP_RETRY_DELAY = 5
FTP_DEFAULT_PORT = 21
FTPS_DEFAULT_PORT = 990

def _parseSize(value) -> int:
    size = int(value or 0)
    return size if size > 0 else SpecialFileSize.UNKNOWN


def _buildArgs(proxies: dict | None) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "connection_timeout": FTP_CONNECTION_TIMEOUT,
        "socket_timeout": FTP_SOCKET_TIMEOUT,
        "path_timeout": FTP_PATH_TIMEOUT,
    }

    proxyUrl = ""
    if isinstance(proxies, dict):
        for key in ("ftp", "https", "http"):
            value = str(proxies.get(key) or "").strip()
            if value:
                proxyUrl = value
                break
    if not proxyUrl:
        return kwargs

    parsedProxy = urlparse(proxyUrl)
    if parsedProxy.scheme not in {"socks4", "socks5"}:
        raise ValueError("FTP/FTPS 下载目前仅支持 SOCKS4/SOCKS5 代理或直连")
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
    scheme: str = "ftp"
    port: int = FTP_DEFAULT_PORT
    username: str = "anonymous"
    password: str = "anon@"
    sourcePath: str = "/"
    portSpecified: bool = False

@dataclass
class FtpFile:
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
class FtpStage(TaskStage):
    fileIndex: int
    remotePath: str
    fileSize: int
    outputFile: str
    supportsRange: bool = field(default=True)
    accelerated: bool = field(default=False)

    def setStatus(self, status: TaskStatus, sync: bool = True):
        if status == TaskStatus.COMPLETED:
            self.receivedBytes = self.fileSize
        super().setStatus(status, sync=sync)


@dataclass(kw_only=True)
class FtpTask(Task):
    packId: str = field(default="ftp")
    connectionInfo: FtpConnectionInfo | dict[str, Any]
    sourceType: str = field(default="file")
    files: list[FtpFile | dict[str, Any]] = field(default_factory=list)
    proxies: dict | None = field(default_factory=getProxies)
    blockNum: int = field(default_factory=lambda: cfg.preBlockNum.value)

    def __post_init__(self):
        if isinstance(self.connectionInfo, dict):
            self.connectionInfo = FtpConnectionInfo(**self.connectionInfo)
        self.files = [
            item if isinstance(item, FtpFile) else FtpFile(**item)
            for item in self.files
        ]
        self._filesByIndex = {file.index: file for file in self.files}
        self.title = toSafeFilename(self.title, fallback="ftp_download")
        super().__post_init__()
        self._recalculateSelection()
        self._syncFiles()
        self.updateStagePaths()

    @property
    def countAll(self) -> int:
        return len(self.files)

    @property
    def countSelected(self) -> int:
        return sum(1 for file in self.files if file.selected)

    @property
    def isDirectory(self) -> bool:
        return self.sourceType == "dir"

    @property
    def selectedStages(self) -> list["FtpStage"]:
        return [
            stage
            for stage in self.stages
            if self.fileByIndex(stage.fileIndex).selected
        ]

    def fileByIndex(self, index: int) -> FtpFile:
        return self._filesByIndex[index]

    def updateStagePaths(self):
        rootPath = Path(self.path) / self.title
        if not self.isDirectory:
            outputFile = str(rootPath)
            for stage in self.stages:
                stage.outputFile = outputFile
            return

        for stage in self.stages:
            file = self.fileByIndex(stage.fileIndex)
            stage.outputFile = str(
                rootPath / Path(*PurePosixPath(file.relativePath).parts)
            )

    def setTitle(self, title: str):
        self.title = toSafeFilename(title, fallback=self.title or "ftp_download")
        self.updateStagePaths()

    def _recalculateSelection(self):
        self.fileSize = sum(file.size for file in self.files if file.selected)

    def _syncFiles(self):
        stageByFileIndex = {stage.fileIndex: stage for stage in self.stages}

        for file in self.files:
            stage = stageByFileIndex[file.index]
            file.downloadedBytes = max(0, int(stage.receivedBytes))
            file.completed = stage.status == TaskStatus.COMPLETED
            if file.completed and file.size > 0:
                file.downloadedBytes = max(file.downloadedBytes, file.size)

    def setSelection(self, selectedIndexes: set[int]):
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
        self._syncFiles()
        self.updateStatus()

    def updateStatus(self) -> TaskStatus:
        self._syncFiles()
        selectedStages = self.selectedStages
        if not selectedStages:
            self.status = TaskStatus.WAITING
            return self.status

        stageStatus = [stage.status for stage in selectedStages]
        activeStatuses = {
            status for status in stageStatus if status != TaskStatus.COMPLETED
        }
        if TaskStatus.FAILED in activeStatuses:
            self.status = TaskStatus.FAILED
        elif not activeStatuses:
            self.status = TaskStatus.COMPLETED
        elif TaskStatus.RUNNING in activeStatuses:
            self.status = TaskStatus.RUNNING
        elif activeStatuses == {TaskStatus.PAUSED}:
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
                stage.reset(sync=False)
            stage.setStatus(status, sync=False)

        return self.updateStatus()

    def reset(self) -> TaskStatus:
        for file in self.files:
            file.downloadedBytes = 0
            file.completed = False
        for stage in self.stages:
            stage.reset(sync=False)
        return self.updateStatus()

    def reopen(self) -> bool:
        if self.status != TaskStatus.COMPLETED:
            return False

        pendingSelectedStages = [
            stage for stage in self.selectedStages if stage.status != TaskStatus.COMPLETED
        ]
        if not pendingSelectedStages:
            return False

        for stage in pendingSelectedStages:
            stage.setStatus(TaskStatus.PAUSED, sync=False)

        self._syncFiles()
        self.updateStatus()
        return True

    def applySettings(self, payload: dict[str, Any]):
        super().applySettings(payload)
        if "proxies" in payload:
            self.proxies = payload["proxies"]
        if "preBlockNum" in payload:
            self.blockNum = payload["preBlockNum"]
        self.updateStagePaths()

    def canPause(self) -> bool:
        selectedStages = self.selectedStages
        return bool(selectedStages) and all(stage.supportsRange for stage in selectedStages)

    def pendingStages(self):
        self.stages.sort(key=lambda stage: stage.stageIndex)
        for stage in self.selectedStages:
            if self.status != TaskStatus.RUNNING:
                break
            if stage.status == TaskStatus.COMPLETED:
                continue
            yield stage

    async def run(self):
        currentStage = None
        try:
            for stage in self.pendingStages():
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


@dataclass
class FtpSubworker:
    start: int
    progress: int
    end: int


class FtpWorker(Worker):
    def __init__(self, stage: FtpStage):
        super().__init__(stage)
        self.stage = stage
        self.task: FtpTask = stage._task
        self.speedHistory: list[int] = []
        self.accelCheckTime = 0.0
        self.subworkerTasks: set[asyncio.Task] = set()
        self._stopping = False

    def _closeTransfer(self, client: aioftp.Client | None, stream):
        with suppress(Exception):
            if stream is not None:
                stream.close()
        if client is not None:
            client.close()

    def _startSubworker(self, subworker: FtpSubworker):
        if self._stopping:
            return

        task = asyncio.create_task(self.handleSubworker(subworker))
        self.subworkerTasks.add(task)
        task.add_done_callback(self.subworkerTasks.discard)

    async def _stopSubworkers(self):
        if self._stopping:
            return

        self._stopping = True
        runningTasks = tuple(task for task in self.subworkerTasks if not task.done())

        for task in runningTasks:
            task.cancel()

        if not runningTasks:
            return

        done, pending = await asyncio.wait(runningTasks, timeout=5)
        for finishedTask in done:
            with suppress(Exception, CancelledError):
                finishedTask.result()

        if pending:
            logger.warning(
                "{} 仍有 {} 个 FTP 子任务未及时退出，已继续结束当前任务",
                self.stage.outputFile,
                len(pending),
            )

    def reassignSubworker(self):
        if self._stopping or self.task.status != TaskStatus.RUNNING or self.stage.fileSize <= 0:
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
        self._startSubworker(newSubworker)

    async def _downloadRange(self, subworker: FtpSubworker):
        client = None
        stream = None
        try:
            client = await _openClient(self.task.connectionInfo, self.task.proxies)
            stream = await client.download_stream(
                PurePosixPath(self.stage.remotePath),
                offset=subworker.progress,
            )

            remaining = subworker.end - subworker.progress + 1
            while remaining > 0:
                chunk = await stream.read(min(FTP_CHUNK_SIZE, remaining))
                if not chunk:
                    raise RuntimeError("FTP 数据流提前结束")
                chunkSize = len(chunk)

                await cfg.checkSpeedLimitation()
                pwrite(self.fileHandle, chunk, subworker.progress)
                subworker.progress += chunkSize
                remaining -= chunkSize
                cfg.globalSpeed += chunkSize
        finally:
            self._closeTransfer(client, stream)

    async def _downloadUnknown(self, subworker: FtpSubworker):
        client = None
        stream = None
        try:
            client = await _openClient(self.task.connectionInfo, self.task.proxies)
            stream = await client.download_stream(
                PurePosixPath(self.stage.remotePath),
                offset=subworker.progress,
            )

            while True:
                chunk = await stream.read(FTP_CHUNK_SIZE)
                if not chunk:
                    return
                chunkSize = len(chunk)

                await cfg.checkSpeedLimitation()
                pwrite(self.fileHandle, chunk, subworker.progress)
                subworker.progress += chunkSize
                cfg.globalSpeed += chunkSize
        finally:
            self._closeTransfer(client, stream)

    async def _downloadWholeFile(self, subworker: FtpSubworker):
        client = None
        stream = None
        try:
            client = await _openClient(self.task.connectionInfo, self.task.proxies)
            stream = await client.download_stream(PurePosixPath(self.stage.remotePath))

            ftruncate(self.fileHandle, 0)
            subworker.progress = 0

            while True:
                chunk = await stream.read(FTP_CHUNK_SIZE)
                if not chunk:
                    ftruncate(self.fileHandle, subworker.progress)
                    return
                chunkSize = len(chunk)

                await cfg.checkSpeedLimitation()
                pwrite(self.fileHandle, chunk, subworker.progress)
                subworker.progress += chunkSize
                cfg.globalSpeed += chunkSize
        finally:
            self._closeTransfer(client, stream)

    async def handleSubworker(self, subworker: FtpSubworker):
        if subworker.end == SpecialFileSize.UNKNOWN:
            while True:
                try:
                    await self._downloadUnknown(subworker)
                    return
                except Exception as e:
                    if self._stopping or self.task.status != TaskStatus.RUNNING:
                        raise CancelledError
                    logger.opt(exception=e).error(
                        "{} 的未知大小分片 {} 连接中断，5 秒后重试",
                        self.stage.outputFile,
                        subworker,
                    )
                    await asyncio.sleep(FTP_RETRY_DELAY)
        elif subworker.end == SpecialFileSize.NOT_SUPPORTED:
            while True:
                try:
                    await self._downloadWholeFile(subworker)
                    return
                except Exception as e:
                    if self._stopping or self.task.status != TaskStatus.RUNNING:
                        raise CancelledError
                    logger.opt(exception=e).error(
                        "{} 不支持断点续传，已从头开始重试",
                        self.stage.outputFile,
                    )
                    await asyncio.sleep(FTP_RETRY_DELAY)
        else:
            while subworker.progress <= subworker.end:
                try:
                    await self._downloadRange(subworker)
                    break
                except Exception as e:
                    if self._stopping or self.task.status != TaskStatus.RUNNING:
                        raise CancelledError
                    logger.opt(exception=e).error(
                        "{} 的分片 {} 连接中断，5 秒后重试",
                        self.stage.outputFile,
                        subworker,
                    )
                    await asyncio.sleep(FTP_RETRY_DELAY)

            if subworker.progress > subworker.end:
                subworker.progress = subworker.end + 1

            self.reassignSubworker()

    def _trySpeedUp(self):
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
            recordFileHandle = open(Path(self.stage.outputFile + ".ghd"), "wb")
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

                self._trySpeedUp()
                await asyncio.sleep(1)
        except CancelledError:
            logger.info(f"{self.stage.outputFile} 停止下载")
        except Exception as e:
            logger.opt(exception=e).error(
                "{} 的监控协程异常退出",
                self.stage.outputFile,
            )
        finally:
            if recordFileHandle is not None:
                recordFileHandle.close()

    def _restoreProgress(self) -> bool:
        recordFile = Path(self.stage.outputFile + ".ghd")
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
            logger.opt(exception=e).error("恢复 FTP 下载分片失败 {}", self.stage.outputFile)
            self.subworkers.clear()
            return False

    def _generateSubworkers(self):
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
        target = Path(self.stage.outputFile + ".ghd")
        try:
            if target.is_file() or target.is_symlink():
                target.unlink()
        except Exception as e:
            logger.opt(exception=e).error("failed to cleanup temporary file {}", target)

    async def run(self):
        self.subworkers: list[FtpSubworker] = []
        self.subworkerTasks.clear()
        self._stopping = False
        shouldCleanupRecordFile = False
        Path(self.stage.outputFile).parent.mkdir(parents=True, exist_ok=True)

        restored = False
        if self.stage.supportsRange:
            restored = self._restoreProgress()
        else:
            self._cleanupRecordFile()

        if not restored:
            logger.info("正在为 {} 生成 FTP 下载分片", self.stage.outputFile)
            self._generateSubworkers()
        else:
            logger.info("从进度文件恢复 FTP 下载分片 {}", self.stage.outputFile)

        openMode = os.O_RDWR | os.O_CREAT
        if not self.stage.supportsRange:
            openMode |= os.O_TRUNC
        self.fileHandle = os.open(self.stage.outputFile, openMode, 0o666)

        if not restored and self.stage.fileSize > 0:
            try:
                ftruncate(self.fileHandle, self.stage.fileSize)
            except Exception as e:
                logger.opt(exception=e).error("{} 预分配文件大小失败", self.stage.outputFile)

        supervisor = asyncio.create_task(self.supervisor())

        try:
            for subworker in self.subworkers:
                self._startSubworker(subworker)

            while self.subworkerTasks:
                currentTasks = tuple(self.subworkerTasks)
                done, _ = await asyncio.wait(
                    currentTasks,
                    return_when=asyncio.FIRST_EXCEPTION,
                )
                for finishedTask in done:
                    if finishedTask.cancelled():
                        raise CancelledError
                    exception = finishedTask.exception()
                    if exception is not None:
                        raise exception

            self.stage.setStatus(TaskStatus.COMPLETED)
            shouldCleanupRecordFile = True
            logger.info("{} 下载完成", self.stage.outputFile)
        except CancelledError:
            await self._stopSubworkers()
            self.stage.setStatus(TaskStatus.PAUSED)
            raise
        except Exception as e:
            await self._stopSubworkers()
            self.stage.setError(e)
            logger.opt(exception=e).error("{} 下载阶段失败", self.stage.outputFile)
            raise
        finally:
            if not supervisor.done():
                supervisor.cancel()
                with suppress(asyncio.CancelledError):
                    await supervisor
            self.subworkerTasks.clear()
            os.close(self.fileHandle)
            if shouldCleanupRecordFile:
                self._cleanupRecordFile()


async def _openClient(connectionInfo: FtpConnectionInfo, proxies: dict | None) -> aioftp.Client:
    scheme = connectionInfo.scheme.lower()
    if scheme != "ftps":
        attempts = [(connectionInfo.port, "plain")]
    elif not connectionInfo.portSpecified:
        attempts = [(FTP_DEFAULT_PORT, "explicit"), (FTPS_DEFAULT_PORT, "implicit")]
    elif connectionInfo.port == FTPS_DEFAULT_PORT:
        attempts = [(connectionInfo.port, "implicit")]
    else:
        attempts = [(connectionInfo.port, "explicit"), (connectionInfo.port, "implicit")]

    lastError: Exception | None = None

    for index, (port, mode) in enumerate(attempts):
        client = aioftp.Client(
            **_buildArgs(proxies),
            ssl=ssl.create_default_context() if mode == "implicit" else None,
        )
        try:
            await client.connect(connectionInfo.host, port)
            if mode == "explicit":
                await client.upgrade_to_tls()
            await client.login(connectionInfo.username, connectionInfo.password)
            return client
        except Exception as e:
            client.close()
            lastError = e
            if index < len(attempts) - 1:
                logger.info(
                    "{}://{}:{} 使用 {} TLS 连接失败，尝试下一种模式: {}",
                    connectionInfo.scheme.lower(),
                    connectionInfo.host,
                    port,
                    mode,
                    repr(e),
                )

    raise lastError or RuntimeError("无法建立 FTP 连接")



async def _supportsRange(client: aioftp.Client) -> bool:
    try:
        await client.command("TYPE I", "200")
        await client.command("REST 1", "350")
        return True
    except Exception as e:
        logger.info("FTP 服务器不支持 REST 断点续传: {}", repr(e))
        return False


async def resolve(payload: dict) -> FtpTask:
    url = str(payload["url"]).strip()
    parsedUrl = urlparse(url)
    scheme = parsedUrl.scheme.lower()
    if scheme not in {"ftp", "ftps"}:
        raise ValueError("不是有效的 FTP/FTPS 链接")
    if not parsedUrl.hostname:
        raise ValueError("FTP/FTPS 链接缺少主机名")

    sourcePath = PurePosixPath(unquote(parsedUrl.path or "/"))
    connectionInfo = FtpConnectionInfo(
        scheme=scheme,
        host=parsedUrl.hostname,
        port=parsedUrl.port or FTP_DEFAULT_PORT,
        username=unquote(parsedUrl.username or "anonymous"),
        password=unquote(parsedUrl.password or "anon@"),
        sourcePath=str(sourcePath),
        portSpecified=parsedUrl.port is not None,
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

        supportsRange = await _supportsRange(client)
        files: list[FtpFile] = []
        stages: list[FtpStage] = []

        if sourceType == "file":
            files.append(
                FtpFile(
                    index=0,
                    remotePath=str(sourcePath),
                    relativePath=sourcePath.name or "ftp_file",
                    size=_parseSize(sourceInfo.get("size")),
                )
            )
        else:
            entries = [item async for item in client.list(sourcePath, recursive=True)]
            index = 0
            for remotePath, info in entries:
                if info["type"] != "file":
                    continue
                files.append(
                    FtpFile(
                        index=index,
                        remotePath=str(remotePath),
                        relativePath=(str(remotePath.relative_to(sourcePath)) if sourcePath in remotePath.parents else remotePath.name),
                        size=_parseSize(info.get("size")),
                    )
                )
                index += 1

            if not files:
                raise ValueError("该 FTP 目录中没有可下载的普通文件")

        for file in files:
            stages.append(
                FtpStage(
                    stageIndex=len(stages) + 1,
                    fileIndex=file.index,
                    remotePath=file.remotePath,
                    fileSize=file.size,
                    outputFile="",
                    supportsRange=supportsRange,
                )
            )

        task = FtpTask(
            title=toSafeFilename(sourcePath.name, fallback="ftp_download") if sourcePath.name else toSafeFilename(connectionInfo.host, fallback="ftp_download"),
            url=url,
            fileSize=sum(file.size for file in files),
            path=path,
            stages=stages,
            connectionInfo=connectionInfo,
            sourceType=sourceType,
            files=files,
            proxies=proxies,
            blockNum=blockNum if isinstance(blockNum, int) else cfg.preBlockNum.value,
        )
        return task
    finally:
        if client is not None:
            try:
                await client.quit()
            except Exception:
                client.close()
