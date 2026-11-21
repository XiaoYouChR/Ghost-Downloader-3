from __future__ import annotations

import asyncio
import errno
import os
import re
import sys
from asyncio import TaskGroup, CancelledError
from collections.abc import Awaitable, Buffer, Callable
from contextlib import suppress
from dataclasses import field, dataclass
from email.utils import parsedate_to_datetime
from pathlib import Path
from struct import unpack, pack
from time import monotonic, time

from loguru import logger
from wreq import Client, HeaderMap, Response, exceptions

from app.checksum import toChecksum
from app.client import buildClient, toEmulation
from app.config.cfg import cfg
from app.models.task import Task, TaskError, TaskStep, TaskStatus, SpecialFileSize, toHost
from app.platform.sysio import ftruncate, pwrite, writeAtomic

STREAM_READ_TIMEOUT = 30
PERMANENT_STATUS = frozenset({400, 401, 403, 404, 405, 410, 451})
FATAL_IO_ERRNO = frozenset({errno.ENOSPC, errno.EDQUOT, errno.EROFS, errno.EIO})
SAMPLE_SIZE = 4096
SAMPLE_TIMEOUT = 15
SOURCE_RETRY_DELAYS = (2, 5, 15)
MAX_RETRY_AFTER = 60
NETWORK_ERRORS = (exceptions.BodyError, exceptions.ConnectionError, exceptions.ConnectionResetError,
                  exceptions.ProxyConnectionError, exceptions.RequestError, exceptions.TimeoutError)


class PermanentDownloadError(Exception):
    def __init__(self, status: int):
        super().__init__(f"HTTP {status}")
        self.status = status


class RangeNotSupportedError(Exception):
    pass


class SourceVersionError(Exception):
    pass


class TemporaryDownloadError(Exception):
    def __init__(self, retryAfter: float = 0):
        self.retryAfter = retryAfter


def rangeEnd(contentRange: bytes, start: int, end: int, total: int | None) -> int | None:
    """RFC 9110 §14.4"""
    unit, _, spec = contentRange.strip().partition(b" ")
    span, _, size = spec.partition(b"/")
    first, _, last = span.partition(b"-")
    if unit.lower() != b"bytes" or not (first.isdigit() and last.isdigit() and size.isdigit()):
        return None
    try:
        firstByte, lastByte, size = int(first), int(last), int(size)
    except ValueError:
        return None
    if firstByte == start and start <= lastByte <= end and lastByte < size and total in {None, size}:
        return lastByte
    return None


def matchRange(contentRange: bytes, start: int, end: int, total: int | None) -> bool:
    return rangeEnd(contentRange, start, end, total) is not None


def strongETag(response: Response) -> str:
    value = bytes(response.headers.get("etag") or b"").strip()
    return value.decode("ascii") if re.fullmatch(rb'"[\x21\x23-\x7e]*"', value) else ""


def retryAfter(response: Response) -> float:
    value = bytes(response.headers.get("retry-after") or b"").strip()
    try:
        delay = int(value) if value.isdigit() else parsedate_to_datetime(value.decode("ascii")).timestamp() - time()
    except (ValueError, OverflowError, OSError):
        return 0
    return max(0, min(delay, MAX_RETRY_AFTER))


def saveCheckpoint(fd: int, path: Path, data: bytes) -> None:
    os.fsync(fd)
    writeAtomic(path, data)


@dataclass(kw_only=True, eq=False)
class HttpSource:
    url: str = field(repr=False, metadata={"persist": True})
    headers: dict[str, str] = field(repr=False, metadata={"persist": True})
    clientProfile: str
    userAgent: str = field(repr=False, metadata={"persist": True})
    etag: str = field(default="", repr=False, metadata={"persist": True})
    effectiveUrl: str = field(default="", init=False, repr=False)
    receivedBytes: int = 0
    speed: int = field(default=0, init=False, repr=False)
    isDisabled: bool = field(default=False, init=False, repr=False)
    retryAt: float = field(default=0, init=False, repr=False)
    failureCount: int = field(default=0, init=False, repr=False)

    @property
    def host(self) -> str:
        return toHost(self.url)

    @property
    def isUnavailable(self) -> bool:
        return self.isDisabled or self.retryAt > monotonic()

    def retryLater(self, delay: float) -> None:
        if self.isUnavailable:
            return
        if self.failureCount >= len(SOURCE_RETRY_DELAYS):
            self.isDisabled = True
        else:
            self.retryAt = monotonic() + max(delay, SOURCE_RETRY_DELAYS[self.failureCount])
            self.failureCount += 1
        self.speed = 0

    def openClient(self, timeout: int | None = None, *, shouldDecodeContent: bool = False) -> Client:
        return buildClient(emulation=toEmulation(self.clientProfile, ""),
                           userAgent=self.userAgent or None, readTimeout=timeout or STREAM_READ_TIMEOUT,
                           timeout=timeout, shouldDecodeContent=shouldDecodeContent,
                           shouldSetRedirectReferer=not any(key.lower() == "referer" for key in self.headers))

    def requestHeaders(self, start: int, end: int) -> dict[str, str]:
        headers = {key.lower(): value for key, value in self.headers.items()}
        if self.userAgent:
            headers.setdefault("user-agent", self.userAgent)
        headers["range"] = f"bytes={start}-{end}"
        headers["accept-encoding"] = "identity"
        if self.etag:
            headers["if-match"] = self.etag
            headers.pop("if-range", None)
        return headers

    def checkVersion(self, response: Response) -> None:
        etag = strongETag(response)
        if self.etag and self.etag != etag:
            raise SourceVersionError()
        self.etag = etag

    async def fetchSample(self, start: int, end: int, total: int) -> bytes:
        client = self.openClient(SAMPLE_TIMEOUT)
        try:
            response = await client.get(self.url, headers=self.requestHeaders(start, end))
            try:
                if checkRangeResponse(response, start, end, total) != end:
                    raise RangeNotSupportedError()
                self.checkVersion(response)
                data = bytearray()
                async for chunk in response.stream():
                    if isinstance(chunk, HeaderMap) or not chunk:
                        continue
                    if len(data) + len(chunk) > end - start + 1:
                        raise RangeNotSupportedError()
                    data.extend(chunk)
                if len(data) != end - start + 1:
                    raise RangeNotSupportedError()
                self.effectiveUrl = str(response.url)
                return bytes(data)
            finally:
                response.close()
        finally:
            client.close()


def checkRangeResponse(response: Response, start: int, end: int, total: int) -> int:
    status = response.status.as_int()
    if status in PERMANENT_STATUS or response.headers.contains_key("cf-mitigated"):
        raise PermanentDownloadError(status)
    if status == 412:
        raise SourceVersionError()
    if status in {408, 429} or 500 <= status < 600:
        raise TemporaryDownloadError(retryAfter(response))
    encoding = bytes(response.headers.get("content-encoding") or b"identity").lower().strip()
    contentRange = bytes(response.headers.get("content-range") or b"")
    servedEnd = rangeEnd(contentRange, start, end, total)
    length = bytes(response.headers.get("content-length") or b"").strip()
    if status != 206 or encoding != b"identity" or servedEnd is None:
        raise RangeNotSupportedError()
    if length and length.lstrip(b"0") != str(servedEnd - start + 1).encode("ascii"):
        raise RangeNotSupportedError()
    return servedEnd


@dataclass
class HttpSubworker:
    index: int
    start: int
    end: int
    receivedBytes: int = 0
    source: HttpSource | None = field(default=None, repr=False, compare=False)

    @property
    def position(self) -> int:
        return self.start + self.receivedBytes


@dataclass(kw_only=True)
class HttpRun:
    fd: int
    recordPath: Path
    subworkers: list[HttpSubworker]
    primary: HttpSource
    reportSpeed: Callable[[int], None]
    waitForSpeedLimit: Callable[[], Awaitable[None]]
    isRangeReady: bool
    group: TaskGroup | None = None
    checkpoint: bytes = b""


@dataclass(kw_only=True, eq=False)
class HttpTask(Task):
    packId: str = "http"
    canEdit = True
    expectedSha256: str = ""

    @property
    def mirrorStep(self) -> HttpTaskStep | None:
        if self.packId != "http" or len(self.steps) != 1 or type(self.steps[0]) is not HttpTaskStep:
            return None
        step = self.steps[0]
        if step.canUseRangeRequests and step.fileSize == self.fileSize > 0 and not step.httpByteOffset and not step.filePath:
            return step
        return None

    def canAddSource(self, incoming: Task) -> bool:
        if not isinstance(incoming, HttpTask) or self.status not in {TaskStatus.RUNNING, TaskStatus.PAUSED}:
            return False
        step, other = self.mirrorStep, incoming.mirrorStep
        return (step is not None and other is not None and step.mirror is None and step.url != other.url
                and self.name.casefold() == incoming.name.casefold() and self.fileSize == incoming.fileSize)

    async def addSource(self, incoming: Task, expectedSha256: str = "") -> None:
        if not self.canAddSource(incoming):
            raise TaskError("任务已变更，无法追加此下载源")
        sha256 = expectedSha256.strip().lower()
        if sha256 and not re.fullmatch(r"[0-9a-f]{64}", sha256):
            raise TaskError("SHA-256 必须是 64 位十六进制字符")
        if sha256 and self.expectedSha256 and sha256 != self.expectedSha256:
            raise TaskError("输入的 SHA-256 与任务已有的校验值不同")
        step = self.mirrorStep
        path = self.outputPath
        primary = step.buildSource()
        mirror = incoming.mirrorStep.buildSource()
        await step.verifySource(primary, mirror)
        if (not self.canAddSource(incoming) or self.mirrorStep is not step or self.outputPath != path
                or primary.headers != step.headers
                or primary.clientProfile != step.clientProfile or primary.userAgent != step.userAgent):
            raise TaskError("任务已变更，无法追加此下载源")
        step.addMirror(primary, mirror)
        self.expectedSha256 = sha256 or self.expectedSha256

    def relink(self, newTask: Task) -> None:
        if newTask.packId not in {"http", "github", "zip", "ffmpeg"}:
            raise TaskError("该链接不能用于更换")
        old, new = self.steps[0], newTask.steps[0]
        if not new.canUseRangeRequests:
            raise TaskError("该链接不能用于更换")
        if self.fileSize <= 0 or new.fileSize != self.fileSize:
            raise TaskError("新链接的内容与原任务不同，请重新添加任务")
        if old.mirror is not None and newTask.packId == "github":
            raise TaskError("该链接不能用于更换")
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
        if old.mirror is not None:
            new.mirror = old.mirror
            new.needsSourceVerification = True
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
    mirror: HttpSource | None = None
    primaryETag: str = ""
    needsSourceVerification: bool = False
    isFinishing: bool = field(default=False, init=False, repr=False)
    subworkers: list[HttpSubworker] = field(default_factory=list, repr=False)
    _activeRun: HttpRun | None = field(default=None, init=False, repr=False)
    _primarySource: HttpSource | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if isinstance(self.mirror, dict):
            from app.models.serialization import filterFields
            self.mirror = HttpSource(**filterFields(HttpSource, self.mirror))

    def buildSource(self) -> HttpSource:
        return HttpSource(url=self.url, headers=dict(self.headers), clientProfile=self.clientProfile,
                          userAgent=self.userAgent, etag=self.primaryETag)

    def addMirror(self, primary: HttpSource, mirror: HttpSource) -> None:
        if self.primaryETag and self.primaryETag != primary.etag:
            raise TaskError("下载源的文件版本已变更")
        run = self._activeRun
        if self.status == TaskStatus.RUNNING:
            if run is None or not self.canAssignSource(run):
                raise TaskError("任务没有可分配的剩余区段")
            try:
                self.assignSource(run, mirror, minBytes=2)
            except RuntimeError:
                raise TaskError("任务没有可分配的剩余区段") from None
        self.primaryETag = primary.etag
        if run is not None:
            run.primary.etag = primary.etag
        self.mirror = mirror

    @property
    def sources(self) -> tuple[HttpSource, ...]:
        primary = self._primarySource
        if primary is None:
            primary = self.buildSource()
            primary.receivedBytes = max(0, self.receivedBytes - (self.mirror.receivedBytes if self.mirror else 0))
        return (primary, self.mirror) if self.mirror else (primary,)

    def isSourceActive(self, source: HttpSource) -> bool:
        return self.status == TaskStatus.RUNNING and any(sw.source is source for sw in self.subworkers)

    async def verifySource(self, primary: HttpSource, mirror: HttpSource) -> None:
        fileSize = self.fileSize
        sampleSize = min(fileSize, SAMPLE_SIZE, max(1, fileSize // 3))
        offsets = dict.fromkeys((0, (fileSize - sampleSize) // 2, fileSize - sampleSize))
        written = self.subworkers or self._loadRecord()
        savedSample = None
        for sw in written:
            if sw.receivedBytes < sampleSize:
                continue
            offsets[sw.start] = None
            try:
                with open(self.outputPath, "rb") as output:
                    output.seek(sw.start)
                    savedSample = (sw.start, output.read(sampleSize))
            except OSError:
                raise TaskError("无法读取原任务已下载的区段") from None
            break

        try:
            async with asyncio.timeout(SAMPLE_TIMEOUT):
                for offset in offsets:
                    end = offset + sampleSize - 1
                    first, second = await asyncio.gather(
                        primary.fetchSample(offset, end, fileSize), mirror.fetchSample(offset, end, fileSize),
                        return_exceptions=True)
                    for result in (first, second):
                        if isinstance(result, BaseException):
                            raise result
                    if first != second or (savedSample and savedSample[0] == offset and first != savedSample[1]):
                        raise TaskError("下载源的文件样本与原任务不一致")
        except SourceVersionError:
            raise TaskError("下载源的文件版本已变更") from None
        except (PermanentDownloadError, RangeNotSupportedError):
            raise TaskError("无法验证下载源，请检查链接和文件大小，并确认两端支持范围请求") from None
        except TaskError:
            raise
        except Exception:
            raise TaskError("无法读取下载源的文件样本，请检查链接或网络") from None

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
        if self.mirror is not None and any(
            key in options and options[key] != getattr(self, key)
            for key in ("headers", "clientProfile", "userAgent")
        ):
            self.needsSourceVerification = True
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
            if self.fileSize > 0:
                nextStart = 0
                for sw in subworkers:
                    if sw.start != nextStart or not sw.start <= sw.position <= sw.end + 1 or sw.end < sw.start:
                        raise ValueError("Invalid download range record")
                    nextStart = sw.end + 1
                if nextStart != self.fileSize:
                    raise ValueError("Incomplete download range record")
                writtenEnd = max((sw.position for sw in subworkers if sw.receivedBytes), default=0)
                if Path(self.outputPath).stat().st_size < writtenEnd:
                    raise ValueError("Download file is shorter than its range record")
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

    def _splitSlowest(self, run: HttpRun, count: int = 2) -> list[HttpSubworker]:
        slowest = max(run.subworkers, key=lambda sw: sw.end - sw.position + 1)
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
            newSubworkers.append(HttpSubworker(index=len(run.subworkers) + len(newSubworkers), start=start, end=start + base - 1))
            start += base
        newSubworkers[-1].end = oldEnd
        index = run.subworkers.index(slowest) + 1
        run.subworkers[index:index] = newSubworkers
        return newSubworkers

    def _emptyRightOf(self, run: HttpRun, subworker: HttpSubworker) -> HttpSubworker | None:
        """右侧分片尚未收到数据时返回它。"""
        if self.mirror is not None:
            return None
        index = run.subworkers.index(subworker) + 1
        if index < len(run.subworkers) and not run.subworkers[index].receivedBytes:
            return run.subworkers[index]
        return None

    def _reassignSubworker(self, run: HttpRun) -> None:
        if self.fileSize <= 0:
            return
        slowest = max(run.subworkers, key=lambda sw: sw.end - sw.position + 1)
        if slowest.end - slowest.position + 1 < cfg.maxReassignSize.value * 1024:
            return
        for newSw in self._splitSlowest(run):
            self._startSubworker(run, newSw, run.primary)

    def canAssignSource(self, run: HttpRun) -> bool:
        return run.group is not None and run.isRangeReady and any(
            sw.end - sw.position + 1 >= (2 if sw.source is not None else 1) for sw in run.subworkers)

    def assignSource(self, run: HttpRun, source: HttpSource, *, minBytes: int) -> None:
        remaining = [sw for sw in run.subworkers if sw.position <= sw.end]
        idle = [sw for sw in remaining if sw.source is None]
        if idle:
            self._startSubworker(run, max(idle, key=lambda sw: sw.end - sw.position), source)
        elif remaining and max(sw.end - sw.position + 1 for sw in remaining) >= minBytes:
            for subworker in self._splitSlowest(run):
                try:
                    self._startSubworker(run, subworker, source)
                except RuntimeError:
                    index = run.subworkers.index(subworker)
                    run.subworkers[index - 1].end = subworker.end
                    run.subworkers.pop(index)
                    raise

    def _startSubworker(self, run: HttpRun, subworker: HttpSubworker, source: HttpSource) -> None:
        group = run.group
        if group is None:
            raise RuntimeError("No active HTTP task group")
        group.create_task(self._runAssigned(run, subworker, source))
        subworker.source = source

    async def _runAssigned(self, run: HttpRun, subworker: HttpSubworker, source: HttpSource) -> None:
        try:
            if self.mirror is not None and run.isRangeReady:
                await self._runMirrored(run, subworker, source)
            else:
                await self._runSubworker(run, subworker)
        finally:
            lastSource = subworker.source
            subworker.source = None
        if self.mirror is not None and run.isRangeReady and lastSource is not None:
            if lastSource.isUnavailable:
                lastSource = next((s for s in self.sources if not s.isUnavailable), None)
            if lastSource is not None:
                self.assignSource(run, lastSource, minBytes=max(2, cfg.maxReassignSize.value * 1024))

    def _autoSpeedUp(self, run: HttpRun) -> None:
        if self.mirror is not None or self.isAccelerated or not cfg.autoSpeedUp.value:
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
            self._accelInitialWorkers = len(run.subworkers)
            self._accelInitialSpeed = avgSpeed
            self._accelCheckTime = asyncio.get_running_loop().time()
            for _ in range(4):
                self._reassignSubworker(run)
        else:
            elapsed = asyncio.get_running_loop().time() - self._accelCheckTime
            if elapsed <= 5:
                return

            workerRatio = (len(run.subworkers) - self._accelInitialWorkers) / self._accelInitialWorkers
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

    async def _supervise(self, run: HttpRun, stopping: asyncio.Event) -> None:
        lastTick = monotonic()
        sourceBytes = {source: source.receivedBytes for source in self.sources}
        self.receivedBytes = sum(sw.receivedBytes for sw in run.subworkers)
        while not stopping.is_set():
            await self._flushRecord(run)
            if stopping.is_set():
                break
            receivedBytes = sum(sw.receivedBytes for sw in run.subworkers)
            self.speed = receivedBytes - self.receivedBytes
            self.receivedBytes = receivedBytes
            self.progress = receivedBytes * 100 / self.fileSize if self.fileSize > 0 else 0

            now = monotonic()
            elapsed = max(now - lastTick, 0.001)
            for source in self.sources:
                lastBytes = sourceBytes.get(source, 0)
                source.speed = int(max(0, source.receivedBytes - lastBytes) / elapsed)
                sourceBytes[source] = source.receivedBytes
            lastTick = now
            self._autoSpeedUp(run)
            with suppress(TimeoutError):
                await asyncio.wait_for(stopping.wait(), timeout=1)

        await self._flushRecord(run)
        self.receivedBytes = sum(sw.receivedBytes for sw in run.subworkers)
        self.progress = self.receivedBytes * 100 / self.fileSize if self.fileSize > 0 else 0
        for source in self.sources:
            source.speed = 0

    async def _flushRecord(self, run: HttpRun) -> None:
        if not self.canUseRangeRequests:
            return
        spans = tuple(val for sw in run.subworkers for val in (sw.start, sw.position, sw.end))
        data = pack("<" + "Q" * len(spans), *spans)
        if data != run.checkpoint:
            await asyncio.to_thread(saveCheckpoint, run.fd, run.recordPath, data)
            run.checkpoint = data

    async def _writeChunk(
        self, run: HttpRun, subworker: HttpSubworker, source: HttpSource, chunk: Buffer,
    ) -> None:
        data = memoryview(chunk)
        written = 0
        while written < len(data):
            count = pwrite(run.fd, data[written:], subworker.position + written)
            if not count:
                raise OSError(errno.EIO, "Incomplete file write")
            written += count
        subworker.receivedBytes += written
        source.receivedBytes += written
        run.reportSpeed(written)
        await run.waitForSpeedLimit()

    async def _runMirrored(self, run: HttpRun, subworker: HttpSubworker, source: HttpSource) -> None:
        mirror = self.mirror
        assert mirror is not None
        sources = (run.primary, mirror)
        while subworker.position <= subworker.end:
            if source.isUnavailable:
                available = next((candidate for candidate in sources if not candidate.isUnavailable), None)
                if available is None:
                    retries = [candidate.retryAt for candidate in sources if not candidate.isDisabled]
                    if not retries:
                        raise TaskError("下载源不可用，请检查链接或稍后继续")
                    await asyncio.sleep(max(0, min(retries) - monotonic()))
                    continue
                source = available
            subworker.source = source
            try:
                await self._fetchRange(run, subworker, source)
            except TemporaryDownloadError as error:
                source.retryLater(error.retryAfter)
            except NETWORK_ERRORS:
                source.retryLater(0)
            except (PermanentDownloadError, RangeNotSupportedError, SourceVersionError,
                    exceptions.BuilderError, exceptions.DecodingError, exceptions.RedirectError,
                    exceptions.StatusError, exceptions.TlsError, exceptions.UpgradeError) as error:
                source.isDisabled = True
                source.speed = 0
                logger.warning("下载源 {} 不可用 ({})", source.host, type(error).__name__)
            else:
                if not source.isUnavailable:
                    source.failureCount = 0

    async def _fetchRange(self, run: HttpRun, subworker: HttpSubworker, source: HttpSource) -> None:
        start, end = subworker.position, subworker.end
        client = source.openClient()
        try:
            response = await client.get(source.url, headers=source.requestHeaders(start, end))
            try:
                servedEnd = checkRangeResponse(response, start, end, self.fileSize)
                source.checkVersion(response)
                source.effectiveUrl = str(response.url)
                if source is run.primary:
                    self.primaryETag = source.etag
                finalChunk = None
                async for chunk in response.stream():
                    if isinstance(chunk, HeaderMap) or not chunk:
                        continue
                    declaredBytes = servedEnd - subworker.position + 1
                    if finalChunk is not None or len(chunk) > declaredBytes:
                        raise RangeNotSupportedError()
                    remaining = min(servedEnd, subworker.end) - subworker.position + 1
                    if subworker.end < servedEnd and len(chunk) >= remaining:
                        await self._writeChunk(run, subworker, source, chunk[:remaining])
                        return
                    if len(chunk) == declaredBytes:
                        finalChunk = chunk
                    else:
                        await self._writeChunk(run, subworker, source, chunk)
                if finalChunk is None:
                    raise TemporaryDownloadError()
                # A checkpoint must not mark the range complete before its stream ends.
                remaining = subworker.end - subworker.position + 1
                await self._writeChunk(run, subworker, source, finalChunk[:remaining])
            finally:
                response.close()
        finally:
            client.close()

    async def _runSubworker(self, run: HttpRun, subworker: HttpSubworker) -> None:
        primary = run.primary
        fd = run.fd
        if subworker.end == SpecialFileSize.UNKNOWN:
            while True:
                client = primary.openClient(shouldDecodeContent=True)
                try:
                    httpPos = self.httpByteOffset + subworker.position
                    headers = {**self._effectiveHeaders, "range": f"bytes={httpPos}-", "accept-encoding": "identity"}
                    response = await client.get(primary.url, headers=headers)
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
                            await self._writeChunk(run, subworker, primary, chunk)
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
                    logger.error("下载分片失败，将在 5 秒后重试 {} ({})", primary.host, type(e).__name__)
                    await asyncio.sleep(5)
                finally:
                    client.close()

        elif subworker.end == SpecialFileSize.NOT_SUPPORTED:
            while True:
                client = primary.openClient(shouldDecodeContent=True)
                try:
                    ftruncate(fd, 0)
                    primary.receivedBytes = subworker.receivedBytes = 0
                    response = await client.get(primary.url, headers=dict(self._effectiveHeaders))
                    try:
                        status = response.status.as_int()
                        if status in PERMANENT_STATUS or response.headers.contains_key("cf-mitigated"):
                            raise PermanentDownloadError(status)
                        if status != 200:
                            raise Exception(f"服务器返回了异常状态码：{status}")
                        async for chunk in response.stream():
                            if isinstance(chunk, HeaderMap) or not chunk:
                                continue
                            await self._writeChunk(run, subworker, primary, chunk)
                            if self.isFinishing:
                                break
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
                    if self.isFinishing:
                        ftruncate(fd, subworker.receivedBytes)
                        return
                    logger.error("下载分片失败，将在 5 秒后重试 {} ({})", primary.host, type(e).__name__)
                    await asyncio.sleep(5)
                finally:
                    client.close()

        else:
            while True:
                # 已被左侧分片并入
                if subworker not in run.subworkers:
                    return
                if self.mirror is not None and run.isRangeReady:
                    await self._runMirrored(run, subworker, primary)
                    return
                while subworker.end < subworker.position and (right := self._emptyRightOf(run, subworker)):
                    subworker.end = right.end
                    run.subworkers.remove(right)
                if subworker.position > subworker.end:
                    break
                client = primary.openClient(shouldDecodeContent=True)
                try:
                    # https://github.com/XiaoYouChR/Ghost-Downloader-3/issues/888
                    shouldConfirmFileSize = isinstance(self.task, HttpTask) and run.subworkers == [subworker] and subworker.position == 0
                    httpPos = self.httpByteOffset + subworker.position
                    # 请求至 Step 末尾，以便直接并入右侧分片
                    httpEnd = self.httpByteOffset + self.fileSize - 1
                    headers = {**self._effectiveHeaders, "accept-encoding": "identity"}
                    if not shouldConfirmFileSize:
                        headers["range"] = f"bytes={httpPos}-{httpEnd}"
                        if primary.etag:
                            headers["if-match"] = primary.etag
                    response = await client.get(primary.url, headers=headers)
                    try:
                        if self.mirror is not None:
                            continue
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
                            if status == 412:
                                raise SourceVersionError()
                            if status == 200:
                                raise RangeNotSupportedError()
                            if status != 206:
                                raise Exception(f"服务器拒绝了范围请求，状态码：{status}")
                            total = self.fileSize if isinstance(self.task, HttpTask) else None
                            if not matchRange(bytes(response.headers.get("content-range") or b""), httpPos, httpEnd, total):
                                raise RangeNotSupportedError()
                            if primary.etag:
                                primary.checkVersion(response)
                        primary.effectiveUrl = str(response.url)
                        if shouldConfirmFileSize and self.canUseRangeRequests:
                            primary.etag = self.primaryETag = strongETag(response)
                        run.isRangeReady = self.canUseRangeRequests and self.fileSize > 0
                        if len(run.subworkers) == 1 and self.canUseRangeRequests:
                            for newSw in self._splitSlowest(run, self.subworkerCount):
                                self._startSubworker(run, newSw, primary)
                        async for chunk in response.stream():
                            if self.mirror is not None:
                                break
                            if isinstance(chunk, HeaderMap) or not chunk:
                                continue
                            if not subworker.receivedBytes and subworker not in run.subworkers:
                                return
                            while subworker.end < subworker.position + len(chunk) and (right := self._emptyRightOf(run, subworker)):
                                subworker.end = right.end
                                run.subworkers.remove(right)
                            remaining = subworker.end - subworker.position + 1
                            if len(chunk) > remaining:
                                chunk = chunk[:remaining]
                            if chunk:
                                await self._writeChunk(run, subworker, primary, chunk)
                            if subworker.position > subworker.end or self.isFinishing or self.mirror is not None:
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
                except SourceVersionError:
                    raise TaskError("下载源的文件版本已变更") from None
                except (PermanentDownloadError, RangeNotSupportedError):
                    if self.mirror is not None:
                        continue
                    raise
                except Exception as e:
                    if isinstance(e, OSError) and e.errno in FATAL_IO_ERRNO:
                        raise
                    if self.isFinishing:
                        ftruncate(fd, subworker.position)
                        return
                    if not self.canUseRangeRequests:
                        raise RangeNotSupportedError() from e
                    if self.mirror is not None:
                        continue
                    # 服务器限流时仅拒绝新连接，尚未收到数据的分片留待左侧分片并入
                    if not subworker.receivedBytes and run.subworkers[0] is not subworker:
                        logger.info("分片请求失败，留待左侧分片并入 {} ({})", primary.host, type(e).__name__)
                        return
                    logger.error("下载分片失败，将在 5 秒后重试 {} ({})", primary.host, type(e).__name__)
                    await asyncio.sleep(5)
                finally:
                    client.close()

            if self.mirror is None:
                self._reassignSubworker(run)

    async def run(
        self,
        reportSpeed: Callable[[int], None],
        waitForSpeedLimit: Callable[[], Awaitable[None]],
    ) -> None:
        if self._activeRun is not None:
            raise RuntimeError("HTTP step already running")
        self._speedHistory: list[int] = []
        self._accelCheckTime = 0
        self._effectiveHeaders = dict(self.headers)
        if self.userAgent and not any(k.lower() == "user-agent" for k in self.headers):
            self._effectiveHeaders["user-agent"] = self.userAgent
        self.isFinishing = False

        subworkers = self._loadRecord() if self.canUseRangeRequests else []
        isResuming = bool(subworkers)
        if not isResuming:
            self._deleteRecord()
            subworkers = self._buildSubworkers()
        primary = self.buildSource()
        recordedBytes = sum(sw.receivedBytes for sw in subworkers)
        if self.mirror is not None:
            self.mirror.receivedBytes = min(self.mirror.receivedBytes, recordedBytes)
            self.mirror.isDisabled = False
            self.mirror.retryAt = self.mirror.failureCount = 0
        primary.receivedBytes = recordedBytes - (self.mirror.receivedBytes if self.mirror else 0)

        openMode = os.O_RDWR | os.O_CREAT
        if not self.canUseRangeRequests:
            openMode |= os.O_TRUNC
        run = HttpRun(
            fd=os.open(self.outputPath, openMode, 0o666),
            recordPath=self.recordPath,
            subworkers=subworkers,
            primary=primary,
            reportSpeed=reportSpeed,
            waitForSpeedLimit=waitForSpeedLimit,
            isRangeReady=isResuming or self.mirror is not None,
        )
        self._activeRun = run
        self._primarySource = primary
        self.subworkers = run.subworkers

        try:
            if self.mirror is not None and self.needsSourceVerification:
                await self.verifySource(primary, self.mirror)
                self.primaryETag = primary.etag
                self.needsSourceVerification = False
            if not isResuming and self.fileSize > 0:
                try:
                    ftruncate(run.fd, self.fileSize)
                except OSError as error:
                    logger.warning("预分配输出文件失败 ({})", type(error).__name__)

            while True:
                try:
                    await self._runWorkers(run, isResuming)
                    break
                except ExceptionGroup as errors:
                    if self.mirror is None and any(
                        isinstance(error, RangeNotSupportedError) for error in errors.exceptions
                    ):
                        # Reset the checkpoint before truncating the output it describes.
                        self._deleteRecord()
                        ftruncate(run.fd, 0)
                        self.canUseRangeRequests = isResuming
                        isResuming = run.isRangeReady = False
                        run.subworkers = self.subworkers = self._buildSubworkers()
                        run.primary.receivedBytes = 0
                        run.checkpoint = b""
                        self._speedHistory.clear()
                        self._accelCheckTime = 0
                        continue
                    cause = errors.exceptions[0]
                    if isinstance(cause, PermanentDownloadError):
                        raise TaskError("服务器返回了错误（{status}）", status=cause.status) from None
                    if isinstance(cause, OSError) and cause.errno in FATAL_IO_ERRNO:
                        raise TaskError("磁盘空间不足") from None
                    raise cause from None

            await self._verifyChecksum()
        except CancelledError:
            self.setStatus(TaskStatus.PAUSED)
            raise
        finally:
            try:
                os.close(run.fd)
            finally:
                self._activeRun = None

        self._deleteRecord()
        if cfg.shouldPreserveLastModified.value and self.lastModified:
            try:
                mtime = parsedate_to_datetime(self.lastModified).timestamp()
                os.utime(self.outputPath, (mtime, mtime))
            except (ValueError, OSError, OverflowError):
                logger.warning("设置文件修改时间失败 {}", self.outputPath)

    async def _runWorkers(self, run: HttpRun, isResuming: bool) -> None:
        stopping = asyncio.Event()
        supervisor = asyncio.create_task(self._supervise(run, stopping))
        try:
            group = TaskGroup()
            run.group = group
            async with group:
                if self.mirror is not None:
                    pending = sum(sw.position <= sw.end for sw in run.subworkers)
                    if pending > 1 or (pending == 1 and self._splitSlowest(run)):
                        self.assignSource(run, self.mirror, minBytes=2)
                for sw in run.subworkers:
                    if sw.source is None and (self.mirror is None or sw.position <= sw.end):
                        self._startSubworker(run, sw, run.primary)
                if isResuming and self.mirror is None:
                    for sw in self._splitSlowest(run, self.subworkerCount - len(run.subworkers) + 1):
                        self._startSubworker(run, sw, run.primary)
        finally:
            run.group = None
            stopping.set()
            # The checkpoint thread still owns the descriptor until the supervisor exits.
            wasCancelled = False
            while not supervisor.done():
                try:
                    await asyncio.shield(supervisor)
                except CancelledError:
                    wasCancelled = True
            supervisor.result()
            if wasCancelled:
                raise CancelledError

    async def _verifyChecksum(self) -> None:
        expected = self.task.expectedSha256 if isinstance(self.task, HttpTask) else ""
        if expected:
            actual = await toChecksum(Path(self.outputPath), "sha256", lambda _: None)
            if actual != expected:
                raise TaskError("SHA256 校验失败：期望 {expected}，实际 {actual}",
                                expected=expected, actual=actual)
            self.task.checksums["sha256"] = actual
