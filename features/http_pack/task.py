from __future__ import annotations

import asyncio
import errno
import os
import sys
from asyncio import TaskGroup, CancelledError
from contextlib import suppress
from dataclasses import field, dataclass
from pathlib import Path
from struct import unpack, pack

from loguru import logger
from wreq import HeaderMap

from app.client import buildClient, toEmulation
from app.config.cfg import cfg
from app.models.task import Task, TaskError, TaskStep, TaskStatus, SpecialFileSize
from app.platform.sysio import ftruncate, pwrite

STREAM_READ_TIMEOUT = 30
PERMANENT_STATUS = frozenset({400, 401, 403, 404, 405, 410, 451})
FATAL_IO_ERRNO = frozenset({errno.ENOSPC, errno.EDQUOT, errno.EROFS, errno.EIO})


class PermanentDownloadError(Exception):
    def __init__(self, status: int):
        super().__init__(f"HTTP {status}")
        self.status = status


class RangeNotSupportedError(Exception):
    pass


def matchRange(contentRange: bytes, start: int, end: int, total: int | None) -> bool:
    """RFC 9110 §14.4"""
    unit, _, spec = contentRange.strip().partition(b" ")
    span, _, size = spec.partition(b"/")
    first, _, last = span.partition(b"-")
    if unit.lower() != b"bytes" or not (first.isdigit() and last.isdigit() and size.isdigit()):
        return False
    return int(first) == start and start <= int(last) <= end and total in {None, int(size)}


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
    userAgent: str = ""
    subworkerCount: int = 8
    canUseRangeRequests: bool = False
    httpByteOffset: int = 0
    lastModified: str = ""
    isAccelerated: bool = False
    subworkers: list[HttpSubworker] = field(default_factory=list, repr=False)

    @property
    def canPause(self) -> bool:
        return self.canUseRangeRequests

    def setOptions(self, options: dict) -> None:
        if "headers" in options:
            self.headers = options["headers"]
        if "clientProfile" in options:
            self.clientProfile = options["clientProfile"]
        if "userAgent" in options:
            self.userAgent = options["userAgent"]
        if "subworkerCount" in options:
            self.subworkerCount = options["subworkerCount"]

    @property
    def outputPath(self) -> str:
        return self.task.outputPath

    @property
    def recordPath(self) -> Path:
        return Path(f"{self.outputPath}.ghd")

    def _loadRecord(self) -> list[HttpSubworker]:
        if not self.recordPath.exists():
            return []
        try:
            subworkers = []
            with open(self.recordPath, "rb") as f:
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

        # 其余分片待首个响应到达后再拆分
        return [HttpSubworker(index=0, start=0, end=self.fileSize - 1)]

    def _deleteRecord(self) -> None:
        try:
            if self.recordPath.is_file() or self.recordPath.is_symlink():
                self.recordPath.unlink()
        except Exception as e:
            logger.opt(exception=e).error("删除进度文件失败 {}", self.recordPath)

    def _splitSlowest(self, count: int = 2) -> list[HttpSubworker]:
        slowest = max(self.subworkers, key=lambda sw: sw.end - sw.position + 1)
        remainingBytes = slowest.end - slowest.position + 1
        count = min(count, remainingBytes)
        if count < 2:
            return []

        base, remainder = divmod(remainingBytes, count)
        oldEnd = slowest.end
        slowest.end = slowest.position + base + remainder - 1

        newSubworkers = []
        start = slowest.end + 1
        for _ in range(count - 1):
            newSubworkers.append(HttpSubworker(index=len(self.subworkers) + len(newSubworkers), start=start, end=start + base - 1))
            start += base
        newSubworkers[-1].end = oldEnd
        index = self.subworkers.index(slowest) + 1
        self.subworkers[index:index] = newSubworkers
        return newSubworkers

    def _emptyRightOf(self, subworker: HttpSubworker) -> HttpSubworker | None:
        """右侧分片尚未收到数据时返回它。"""
        index = self.subworkers.index(subworker) + 1
        if index < len(self.subworkers) and not self.subworkers[index].receivedBytes:
            return self.subworkers[index]
        return None

    def _reassignSubworker(self) -> None:
        if self.fileSize <= 0:
            return
        slowest = max(self.subworkers, key=lambda sw: sw.end - sw.position + 1)
        if slowest.end - slowest.position + 1 < cfg.maxReassignSize.value * 1024:
            return
        for newSw in self._splitSlowest():
            self._taskGroup.create_task(self._runSubworker(newSw, self._fd))

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
            self._accelCheckTime = asyncio.get_running_loop().time()
            for _ in range(4):
                self._reassignSubworker()
        else:
            elapsed = asyncio.get_running_loop().time() - self._accelCheckTime
            if elapsed <= 5:
                return

            workerRatio = (len(self.subworkers) - self._accelInitialWorkers) / self._accelInitialWorkers
            speedRatio = (avgSpeed - self._accelInitialSpeed) / self._accelInitialSpeed

            # 新分片均被拒绝时，同样视为加速无效
            if workerRatio <= 0 or speedRatio < 0.8 * workerRatio:
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
            recordFile = open(self.recordPath, "wb")
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
                client = buildClient(emulation=self._emulation, userAgent=self.userAgent or None, readTimeout=STREAM_READ_TIMEOUT)
                try:
                    httpPos = self.httpByteOffset + subworker.position
                    headers = {**self._effectiveHeaders, "range": f"bytes={httpPos}-", "accept-encoding": "identity"}
                    response = await client.get(self._effectiveUrl, headers=headers)
                    try:
                        status = response.status.as_int()
                        if status in PERMANENT_STATUS or response.headers.contains_key("cf-mitigated"):
                            raise PermanentDownloadError(status)
                        if status == 200:
                            raise RangeNotSupportedError()
                        if status != 206:
                            raise Exception(f"服务器拒绝了范围请求，状态码：{status}")
                        async for chunk in response.stream():
                            # 服务器发送 HTTP trailer 时，wreq 在流末尾以 HeaderMap 交出
                            if isinstance(chunk, HeaderMap) or not chunk:
                                continue
                            pwrite(fd, chunk, subworker.position)
                            subworker.receivedBytes += len(chunk)
                            self._reportSpeed(len(chunk))
                            await self._waitForSpeedLimit()
                    finally:
                        response.close()
                    return
                except CancelledError:
                    raise
                except (PermanentDownloadError, RangeNotSupportedError):
                    raise
                except Exception as e:
                    if isinstance(e, OSError) and e.errno in FATAL_IO_ERRNO:
                        raise
                    logger.opt(exception=e).error("下载分片失败，将在 5 秒后重试 {}", self.outputPath)
                    await asyncio.sleep(5)
                finally:
                    client.close()

        elif subworker.end == SpecialFileSize.NOT_SUPPORTED:
            while True:
                client = buildClient(emulation=self._emulation, userAgent=self.userAgent or None, readTimeout=STREAM_READ_TIMEOUT)
                try:
                    ftruncate(fd, 0)
                    subworker.receivedBytes = 0
                    response = await client.get(self._effectiveUrl, headers=dict(self._effectiveHeaders))
                    try:
                        status = response.status.as_int()
                        if status in PERMANENT_STATUS or response.headers.contains_key("cf-mitigated"):
                            raise PermanentDownloadError(status)
                        if status != 200:
                            raise Exception(f"服务器返回了异常状态码：{status}")
                        async for chunk in response.stream():
                            if isinstance(chunk, HeaderMap) or not chunk:
                                continue
                            pwrite(fd, chunk, subworker.receivedBytes)
                            subworker.receivedBytes += len(chunk)
                            self._reportSpeed(len(chunk))
                            await self._waitForSpeedLimit()
                    finally:
                        response.close()
                    ftruncate(fd, subworker.receivedBytes)
                    return
                except CancelledError:
                    raise
                except PermanentDownloadError:
                    raise
                except Exception as e:
                    if isinstance(e, OSError) and e.errno in FATAL_IO_ERRNO:
                        raise
                    logger.opt(exception=e).error("下载分片失败，将在 5 秒后重试 {}", self.outputPath)
                    await asyncio.sleep(5)
                finally:
                    client.close()

        else:
            while True:
                # 已被左侧分片并入
                if subworker not in self.subworkers:
                    return
                while subworker.end < subworker.position and (right := self._emptyRightOf(subworker)):
                    subworker.end = right.end
                    self.subworkers.remove(right)
                if subworker.position > subworker.end:
                    break
                client = buildClient(emulation=self._emulation, userAgent=self.userAgent or None, readTimeout=STREAM_READ_TIMEOUT)
                try:
                    # https://github.com/XiaoYouChR/Ghost-Downloader-3/issues/888
                    shouldConfirmFileSize = isinstance(self.task, HttpTask) and self.subworkers == [subworker] and subworker.position == 0
                    httpPos = self.httpByteOffset + subworker.position
                    # 请求至 Step 末尾，以便直接并入右侧分片
                    httpEnd = self.httpByteOffset + self.fileSize - 1
                    headers = {**self._effectiveHeaders, "accept-encoding": "identity"}
                    if not shouldConfirmFileSize:
                        headers["range"] = f"bytes={httpPos}-{httpEnd}"
                    response = await client.get(self._effectiveUrl, headers=headers)
                    try:
                        status = response.status.as_int()
                        if status in PERMANENT_STATUS or response.headers.contains_key("cf-mitigated"):
                            raise PermanentDownloadError(status)
                        if shouldConfirmFileSize:
                            if status != 200:
                                raise Exception(f"服务器返回了异常状态码：{status}")
                            length = bytes(response.headers.get("content-length") or b"")
                            if length.isdigit():
                                self.fileSize = self.task.fileSize = int(length)
                                subworker.end = self.fileSize - 1
                                ftruncate(fd, self.fileSize)
                            else:
                                # 缺少 Content-Length 时无法校验 Range
                                self.canUseRangeRequests = False
                                self.fileSize = self.task.fileSize = SpecialFileSize.UNKNOWN
                                subworker.end = sys.maxsize
                        else:
                            if status == 200:
                                raise RangeNotSupportedError()
                            if status != 206:
                                raise Exception(f"服务器拒绝了范围请求，状态码：{status}")
                            total = self.fileSize if isinstance(self.task, HttpTask) else None
                            if not matchRange(bytes(response.headers.get("content-range") or b""), httpPos, httpEnd, total):
                                raise RangeNotSupportedError()
                        self._effectiveUrl = str(response.url)
                        if len(self.subworkers) == 1 and self.canUseRangeRequests:
                            for newSw in self._splitSlowest(self.subworkerCount):
                                self._taskGroup.create_task(self._runSubworker(newSw, fd))
                        async for chunk in response.stream():
                            if isinstance(chunk, HeaderMap) or not chunk:
                                continue
                            if not subworker.receivedBytes and subworker not in self.subworkers:
                                return
                            while subworker.end < subworker.position + len(chunk) and (right := self._emptyRightOf(subworker)):
                                subworker.end = right.end
                                self.subworkers.remove(right)
                            remaining = subworker.end - subworker.position + 1
                            if len(chunk) > remaining:
                                chunk = chunk[:remaining]
                            pwrite(fd, chunk, subworker.position)
                            subworker.receivedBytes += len(chunk)
                            self._reportSpeed(len(chunk))
                            await self._waitForSpeedLimit()
                            if subworker.position > subworker.end:
                                break
                    finally:
                        response.close()

                    if not self.canUseRangeRequests:
                        ftruncate(fd, subworker.position)
                        return
                    if subworker.position > subworker.end:
                        subworker.receivedBytes = subworker.end - subworker.start + 1

                except CancelledError:
                    raise
                except (PermanentDownloadError, RangeNotSupportedError):
                    raise
                except Exception as e:
                    if isinstance(e, OSError) and e.errno in FATAL_IO_ERRNO:
                        raise
                    if not self.canUseRangeRequests:
                        raise RangeNotSupportedError() from e
                    # 服务器限流时仅拒绝新连接，尚未收到数据的分片留待左侧分片并入
                    if not subworker.receivedBytes and self.subworkers[0] is not subworker:
                        logger.info("分片请求失败，留待左侧分片并入 {}: {}", self.outputPath, e)
                        return
                    logger.opt(exception=e).error("下载分片失败，将在 5 秒后重试 {}", self.outputPath)
                    await asyncio.sleep(5)
                finally:
                    client.close()

            self._reassignSubworker()

    async def run(self, reportSpeed, waitForSpeedLimit) -> None:
        self._reportSpeed = reportSpeed
        self._waitForSpeedLimit = waitForSpeedLimit
        self._speedHistory: list[int] = []
        self._accelCheckTime = 0
        shouldDeleteRecord = False

        self._effectiveHeaders = {**self.headers}
        if self.userAgent and not any(k.lower() == "user-agent" for k in self.headers):
            self._effectiveHeaders["user-agent"] = self.userAgent

        self._emulation = toEmulation(self.clientProfile or cfg.clientProfile.value, "")
        self._effectiveUrl = self.url

        self.subworkers = self._loadRecord() if self.canUseRangeRequests else []
        isResuming = bool(self.subworkers)
        if not isResuming:
            self._deleteRecord()
            self.subworkers = self._buildSubworkers()

        openMode = os.O_RDWR | os.O_CREAT
        if not self.canUseRangeRequests:
            openMode |= os.O_TRUNC
        self._fd = os.open(self.outputPath, openMode, 0o666)

        if not isResuming and self.fileSize > 0:
            try:
                ftruncate(self._fd, self.fileSize)
            except Exception as e:
                logger.opt(exception=e).error("{} 预分配文件大小失败", self.outputPath)

        try:
            while True:
                supervisor = asyncio.create_task(self._supervise())
                try:
                    self._taskGroup = TaskGroup()
                    async with self._taskGroup:
                        for subworker in list(self.subworkers):
                            self._taskGroup.create_task(self._runSubworker(subworker, self._fd))
                        if isResuming:
                            for newSw in self._splitSlowest(self.subworkerCount - len(self.subworkers) + 1):
                                self._taskGroup.create_task(self._runSubworker(newSw, self._fd))

                    shouldDeleteRecord = True
                    break
                except CancelledError:
                    self.setStatus(TaskStatus.PAUSED)
                    raise
                except ExceptionGroup as eg:
                    if any(isinstance(e, RangeNotSupportedError) for e in eg.exceptions):
                        if isResuming:
                            # https://github.com/XiaoYouChR/Ghost-Downloader-3/issues/377
                            logger.warning("续传的范围对不上，重新下载 {}", self.outputPath)
                            isResuming = False
                        else:
                            logger.warning("服务器不支持范围请求，降级为单流下载 {}", self.outputPath)
                            self.canUseRangeRequests = False
                        self.subworkers = self._buildSubworkers()
                        ftruncate(self._fd, 0)
                        self._deleteRecord()
                        self._speedHistory.clear()
                        self._accelCheckTime = 0
                        continue

                    cause = eg.exceptions[0]
                    if isinstance(cause, PermanentDownloadError):
                        raise TaskError("服务器返回了错误（{status}）", status=cause.status) from eg
                    if isinstance(cause, OSError) and cause.errno in FATAL_IO_ERRNO:
                        raise TaskError("磁盘空间不足") from eg
                    raise cause from eg
                finally:
                    if not supervisor.done():
                        supervisor.cancel()
                        with suppress(CancelledError):
                            await supervisor
        finally:
            os.close(self._fd)
            if shouldDeleteRecord:
                self._deleteRecord()
                if cfg.shouldPreserveLastModified.value and self.lastModified:
                    try:
                        from email.utils import parsedate_to_datetime
                        mtime = parsedate_to_datetime(self.lastModified).timestamp()
                        os.utime(self.outputPath, (mtime, mtime))
                    except Exception as e:
                        logger.opt(exception=e).warning("设置文件修改时间失败 {}", self.outputPath)
