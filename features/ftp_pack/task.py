from __future__ import annotations

import asyncio
import os
import ssl
from asyncio import CancelledError
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from struct import pack, unpack
from urllib.parse import unquote, urlparse

import aioftp
from loguru import logger

from app.config.cfg import cfg
from app.models.task import Task, TaskError, TaskStep, TaskFile, TaskStatus, SpecialFileSize
from app.platform.filesystem import deletePath, toPosixPath
from app.platform.sysio import ftruncate, pwrite
FTP_CONNECTION_TIMEOUT = 15
FTP_SOCKET_TIMEOUT = 30
FTP_PATH_TIMEOUT = 30
FTP_RETRY_DELAY = 5
FTP_DEFAULT_PORT = 21
FTPS_DEFAULT_PORT = 990


@dataclass
class FtpConnectionInfo:
    scheme: str
    host: str
    port: int
    username: str
    password: str
    sourcePath: str
    hasPort: bool = False

    async def connect(self) -> aioftp.Client:
        from app.config.cfg import proxy

        scheme = self.scheme.lower()
        if scheme != "ftps":
            attempts = [(self.port, "plain")]
        elif not self.hasPort:
            attempts = [(FTP_DEFAULT_PORT, "explicit"), (FTPS_DEFAULT_PORT, "implicit")]
        elif self.port == FTPS_DEFAULT_PORT:
            attempts = [(self.port, "implicit")]
        else:
            attempts = [(self.port, "explicit"), (self.port, "implicit")]

        kwargs = {
            "connection_timeout": FTP_CONNECTION_TIMEOUT,
            "socket_timeout": FTP_SOCKET_TIMEOUT,
            "path_timeout": FTP_PATH_TIMEOUT,
        }

        url = proxy()
        if url:
            parsed = urlparse(url)
            if parsed.scheme in {"socks4", "socks5", "socks5h"} and parsed.hostname and parsed.port:
                kwargs.update({
                    "socks_host": parsed.hostname,
                    "socks_port": parsed.port,
                    "socks_version": 4 if parsed.scheme == "socks4" else 5,
                })
                if parsed.username:
                    kwargs["username"] = unquote(parsed.username)
                if parsed.password:
                    kwargs["password"] = unquote(parsed.password)

        lastError: Exception | None = None
        for index, (port, mode) in enumerate(attempts):
            client = aioftp.Client(
                **kwargs,
                ssl=ssl.create_default_context() if mode == "implicit" else None,
            )
            try:
                await client.connect(self.host, port)
                if mode == "explicit":
                    await client.upgrade_to_tls()
                await client.login(self.username, self.password)
                return client
            except Exception as e:
                client.close()
                lastError = e
                if index < len(attempts) - 1:
                    logger.info(
                        "{}://{}:{} 使用 {} TLS 连接失败，尝试下一种模式: {}",
                        scheme, self.host, port, mode, repr(e),
                    )

        raise TaskError("无法建立 FTP 连接") from lastError


@dataclass
class FtpSubworker:
    index: int
    start: int
    end: int
    receivedBytes: int = 0

    @property
    def position(self) -> int:
        return self.start + self.receivedBytes


@dataclass(kw_only=True)
class FtpFile(TaskFile):
    remotePath: str

    def __post_init__(self):
        self.remotePath = toPosixPath(self.remotePath)
        self.relativePath = toPosixPath(self.relativePath)


@dataclass(kw_only=True)
class FtpStep(TaskStep):
    fileIndex: int
    remotePath: str
    fileSize: int = 0
    canUseRangeRequests: bool = False
    isAccelerated: bool = False
    subworkerCount: int = 8

    @property
    def canPause(self) -> bool:
        return self.canUseRangeRequests

    @property
    def outputPath(self) -> str:
        task: FtpTask = self.task
        if self.fileIndex >= 0 and task.files and task.isFolder:
            for file in task.files:
                if file.index == self.fileIndex:
                    return toPosixPath(task.outputFolder / task.name / file.relativePath)
        return toPosixPath(task.outputFolder / task.name)

    def setOptions(self, options: dict) -> None:
        if "subworkerCount" in options:
            self.subworkerCount = options["subworkerCount"]

    def setStatus(self, status: TaskStatus):
        if status == TaskStatus.COMPLETED:
            self.receivedBytes = self.fileSize
        super().setStatus(status)

    @classmethod
    def fromFile(cls, file: TaskFile, task: Task) -> FtpStep:
        ftpFile: FtpFile = file
        return cls(
            stepIndex=file.index + 1,
            fileIndex=file.index,
            remotePath=ftpFile.remotePath,
            fileSize=file.size,
            canUseRangeRequests=True,
            subworkerCount=cfg.preBlockNum.value,
        )

    def _loadRecord(self) -> list[FtpSubworker]:
        recordPath = Path(self.outputPath + ".ghd")
        if not recordPath.exists():
            return []
        try:
            subworkers = []
            with open(recordPath, "rb") as f:
                index = 0
                while data := f.read(24):
                    start, position, end = unpack("<QQQ", data)
                    subworkers.append(FtpSubworker(
                        index=index, start=start, end=end,
                        receivedBytes=position - start,
                    ))
                    index += 1
            return subworkers
        except Exception as e:
            logger.opt(exception=e).error("恢复 FTP 下载分片失败 {}", self.outputPath)
            return []

    def _buildSubworkers(self) -> list[FtpSubworker]:
        if not self.canUseRangeRequests:
            return [FtpSubworker(index=0, start=0, end=SpecialFileSize.NOT_SUPPORTED)]

        if self.fileSize <= 0:
            return [FtpSubworker(index=0, start=0, end=SpecialFileSize.UNKNOWN)]

        count = min(self.subworkerCount, self.fileSize)
        chunkSize = self.fileSize // count
        if chunkSize <= 0:
            return [FtpSubworker(index=0, start=0, end=max(0, self.fileSize - 1))]

        subworkers = []
        start = 0
        for i in range(count - 1):
            end = start + chunkSize - 1
            subworkers.append(FtpSubworker(index=i, start=start, end=end))
            start = end + 1
        subworkers.append(FtpSubworker(index=count - 1, start=start, end=self.fileSize - 1))
        return subworkers

    def _deleteRecord(self) -> None:
        target = Path(self.outputPath + ".ghd")
        try:
            if target.is_file() or target.is_symlink():
                target.unlink()
        except Exception as e:
            logger.opt(exception=e).error("删除进度文件失败 {}", target)

    def _reassignSubworker(self) -> None:
        if self._stopping or self.task.status != TaskStatus.RUNNING or self.fileSize <= 0:
            return

        slowest = max(self._subworkers, key=lambda sw: sw.end - sw.position + 1)
        remainingBytes = slowest.end - slowest.position + 1
        if remainingBytes < cfg.maxReassignSize.value * 1024:
            return

        base = remainingBytes // 2
        remainder = remainingBytes % 2
        oldEnd = slowest.end
        slowest.end = slowest.position + base + remainder - 1

        newSubworker = FtpSubworker(
            index=len(self._subworkers),
            start=slowest.end + 1,
            end=oldEnd,
        )
        self._subworkers.insert(self._subworkers.index(slowest) + 1, newSubworker)
        self._startSubworkerTask(newSubworker)

    def _autoSpeedUp(self) -> None:
        if self.isAccelerated or not cfg.autoSpeedUp.value:
            return

        self._speedHistory.append(self.speed)
        if len(self._speedHistory) > 5:
            self._speedHistory.pop(0)
        if len(self._speedHistory) < 5:
            return

        avgSpeed = sum(self._speedHistory) / len(self._speedHistory)
        if avgSpeed == 0:
            return

        maxDeviation = max(abs(s - avgSpeed) / avgSpeed for s in self._speedHistory)
        if maxDeviation > 0.15:
            return

        if self._accelCheckTime == 0:
            self._accelInitialWorkers = len(self._subworkers)
            self._accelInitialSpeed = avgSpeed
            self._accelCheckTime = asyncio.get_event_loop().time()
            for _ in range(4):
                self._reassignSubworker()
        else:
            elapsed = asyncio.get_event_loop().time() - self._accelCheckTime
            if elapsed <= 5:
                return

            workerRatio = (len(self._subworkers) - self._accelInitialWorkers) / self._accelInitialWorkers
            speedRatio = (avgSpeed - self._accelInitialSpeed) / self._accelInitialSpeed

            if speedRatio < 0.8 * workerRatio:
                self.isAccelerated = True
                logger.info("自动加速已禁用，subworker 增加比: {:.2%}, 速度提升比: {:.2%}",
                            workerRatio, speedRatio)
            else:
                self._accelCheckTime = 0
                logger.info("继续自动加速，subworker 增加比: {:.2%}, 速度提升比: {:.2%}",
                            workerRatio, speedRatio)

    async def _supervise(self) -> None:
        recordFile = None
        if self.canUseRangeRequests:
            recordFile = open(self.outputPath + ".ghd", "wb")
        try:
            self.receivedBytes = sum(sw.receivedBytes for sw in self._subworkers)
            while True:
                if recordFile is not None:
                    data = tuple(
                        val for sw in self._subworkers
                        for val in (sw.start, sw.position, sw.end)
                    )
                    recordFile.seek(0)
                    recordFile.write(pack("<" + "Q" * len(data), *data))
                    recordFile.flush()
                    recordFile.truncate()

                receivedBytes = sum(sw.receivedBytes for sw in self._subworkers)
                self.speed = receivedBytes - self.receivedBytes
                self.receivedBytes = receivedBytes
                if self.fileSize > 0:
                    self.progress = (receivedBytes / self.fileSize) * 100
                else:
                    self.progress = 0

                self._autoSpeedUp()
                await asyncio.sleep(1)
        except CancelledError:
            pass
        finally:
            if recordFile is not None:
                recordFile.close()

    def _closeTransfer(self, client: aioftp.Client | None, stream):
        with suppress(Exception):
            if stream is not None:
                stream.close()
        if client is not None:
            client.close()

    async def _runSubworker(self, subworker: FtpSubworker, fd: int) -> None:
        ftpTask: FtpTask = self.task

        if subworker.end == SpecialFileSize.UNKNOWN:
            while True:
                client = None
                stream = None
                try:
                    client = await ftpTask.connectionInfo.connect()
                    stream = await client.download_stream(
                        PurePosixPath(self.remotePath),
                        offset=subworker.position,
                    )
                    while True:
                        chunk = await stream.read(65536)
                        if not chunk:
                            return
                        pwrite(fd, chunk, subworker.position)
                        subworker.receivedBytes += len(chunk)
                        self._reportSpeed(len(chunk))
                        await self._waitForSpeedLimit()
                except Exception as e:
                    if self._stopping or self.task.status != TaskStatus.RUNNING:
                        raise CancelledError
                    logger.opt(exception=e).error("{} 的未知大小分片连接中断，5 秒后重试", self.outputPath)
                    await asyncio.sleep(FTP_RETRY_DELAY)
                finally:
                    self._closeTransfer(client, stream)

        elif subworker.end == SpecialFileSize.NOT_SUPPORTED:
            while True:
                client = None
                stream = None
                try:
                    client = await ftpTask.connectionInfo.connect()
                    stream = await client.download_stream(PurePosixPath(self.remotePath))
                    ftruncate(fd, 0)
                    subworker.receivedBytes = 0
                    while True:
                        chunk = await stream.read(65536)
                        if not chunk:
                            ftruncate(fd, subworker.receivedBytes)
                            return
                        pwrite(fd, chunk, subworker.receivedBytes)
                        subworker.receivedBytes += len(chunk)
                        self._reportSpeed(len(chunk))
                        await self._waitForSpeedLimit()
                except Exception as e:
                    if self._stopping or self.task.status != TaskStatus.RUNNING:
                        raise CancelledError
                    logger.opt(exception=e).error("{} 不支持断点续传，已从头开始重试", self.outputPath)
                    await asyncio.sleep(FTP_RETRY_DELAY)
                finally:
                    self._closeTransfer(client, stream)

        else:
            while subworker.position <= subworker.end:
                client = None
                stream = None
                try:
                    client = await ftpTask.connectionInfo.connect()
                    stream = await client.download_stream(
                        PurePosixPath(self.remotePath),
                        offset=subworker.position,
                    )
                    remaining = subworker.end - subworker.position + 1
                    while remaining > 0:
                        chunk = await stream.read(min(65536, remaining))
                        if not chunk:
                            raise RuntimeError("FTP 数据流提前结束")
                        pwrite(fd, chunk, subworker.position)
                        chunkSize = len(chunk)
                        subworker.receivedBytes += chunkSize
                        remaining -= chunkSize
                        self._reportSpeed(chunkSize)
                        await self._waitForSpeedLimit()
                    break
                except Exception as e:
                    if self._stopping or self.task.status != TaskStatus.RUNNING:
                        raise CancelledError
                    logger.opt(exception=e).error("{} 的分片连接中断，5 秒后重试", self.outputPath)
                    await asyncio.sleep(FTP_RETRY_DELAY)
                finally:
                    self._closeTransfer(client, stream)

            if subworker.position > subworker.end:
                subworker.receivedBytes = subworker.end - subworker.start + 1

            self._reassignSubworker()

    def _startSubworkerTask(self, subworker: FtpSubworker):
        if self._stopping:
            return
        task = asyncio.create_task(self._runSubworker(subworker, self._fd))
        self._subworkerTasks.add(task)
        task.add_done_callback(self._subworkerTasks.discard)

    async def _stopSubworkerTasks(self):
        if self._stopping:
            return
        self._stopping = True
        running = tuple(t for t in self._subworkerTasks if not t.done())
        for t in running:
            t.cancel()
        if running:
            done, _ = await asyncio.wait(running, timeout=5)
            for t in done:
                with suppress(Exception, CancelledError):
                    t.result()

    async def run(self, reportSpeed, waitForSpeedLimit) -> None:
        self._reportSpeed = reportSpeed
        self._waitForSpeedLimit = waitForSpeedLimit
        self._subworkers: list[FtpSubworker] = []
        self._subworkerTasks: set[asyncio.Task] = set()
        self._speedHistory: list[int] = []
        self._accelCheckTime = 0.0
        self._stopping = False
        shouldDeleteRecord = False

        Path(self.outputPath).parent.mkdir(parents=True, exist_ok=True)

        restored = False
        if self.canUseRangeRequests:
            loaded = self._loadRecord()
            if loaded:
                self._subworkers = loaded
                restored = True

        if not restored:
            if not self.canUseRangeRequests:
                self._deleteRecord()
            self._subworkers = self._buildSubworkers()

        openMode = os.O_RDWR | os.O_CREAT
        if not self.canUseRangeRequests:
            openMode |= os.O_TRUNC
        self._fd = os.open(self.outputPath, openMode, 0o666)

        if not restored and self.fileSize > 0:
            try:
                ftruncate(self._fd, self.fileSize)
            except Exception as e:
                logger.opt(exception=e).error("{} 预分配文件大小失败", self.outputPath)

        supervisor = asyncio.create_task(self._supervise())

        try:
            for subworker in self._subworkers:
                self._startSubworkerTask(subworker)

            while self._subworkerTasks:
                currentTasks = tuple(self._subworkerTasks)
                done, _ = await asyncio.wait(currentTasks, return_when=asyncio.FIRST_EXCEPTION)
                for finished in done:
                    if finished.cancelled():
                        raise CancelledError
                    exc = finished.exception()
                    if exc is not None:
                        raise exc

            self.setStatus(TaskStatus.COMPLETED)
            shouldDeleteRecord = True
        except CancelledError:
            await self._stopSubworkerTasks()
            self.setStatus(TaskStatus.PAUSED)
            raise
        except Exception:
            await self._stopSubworkerTasks()
            raise
        finally:
            if not supervisor.done():
                supervisor.cancel()
                with suppress(CancelledError):
                    await supervisor
            self._subworkerTasks.clear()
            os.close(self._fd)
            if shouldDeleteRecord:
                self._deleteRecord()


@dataclass(kw_only=True, eq=False)
class FtpTask(Task):
    packId: str = "ftp"
    canEdit = True
    fileType = FtpFile
    connectionInfo: FtpConnectionInfo
    sourceType: str = "file"

    def __post_init__(self):
        if isinstance(self.connectionInfo, dict):
            self.connectionInfo = FtpConnectionInfo(**self.connectionInfo)
        super().__post_init__()
        # 旧存档中被取消勾选的文件没有 Step，按 files 补建
        if self.files:
            existing = {getattr(s, "fileIndex", None) for s in self.steps}
            for file in self.files:
                if file.index not in existing:
                    self.addStep(FtpStep.fromFile(file, self))

    @property
    def isFolder(self) -> bool:
        return self.sourceType == "dir"

    @property
    def countSelected(self) -> int:
        return sum(1 for file in self.files if file.selected)

    def deleteFiles(self):
        if self.isFolder:
            deletePath(Path(self.outputPath))
            return
        for step in self.steps:
            target = Path(step.outputPath)
            deletePath(target)
            deletePath(Path(f"{target}.ghd"))

