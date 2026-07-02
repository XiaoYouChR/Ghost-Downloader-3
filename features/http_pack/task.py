from __future__ import annotations

import asyncio
import os
from asyncio import TaskGroup, CancelledError
from contextlib import suppress
from dataclasses import field, dataclass
from pathlib import Path
from struct import unpack, pack

from loguru import logger

from app.client import buildClient, toEmulation
from app.config.cfg import cfg
from app.models.task import Task, TaskError, TaskStep, TaskStatus, SpecialFileSize
from app.platform.sysio import ftruncate, pwrite
from app.services.speed_meter import speedMeter


PERMANENT_STATUS = frozenset({400, 401, 403, 404, 405, 410, 451})


class PermanentDownloadError(Exception):
    def __init__(self, status: int):
        super().__init__(f"HTTP {status}")
        self.status = status


@dataclass
class HttpSubworker:
    index: int
    start: int
    end: int
    receivedBytes: int = 0

    @property
    def position(self) -> int:
        return self.start + self.receivedBytes


@dataclass(kw_only=True, eq=False)
class HttpTask(Task):
    packId: str = "http"
    canEdit = True

    def canReuseProgress(self, newTask: Task) -> bool:
        return (
            isinstance(newTask, HttpTask)
            and self.fileSize > 0
            and self.fileSize == newTask.fileSize
        )


@dataclass(kw_only=True)
class HttpTaskStep(TaskStep):
    url: str = ""
    fileSize: int = 0
    headers: dict[str, str] = field(default_factory=dict)
    clientProfile: str = ""
    subworkerCount: int = 8
    canUseRangeRequests: bool = False
    lastModified: str = ""
    isAccelerated: bool = False
    outputFile: str = ""
    subworkers: list[HttpSubworker] = field(default_factory=list, repr=False)

    def __post_init__(self):
        self.canPause = self.canUseRangeRequests

    def deleteFiles(self):
        from app.platform.filesystem import deletePath
        path = Path(self.outputPath)
        deletePath(path)
        deletePath(Path(f"{path}.ghd"))

    def setOptions(self, options: dict) -> None:
        if "headers" in options:
            self.headers = options["headers"]
        if "clientProfile" in options:
            self.clientProfile = options["clientProfile"]
        if "subworkerCount" in options:
            self.subworkerCount = options["subworkerCount"]

    @property
    def outputPath(self) -> str:
        if self.outputFile:
            return self.outputFile
        return str(self.task.outputFolder / self.task.name)

    def _loadRecord(self) -> list[HttpSubworker]:
        recordPath = Path(self.outputPath + ".ghd")
        if not recordPath.exists():
            return []
        try:
            subworkers = []
            with open(recordPath, "rb") as f:
                index = 0
                while data := f.read(24):
                    start, position, end = unpack("<QQQ", data)
                    subworkers.append(HttpSubworker(
                        index=index, start=start, end=end,
                        receivedBytes=position - start,
                    ))
                    index += 1
            return subworkers
        except Exception as e:
            logger.opt(exception=e).error("恢复下载分片失败 {}", self.outputPath)
            return []

    def _buildSubworkers(self) -> list[HttpSubworker]:
        if not self.canUseRangeRequests:
            return [HttpSubworker(index=0, start=0, end=SpecialFileSize.NOT_SUPPORTED)]

        if self.fileSize == SpecialFileSize.UNKNOWN:
            return [HttpSubworker(index=0, start=0, end=SpecialFileSize.UNKNOWN)]

        count = min(self.subworkerCount, self.fileSize)
        chunkSize = self.fileSize // count
        subworkers = []
        start = 0
        for i in range(count - 1):
            end = start + chunkSize - 1
            subworkers.append(HttpSubworker(index=i, start=start, end=end))
            start = end + 1
        subworkers.append(HttpSubworker(index=count - 1, start=start, end=self.fileSize - 1))
        return subworkers

    def _deleteRecord(self) -> None:
        target = Path(self.outputPath + ".ghd")
        try:
            if target.is_file() or target.is_symlink():
                target.unlink()
        except Exception as e:
            logger.opt(exception=e).error("删除进度文件失败 {}", target)

    def _reassignSubworker(self) -> None:
        if self.fileSize <= 0:
            return

        slowest = max(self.subworkers, key=lambda sw: sw.end - sw.position + 1)
        remainingBytes = slowest.end - slowest.position + 1
        if remainingBytes < cfg.maxReassignSize.value * 1024:
            return

        base = remainingBytes // 2
        remainder = remainingBytes % 2
        oldEnd = slowest.end
        slowest.end = slowest.position + base + remainder - 1

        newSubworker = HttpSubworker(
            index=len(self.subworkers),
            start=slowest.end + 1,
            end=oldEnd,
        )
        self.subworkers.insert(self.subworkers.index(slowest) + 1, newSubworker)
        self._taskGroup.create_task(self._runSubworker(newSubworker, self._fd))

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
            self._accelInitialWorkers = len(self.subworkers)
            self._accelInitialSpeed = avgSpeed
            self._accelCheckTime = asyncio.get_event_loop().time()
            for _ in range(4):
                self._reassignSubworker()
        else:
            elapsed = asyncio.get_event_loop().time() - self._accelCheckTime
            if elapsed <= 5:
                return

            workerRatio = (len(self.subworkers) - self._accelInitialWorkers) / self._accelInitialWorkers
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
            self.receivedBytes = sum(sw.receivedBytes for sw in self.subworkers)
            while True:
                if recordFile is not None:
                    data = tuple(
                        val for sw in self.subworkers
                        for val in (sw.start, sw.position, sw.end)
                    )
                    recordFile.seek(0)
                    recordFile.write(pack("<" + "Q" * len(data), *data))
                    recordFile.flush()
                    recordFile.truncate()

                receivedBytes = sum(sw.receivedBytes for sw in self.subworkers)
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

    async def _runSubworker(self, subworker: HttpSubworker, fd: int) -> None:
        if subworker.end == SpecialFileSize.UNKNOWN:
            while True:
                try:
                    headers = {**self.headers, "range": f"bytes={subworker.position}-", "accept-encoding": "identity"}
                    response = await self._client.get(self.url, headers=headers)
                    try:
                        status = response.status.as_int()
                        if status in PERMANENT_STATUS or response.headers.contains_key("cf-mitigated"):
                            raise PermanentDownloadError(status)
                        if status != 206:
                            raise Exception(f"服务器拒绝了范围请求，状态码：{status}")
                        async for chunk in response.stream():
                            if not chunk:
                                continue
                            pwrite(fd, chunk, subworker.position)
                            subworker.receivedBytes += len(chunk)
                            speedMeter.addSpeed(len(chunk))
                            await speedMeter.waitForSpeedLimit()
                    finally:
                        response.close()
                    return
                except CancelledError:
                    raise
                except PermanentDownloadError:
                    raise
                except Exception as e:
                    logger.opt(exception=e).error("下载分片失败，将在 5 秒后重试 {}", self.outputPath)
                    await asyncio.sleep(5)

        elif subworker.end == SpecialFileSize.NOT_SUPPORTED:
            while True:
                try:
                    ftruncate(fd, 0)
                    subworker.receivedBytes = 0
                    response = await self._client.get(self.url, headers=dict(self.headers))
                    try:
                        status = response.status.as_int()
                        if status in PERMANENT_STATUS or response.headers.contains_key("cf-mitigated"):
                            raise PermanentDownloadError(status)
                        if status != 200:
                            raise Exception(f"服务器返回了异常状态码：{status}")
                        async for chunk in response.stream():
                            if not chunk:
                                continue
                            pwrite(fd, chunk, subworker.receivedBytes)
                            subworker.receivedBytes += len(chunk)
                            speedMeter.addSpeed(len(chunk))
                            await speedMeter.waitForSpeedLimit()
                    finally:
                        response.close()
                    ftruncate(fd, subworker.receivedBytes)
                    return
                except CancelledError:
                    raise
                except PermanentDownloadError:
                    raise
                except Exception as e:
                    logger.opt(exception=e).error("下载分片失败，将在 5 秒后重试 {}", self.outputPath)
                    await asyncio.sleep(5)

        else:
            while subworker.position <= subworker.end:
                try:
                    headers = {
                        **self.headers,
                        "range": f"bytes={subworker.position}-{subworker.end}",
                        "accept-encoding": "identity",
                    }
                    response = await self._client.get(self.url, headers=headers)
                    try:
                        status = response.status.as_int()
                        if status in PERMANENT_STATUS or response.headers.contains_key("cf-mitigated"):
                            raise PermanentDownloadError(status)
                        if status != 206:
                            raise Exception(f"服务器拒绝了范围请求，状态码：{status}")
                        async for chunk in response.stream():
                            if not chunk:
                                continue
                            remaining = subworker.end - subworker.position + 1
                            if len(chunk) > remaining:
                                chunk = chunk[:remaining]
                            pwrite(fd, chunk, subworker.position)
                            subworker.receivedBytes += len(chunk)
                            speedMeter.addSpeed(len(chunk))
                            await speedMeter.waitForSpeedLimit()
                            if subworker.position > subworker.end:
                                break
                    finally:
                        response.close()

                    if subworker.position > subworker.end:
                        subworker.receivedBytes = subworker.end - subworker.start + 1

                except CancelledError:
                    raise
                except PermanentDownloadError:
                    raise
                except Exception as e:
                    logger.opt(exception=e).error("下载分片失败，将在 5 秒后重试 {}", self.outputPath)
                    await asyncio.sleep(5)

            self._reassignSubworker()

    async def run(self) -> None:
        self._taskGroup = TaskGroup()
        self._speedHistory: list[int] = []
        self._accelCheckTime = 0
        self.subworkers = []
        shouldDeleteRecord = False

        Path(self.outputPath).parent.mkdir(parents=True, exist_ok=True)

        emulation = toEmulation(self.clientProfile or cfg.clientProfile.value, "")
        self._client = buildClient(emulation=emulation)

        restored = False
        if self.canUseRangeRequests:
            loaded = self._loadRecord()
            if loaded:
                self.subworkers = loaded
                restored = True

        if not restored:
            if not self.canUseRangeRequests:
                self._deleteRecord()
            self.subworkers = self._buildSubworkers()

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
            async with self._taskGroup:
                for subworker in self.subworkers:
                    self._taskGroup.create_task(self._runSubworker(subworker, self._fd))

            self.setStatus(TaskStatus.COMPLETED)
            shouldDeleteRecord = True
        except CancelledError:
            self.setStatus(TaskStatus.PAUSED)
            raise
        except ExceptionGroup as eg:
            cause = eg.exceptions[0]
            if isinstance(cause, PermanentDownloadError):
                raise TaskError("Server returned error ({status})", status=cause.status) from eg
            raise cause from eg
        finally:
            if not supervisor.done():
                supervisor.cancel()
                with suppress(CancelledError):
                    await supervisor
            os.close(self._fd)
            self._client.close()
            if shouldDeleteRecord:
                self._deleteRecord()
                if cfg.shouldPreserveLastModified.value and self.lastModified:
                    try:
                        from email.utils import parsedate_to_datetime
                        mtime = parsedate_to_datetime(self.lastModified).timestamp()
                        os.utime(self.outputPath, (mtime, mtime))
                    except Exception as e:
                        logger.opt(exception=e).warning("设置文件修改时间失败 {}", self.outputPath)
