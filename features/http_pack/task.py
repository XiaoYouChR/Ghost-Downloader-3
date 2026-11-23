from __future__ import annotations

import asyncio
import errno
import os
import sys
from asyncio import TaskGroup, CancelledError
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import field, dataclass
from pathlib import Path
from struct import unpack, pack

from loguru import logger
from wreq import HeaderMap

from app.client import buildClient, toEmulation
from app.file_writer import FileWriter, FileWriteError
from app.config.cfg import cfg
from app.models.task import Task, TaskError, TaskStep, TaskStatus, SpecialFileSize
from app.platform.sysio import ftruncate

STREAM_READ_TIMEOUT = 30
AUTO_SPEED_UP_MAX_SUBWORKERS = 64
PERMANENT_STATUS = frozenset({400, 401, 403, 404, 405, 410, 451})
FATAL_IO_ERRNO = frozenset({errno.ENOSPC, errno.EDQUOT, errno.EROFS, errno.EIO})


class PermanentDownloadError(Exception):
    def __init__(self, status: int):
        super().__init__(f"HTTP {status}")
        self.status = status


class RangeNotSupportedError(Exception):
    pass


def toDiskTaskError(error: FileWriteError) -> Exception:
    if error.__cause__.errno in FATAL_IO_ERRNO:
        return TaskError("磁盘空间不足")
    return error


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

    def relink(self, newTask: Task) -> None:
        if newTask.packId not in {"http", "github", "zip", "ffmpeg"}:
            raise TaskError("该链接不能用于更换")
        old, new = self.steps[0], newTask.steps[0]
        if not new.canUseRangeRequests:
            raise TaskError("该链接不能用于更换")
        if self.fileSize <= 0 or new.fileSize != self.fileSize:
            raise TaskError("新链接的内容与原任务不同，请重新添加任务")
        if type(new) is not HttpTaskStep and newTask.packId != "github":
            new = HttpTaskStep(
                stepIndex=old.stepIndex,
                url=new.url,
                fileSize=new.fileSize,
                headers=dict(new.headers),
                clientProfile=new.clientProfile,
                userAgent=new.userAgent,
                subworkerCount=new.subworkerCount,
                canUseRangeRequests=new.canUseRangeRequests,
                lastModified=new.lastModified,
            )
        new.status = TaskStatus.PAUSED if old.status in {TaskStatus.RUNNING, TaskStatus.FAILED} else old.status
        new.progress, new.receivedBytes = old.progress, old.receivedBytes
        new._bindTask(self)
        self.url = newTask.url
        self.packId = "github" if newTask.packId == "github" or type(new) is not HttpTaskStep else "http"
        self.steps[0] = new
        self.updateStatus()


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
    filePath: str = ""
    isAccelerated: bool = False
    isFinishing: bool = field(default=False, init=False, repr=False)
    subworkers: list[HttpSubworker] = field(default_factory=list, repr=False)
    lastRunStopped: asyncio.Event | None = field(default=None, init=False, repr=False)

    def rangeStep(self, start: int, end: int, path: Path) -> HttpTaskStep:
        isSmall = end - start < cfg.maxReassignSize.value * 1024
        step = HttpTaskStep(
            stepIndex=self.stepIndex,
            url=self.url,
            headers=dict(self.headers),
            clientProfile=self.clientProfile,
            userAgent=self.userAgent,
            subworkerCount=1 if isSmall else self.subworkerCount,
            canUseRangeRequests=True,
            httpByteOffset=start,
            fileSize=end - start,
            filePath=str(path),
        )
        step._bindTask(self.task)
        return step

    @property
    def canPause(self) -> bool:
        return self.canUseRangeRequests

    def finish(self) -> None:
        """可从任意线程调用，读循环在下一个数据块或读超时时收尾。"""
        self.isFinishing = True

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
        return self.filePath or self.task.outputPath

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
            self._taskGroup.create_task(self._runSubworker(newSw))

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
            # 限流按连接计的服务器上速度会随连接数一直增长，不设上限会被当作滥用而封禁
            activeCount = sum(sw.position <= sw.end for sw in self.subworkers)
            if activeCount >= AUTO_SPEED_UP_MAX_SUBWORKERS:
                self.isAccelerated = True
                logger.info("自动加速已达连接上限 {}", AUTO_SPEED_UP_MAX_SUBWORKERS)
                return
            self._accelInitialWorkers = len(self.subworkers)
            self._accelInitialSpeed = avgSpeed
            self._accelCheckTime = asyncio.get_running_loop().time()
            for _ in range(min(4, AUTO_SPEED_UP_MAX_SUBWORKERS - activeCount)):
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

    def _buildRecord(self) -> bytes:
        data = tuple(val for sw in self.subworkers for val in (sw.start, sw.position, sw.end))
        return pack("<" + "Q" * len(data), *data)

    async def _supervise(self) -> None:
        recordFile = None
        if self.canUseRangeRequests:
            recordFile = open(self.recordPath, "wb")
        # 进度在提交写入时即推进，快照须等对应数据落盘后才能保存，否则崩溃后续传会留下空洞
        pending: tuple[int, bytes] | None = None
        try:
            self.receivedBytes = sum(sw.receivedBytes for sw in self.subworkers)
            while True:
                if recordFile is not None:
                    if pending is None:
                        pending = (self._writer.submittedCount, self._buildRecord())
                    if self._writer.doneCount >= pending[0]:
                        recordFile.seek(0)
                        recordFile.write(pending[1])
                        recordFile.flush()
                        recordFile.truncate()
                        pending = None

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

    async def _runSubworker(self, subworker: HttpSubworker) -> None:
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
                            self._writer.write(chunk, subworker.position)
                            subworker.receivedBytes += len(chunk)
                            self._reportSpeed(len(chunk))
                            await self._waitForSpeedLimit()
                            await self._writer.waitForRoom()
                    finally:
                        response.close()
                    return
                except CancelledError:
                    raise
                except (PermanentDownloadError, RangeNotSupportedError, FileWriteError):
                    raise
                except Exception as e:
                    logger.opt(exception=e).error("下载分片失败，将在 5 秒后重试 {}", self.outputPath)
                    await asyncio.sleep(5)
                finally:
                    client.close()

        elif subworker.end == SpecialFileSize.NOT_SUPPORTED:
            while True:
                client = buildClient(emulation=self._emulation, userAgent=self.userAgent or None, readTimeout=STREAM_READ_TIMEOUT)
                try:
                    self._writer.truncate(0)
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
                            self._writer.write(chunk, subworker.receivedBytes)
                            subworker.receivedBytes += len(chunk)
                            self._reportSpeed(len(chunk))
                            await self._waitForSpeedLimit()
                            await self._writer.waitForRoom()
                            if self.isFinishing:
                                break
                    finally:
                        response.close()
                    self._writer.truncate(subworker.receivedBytes)
                    return
                except CancelledError:
                    raise
                except (PermanentDownloadError, FileWriteError):
                    raise
                except Exception as e:
                    if self.isFinishing:
                        self._writer.truncate(subworker.receivedBytes)
                        return
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
                                self._writer.truncate(self.fileSize)
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
                                self._taskGroup.create_task(self._runSubworker(newSw))
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
                            self._writer.write(chunk, subworker.position)
                            subworker.receivedBytes += len(chunk)
                            self._reportSpeed(len(chunk))
                            await self._waitForSpeedLimit()
                            await self._writer.waitForRoom()
                            if subworker.position > subworker.end or self.isFinishing:
                                break
                    finally:
                        response.close()

                    if not self.canUseRangeRequests:
                        self._writer.truncate(subworker.position)
                        return
                    if subworker.position > subworker.end:
                        subworker.receivedBytes = subworker.end - subworker.start + 1

                except CancelledError:
                    raise
                except (RangeNotSupportedError, FileWriteError):
                    raise
                except PermanentDownloadError as e:
                    # 部分服务器超出连接数时对新连接返回 403，左侧分片的连接仍然有效
                    if not subworker.receivedBytes and self.subworkers[0] is not subworker:
                        logger.info("分片请求被拒绝，留待左侧分片并入 {}: {}", self.outputPath, e)
                        return
                    raise
                except Exception as e:
                    if self.isFinishing:
                        self._writer.truncate(subworker.position)
                        return
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

    async def run(
        self,
        reportSpeed: Callable[[int], None],
        waitForSpeedLimit: Callable[[], Awaitable[None]],
    ) -> None:
        # 暂停后立即继续时，上一轮可能仍在把写入队列写完并保存记录
        if self.lastRunStopped is not None:
            await self.lastRunStopped.wait()
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
        self.isFinishing = False

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

        self._writer = FileWriter(self._fd)
        self.lastRunStopped = asyncio.Event()
        try:
            while True:
                supervisor = asyncio.create_task(self._supervise())
                try:
                    self._taskGroup = TaskGroup()
                    async with self._taskGroup:
                        for subworker in list(self.subworkers):
                            self._taskGroup.create_task(self._runSubworker(subworker))
                        if isResuming:
                            for newSw in self._splitSlowest(self.subworkerCount - len(self.subworkers) + 1):
                                self._taskGroup.create_task(self._runSubworker(newSw))

                    shouldDeleteRecord = True
                    break
                except CancelledError:
                    self.setStatus(TaskStatus.PAUSED)
                    raise
                except ExceptionGroup as eg:
                    if self._writer.error is not None:
                        raise toDiskTaskError(self._writer.error) from eg
                    if any(isinstance(e, RangeNotSupportedError) for e in eg.exceptions):
                        if isResuming:
                            # https://github.com/XiaoYouChR/Ghost-Downloader-3/issues/377
                            logger.warning("续传的范围对不上，重新下载 {}", self.outputPath)
                            isResuming = False
                        else:
                            logger.warning("服务器不支持范围请求，降级为单流下载 {}", self.outputPath)
                            self.canUseRangeRequests = False
                        self.subworkers = self._buildSubworkers()
                        self._writer.truncate(0)
                        self._deleteRecord()
                        self._speedHistory.clear()
                        self._accelCheckTime = 0
                        continue

                    cause = eg.exceptions[0]
                    if isinstance(cause, PermanentDownloadError):
                        raise TaskError("服务器返回了错误（{status}）", status=cause.status) from eg
                    raise cause from eg
                finally:
                    if not supervisor.done():
                        supervisor.cancel()
                        with suppress(CancelledError):
                            await supervisor
        finally:
            try:
                await self._writer.close()
                if self._writer.error is not None:
                    # 记录停留在最后一次落盘的快照，续传时补齐丢失的数据
                    shouldDeleteRecord = False
                elif not shouldDeleteRecord and self.canUseRangeRequests:
                    self.recordPath.write_bytes(self._buildRecord())
                if shouldDeleteRecord:
                    self._deleteRecord()
                    if cfg.shouldPreserveLastModified.value and self.lastModified:
                        try:
                            from email.utils import parsedate_to_datetime
                            mtime = parsedate_to_datetime(self.lastModified).timestamp()
                            os.utime(self.outputPath, (mtime, mtime))
                        except Exception as e:
                            logger.opt(exception=e).warning("设置文件修改时间失败 {}", self.outputPath)
            finally:
                self.lastRunStopped.set()
        # 最后几块数据可能在所有分片结束后才写入失败
        if self._writer.error is not None:
            raise toDiskTaskError(self._writer.error)
