import asyncio
import os
from asyncio import TaskGroup
from dataclasses import field, dataclass
from pathlib import Path
from struct import unpack, pack

import niquests
from loguru import logger

from app.bases.interfaces import Worker
from app.bases.models import Task, TaskStage
from app.supports.config import DEFAULT_HEADERS, cfg
from app.supports.utils import getProxies, getReadableSize
from features.http_pack.const import SpecialFileSize
from app.supports.sysio import pwrite


class HttpTaskStage(TaskStage):
    url: str
    fileSize: int
    headers: dict
    proxies: dict
    resolvePath: str
    blockNum: int

@dataclass
class HttpTask(Task):
    url: str
    fileSize: int
    headers: dict = field(default_factory=DEFAULT_HEADERS.copy)
    proxies: dict = field(default_factory=getProxies)
    blockNum: int = field(default=8)    # TODO 下载设置项

@dataclass
class HttpSubworker:
    start: int
    progress: int
    end: int


class HttpWorker(Worker):
    def __init__(self, stage: HttpTaskStage):
        super().__init__(stage)
        self.stage = stage

    async def reassignWorker(self) -> HttpSubworker:
        ...

    async def handleSubworker(self, subworker: HttpSubworker):
        if subworker.end == SpecialFileSize.UNKNOWN:  # 支持断点续传, 但文件大小未知
            ...
        elif subworker.end == SpecialFileSize.NOT_SUPPORTED:  # 不支持断点续传
            ...
        else:  # 正常下载
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
                            if subworker.progress >= subworker.end:
                                break
                            if chunk:
                                offset = subworker.progress
                                pwrite(self.fileHandle, chunk, offset)
                                subworker.progress += 65536
                                cfg.globalSpeed += 65536
                                cfg.checkSpeedLimitation()
                    except Exception as e:
                        raise e
                    finally:
                        await res.close()

                    if subworker.progress > subworker.end:
                        subworker.progress = subworker.end

                except Exception as e:
                    logger.error(f"{self.stage.resolvePath}. {subworker} is reconnecting to the server, Error: {repr(e)}")
                    await asyncio.sleep(5)

            await self.reassignWorker()

    async def supervisor(self):
        recordFileHandle = open(Path(self.stage.resolvePath + ".ghd"), "wb")
        try:
            lastProgress = sum(subworker.progress - subworker.start for subworker in self.subworkers)
            while True:
                data = tuple(val for subworker in self.subworkers for val in (subworker.start, subworker.progress, subworker.end))
                recordFileHandle.write(pack("<" + "Q" * len(data), *data))
                recordFileHandle.flush()
                recordFileHandle.truncate()

                progress = sum(subworker.progress - subworker.start for subworker in self.subworkers)
                speed = getReadableSize(progress - lastProgress)
                lastProgress = progress
                print(speed)

                await asyncio.sleep(1)
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
        self.fileHandle = os.open(self.stage.resolvePath, os.O_RDWR | os.O_CREAT | os.O_TRUNC, 0o666)
        self.taskGroup = TaskGroup()
        self.subworkers: list = []
        self.client = niquests.AsyncSession(happy_eyeballs=True)

        if not self.restoreProgress():
            self.generateSubworkers()

        supervisor = asyncio.create_task(self.supervisor())

        try:
            async with self.taskGroup:
                for subworker in self.subworkers:
                    self.taskGroup.create_task(self.handleSubworker(subworker))

            logger.info(f"{self.stage.resolvePath} 下载完成")
        except Exception as e:
            logger.error(f"{self.stage.resolvePath} 错误: {repr(e)}")
        finally:
            supervisor.cancel()
            await supervisor
            os.close(self.fileHandle)
