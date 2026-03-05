import asyncio
import os
from asyncio import TaskGroup, CancelledError
from dataclasses import field, dataclass
from pathlib import Path
from struct import unpack, pack

import niquests
from loguru import logger

from app.bases.interfaces import Worker
from app.bases.models import Task, TaskStage, TaskStatus
from app.supports.config import DEFAULT_HEADERS, cfg
from app.supports.sysio import pwrite
from app.supports.utils import getProxies, getReadableSize
from features.http_pack.config import httpConfig
from features.http_pack.const import SpecialFileSize


@dataclass
class HttpTaskStage(TaskStage):
    url: str
    fileSize: int
    headers: dict
    proxies: dict
    resolvePath: str
    blockNum: int
    receivedBytes: int = field(default=0)
    accelerated: bool = field(default=False)


@dataclass
class HttpTask(Task):
    url: str
    fileSize: int
    headers: dict = field(default_factory=DEFAULT_HEADERS.copy)
    proxies: dict = field(default_factory=getProxies)
    blockNum: int = field(default=8)  # TODO 下载设置项

    async def run(self):
        try:
            self.stages.sort(key=lambda stage: stage.stageIndex)
            for stage in self.stages:
                if stage.status != TaskStatus.COMPLETED:
                    stage.status = TaskStatus.RUNNING
                    await HttpWorker(stage).run()
                    stage.status = TaskStatus.COMPLETED
        except CancelledError:
            logger.info(f"{self.title} 停止下载")

    def __hash__(self):
        return hash(self.taskId)

@dataclass
class HttpSubworker:
    start: int
    progress: int
    end: int


class HttpWorker(Worker):
    def __init__(self, stage: HttpTaskStage):
        super().__init__(stage)
        self.stage = stage
        self.speedHistory = []
        self.accelCheckTime = 0

    def reassignSubworker(self):
        slowestSubworker = max(self.subworkers, key=lambda subworker: subworker.end - subworker.progress)
        remainingBytes = slowestSubworker.end - slowestSubworker.progress
        if remainingBytes < httpConfig.maxReassignSize.value * 1048576:
            return
        base = remainingBytes // 2
        remainder = remainingBytes % 2
        slowestSubworker.end = slowestSubworker.progress + base + remainder
        newSubworker = HttpSubworker(slowestSubworker.end + 1, slowestSubworker.end + 1, slowestSubworker.end + base)
        self.subworkers.insert(self.subworkers.index(slowestSubworker) + 1, newSubworker)
        self.taskGroup.create_task(self.handleSubworker(newSubworker))

    async def handleSubworker(self, subworker: HttpSubworker):
        if subworker.end == SpecialFileSize.UNKNOWN:  # 支持断点续传, 但文件大小未知
            ...
        elif subworker.end == SpecialFileSize.NOT_SUPPORTED:  # 不支持断点续传
            ...
        else:  # 正常下载
            print(subworker.start, subworker.progress, subworker.end)
            while subworker.progress < subworker.end:
                try:
                    requestHeaders = self.stage.headers.copy()
                    requestHeaders["range"] = f"bytes={subworker.progress}-{subworker.end}"

                    res = await niquests.aget(self.stage.url, headers=requestHeaders, proxies=self.stage.proxies,
                                              verify=False, allow_redirects=True, stream=True)
                    try:
                        res.raise_for_status()
                        if res.status_code != 206:
                            raise Exception(f"服务器拒绝了范围请求，状态码：{res.status_code}")

                        async for chunk in await res.iter_raw(chunk_size=65536):
                            if not chunk:
                                continue
                            offset = subworker.progress
                            pwrite(self.fileHandle, chunk, offset)
                            # inc = len(chunk)
                            subworker.progress += 65536
                            cfg.globalSpeed += 65536
                            cfg.checkSpeedLimitation()
                            if subworker.progress >= subworker.end:
                                break
                    except Exception as e:
                        raise e
                    finally:
                        await res.close()

                    if subworker.progress > subworker.end:
                        subworker.progress = subworker.end

                except Exception as e:
                    logger.error(f"{self.stage.resolvePath}. {subworker} is reconnecting to the server, Error: {repr(e)}")
                    await asyncio.sleep(5)

            self.reassignSubworker()

    def checkIfAutoAcceleration(self):
        if self.stage.accelerated or not httpConfig.autoSpeedUp.value:
            return

        self.speedHistory.append(self.stage.speed)
        if len(self.speedHistory) > 5:
            self.speedHistory.pop(0)
        if len(self.speedHistory) < 5:
            return

        avgSpeed = sum(self.speedHistory) / len(self.speedHistory)
        if avgSpeed == 0:
            return

        maxDeviation = max(abs(speed - avgSpeed) / avgSpeed for speed in self.speedHistory)
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
            workerIncreaseRatio = ((currentWorkers - self.accelInitialWorkers) / self.accelInitialWorkers)
            speedIncreaseRatio = ((avgSpeed - self.accelInitialSpeed) / self.accelInitialSpeed)

            if speedIncreaseRatio < 0.8 * workerIncreaseRatio:
                self.stage.accelerated = True
                logger.info(
                    f"自动加速已禁用，subworker 增加比: {workerIncreaseRatio:.2%}, "
                    f"速度提升比: {speedIncreaseRatio:.2%}"
                )
            else:
                self.accelCheckTime = 0
                logger.info(
                    f"继续自动加速，subworker 增加比: {workerIncreaseRatio:.2%}, "
                    f"速度提升比: {speedIncreaseRatio:.2%}"
                )

    async def supervisor(self):
        recordFileHandle = open(Path(self.stage.resolvePath + ".ghd"), "wb")
        try:
            self.stage.receivedBytes = sum(subworker.progress - subworker.start for subworker in self.subworkers)
            while True:
                data = tuple(val for subworker in self.subworkers for val in (subworker.start, subworker.progress, subworker.end))
                recordFileHandle.seek(0)
                recordFileHandle.write(pack("<" + "Q" * len(data), *data))
                recordFileHandle.flush()
                recordFileHandle.truncate()

                receivedBytes = sum(subworker.progress - subworker.start for subworker in self.subworkers)
                self.stage.speed = receivedBytes - self.stage.receivedBytes
                self.stage.receivedBytes = receivedBytes
                self.stage.progress = (receivedBytes / self.stage.fileSize) * 100
                print(getReadableSize(self.stage.speed))

                self.checkIfAutoAcceleration()

                await asyncio.sleep(1)
        except CancelledError:
            logger.info(f"{self.stage.resolvePath} 停止下载")
        except Exception as e:
            logger.error(f"{self.stage.resolvePath} 出现异常: {e}")
        finally:
            recordFileHandle.close()

    def restoreProgress(self) -> bool:
        recordFile = Path(self.stage.resolvePath + ".ghd")
        if recordFile.exists():
            try:
                with open(recordFile, "rb") as f:
                    while True:
                        data = f.read(24)  # 每个 worker 有 3 个 64 位的无符号整数，共 24 字节
                        if not data: break

                        start, process, end = unpack("<QQQ", data)
                        self.subworkers.append(HttpSubworker(start, process, end))
                return True

            except Exception as e:
                logger.error(f"Failed to load workers: {e}")
                self.subworkers.clear()
                return False

        return False

    def generateSubworkers(self):
        step = self.stage.fileSize // self.stage.blockNum  # 每块大小
        start = 0
        for i in range(self.stage.blockNum - 1):
            end = start + step - 1
            self.subworkers.append(HttpSubworker(start, start, end))
            start = end + 1

        self.subworkers.append(HttpSubworker(start, start, self.stage.fileSize - 1)) # Http 请求是以 0 开头的

    async def run(self):
        # prepare async components
        self.taskGroup = TaskGroup()
        self.subworkers: list[HttpSubworker] = []
        self.client = niquests.AsyncSession(happy_eyeballs=True)
        self.client.trust_env = False

        restored = self.restoreProgress()
        if not restored:
            print("正在生成下载任务")
            self.generateSubworkers()
        else:
            print("从文件恢复下载进度")

        self.fileHandle = os.open(self.stage.resolvePath, os.O_RDWR | os.O_CREAT, 0o666)

        if not restored:
            try:
                os.ftruncate(self.fileHandle, self.stage.fileSize)
            except Exception as e:
                print(repr(e))

        supervisor = asyncio.create_task(self.supervisor())

        try:
            async with self.taskGroup:
                for subworker in self.subworkers:
                    self.taskGroup.create_task(self.handleSubworker(subworker))

            logger.info(f"{self.stage.resolvePath} 下载完成")
        except Exception as e:
            logger.error(f"{self.stage.resolvePath} 错误: {repr(e)}")
        finally:
            if not supervisor.cancel():
                await supervisor
            os.close(self.fileHandle)
