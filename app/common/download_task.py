import asyncio
import os
import threading
from typing import Callable, IO

import curl_cffi
from loguru import logger


class Worker:
    def __init__(self, start, end, pos=0, session=None, headers: dict = None, fp: IO[bytes] = None):
        self.start = start
        self.end = end
        self.pos = pos + start
        self.chunkSize = 4194304  # 4MB
        self.session = session  # type: curl_cffi.AsyncSession
        self.headers = headers
        self.fp = fp

        self.task = None

    @property
    def progress(self):
        return self.pos - self.start

    @property
    def size(self):
        return self.end - self.start + 1

    @property
    def isComplete(self):
        return self.progress >= self.size

    async def download(self):
        if self.isComplete:
            return  # 防止创建空线程

        headers = self.headers.copy()  # 由于接下来需要修改 headers, 所以先复制一份

        while not self.isComplete:
            try:
                if self.end:  # 只有 end 是有效的情况下才设置 range
                    headers['range'] = f'bytes={self.pos}-{self.end}'

                async with (self.session.stream(
                        headers=headers
                ) as response):
                    response.raise_for_status()

                    # 同样, 只有 end 是有效的情况下范围检查才有意义
                    if self.end \
                            and response.status_code != 206:
                        raise RuntimeError(f"服务器拒绝了范围请求, Status Code: {response.status_code}")

                    async for chunk in response.content.aiter_chunks(self.chunkSize):
                        self.pos += len(chunk)
                        await asyncio.to_thread(os.write, self.fp.fileno(), chunk)

            except Exception as e:
                logger.debug(f"下载时发生错误: {type(e).__name__}: {e}")

    def start(self):
        self.task = asyncio.create_task(self.download())

    def stop(self):
        self.task.cancel()


class DownloadTask:
    def __init__(self, url):
        self.url = url
        self.headers = {}
        self.preCoroNum = 8
        self.filePath = None
        self.fileName = None
        self.autoSpeedUp: Callable[[DownloadTask, float], ...]
        self.fileSize: int = 0
        self.fp = None
        self.thread = None
        self.main_task = None

        self.workers = []
        self.session = curl_cffi.AsyncSession(
            max_clients=256,
            trust_env=False,
            allow_redirects=True,
            impersonate='chrome',
            http_version='v3'
        )

    def addWorker(self, worker, run=False):
        self.workers.append(worker)
        if run:
            worker.start()

    def assign(self):
        if self.fileSize == 0:
            return
            
        chunkSize = self.fileSize // self.preCoroNum
        for i in range(self.preCoroNum - 1):
            yield i * chunkSize, (i + 1) * chunkSize - 1

        yield (self.preCoroNum - 1) * chunkSize, self.fileSize - 1

    async def main(self):
        async with self.session:
            if self.fileSize == 0:
                self.addWorker(Worker(0, 0, 0, self.session, self.headers, self.fp))

            else:
                for start, end in self.assign():
                    self.addWorker(Worker(start, end, 0, self.session, self.headers, self.fp))


    def threadMain(self):
        loop = asyncio.EventLoop()
        asyncio.set_event_loop(loop)
        try:
            self.main_task = loop.create_task(self.main())
            loop.run_until_complete(self.main_task)
        except Exception as e:
            logger.error(e)

    def start(self):
        self.thread = threading.Thread(target=self.threadMain)
        self.thread.start()

    def stop(self):
        self.main_task.cancel()
