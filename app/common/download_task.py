import asyncio
import struct
import time
from asyncio import Task
from pathlib import Path
from threading import Thread

import httpx
from PySide6.QtCore import QThread, Signal
from loguru import logger

from app.common.config import cfg
from app.common.methods import getProxy, getReadableSize, getLinkInfo

Headers = {
    "accept-encoding": "deflate, br",
    "accept-language": "zh-CN,zh;q=0.9",
    "cookie": "down_ip=1",
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "none",
    "sec-fetch-user": "?1",
    "upgrade-insecure-requests": "1",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36 Edg/112.0.1722.64"}


# def getRealUrl(url: str):
#     response = httpx.head(url=url, headers=Headers, follow_redirects=False, verify=False,
#                           proxyServer=getProxy())
#
#     if response.status_code == 400:  # Bad Requests
#         # TODO 报错处理
#         logger.error("HTTP status code 400, it seems that the url is unavailable")
#         return
#
#     while response.status_code == 302:  # 当302的时候
#         rs = response.headers["location"]  # 获取重定向信息
#         logger.info(f'HTTP status code:302, Headers["Location"] is: {rs}')
#         # 看它返回的是不是完整的URL
#         t = urlRe.search(rs)
#         if t:  # 是的话直接跳转
#             url = rs
#         elif not t:  # 不是在前面加上URL
#             url = re.findall(r"((?:https?|ftp)://[\s\S]*?)/", url)
#             url = url[0] + rs
#
#             logger.info(f"HTTP status code:302, Redirect to {url}")
#
#         response = httpx.head(url=url, headers=Headers, follow_redirects=False, verify=False,
#                               proxyServer=getProxy())  # 再访问一次
#
#     return url
class DownloadWorker:
    """只能出卖劳动力的最底层工作者"""

    def __init__(self, start, process, end, client: httpx.AsyncClient):
        self.startPos = start
        self.process = process
        self.endPos = end

        self.client = client


class DownloadTask(QThread):
    """TaskManager"""

    taskInited = Signal()  # 线程初始化成功
    # processChange = Signal(str)  # 目前进度 且因为C++ int最大值仅支持到2^31 PyQt又没有Qint类 故只能使用str代替
    workerInfoChange = Signal(list)  # 目前进度 v3.2版本引进了分段式进度条
    taskFinished = Signal()  # 内置信号的不好用
    gotWrong = Signal(str)  # 😭 我出问题了

    def __init__(self, url, maxBlockNum: int = 8, filePath=None, fileName=None, parent=None):
        super().__init__(parent)

        self.process = 0
        self.url = url
        self.fileName = fileName
        self.filePath = filePath
        self.maxBlockNum = maxBlockNum
        self.workers: list[DownloadWorker] = []
        self.tasks: list[Task] = []

        self.client = httpx.AsyncClient(headers=Headers, verify=False,
                                        proxy=getProxy(), limits=httpx.Limits(max_connections=256))

        self.__tempThread = Thread(target=self.__getLinkInfo, daemon=True)  # TODO 获取文件名和文件大小的线程等信息, 暂时使用线程方式
        self.__tempThread.start()

    def __reassignWorker(self):

        # 找到剩余进度最多的线程
        maxRemainder = 0
        maxRemainderWorkerProcess = 0
        maxRemainderWorkerEnd = 0
        maxRemainderWorker: DownloadWorker = None

        for i in self.workers:
            if (i.endPos - i.process) > maxRemainder:  # TODO 其实逻辑有一点问题, 但是影响不大
                maxRemainderWorkerProcess = i.process
                maxRemainderWorkerEnd = i.endPos
                maxRemainder = (maxRemainderWorkerEnd - maxRemainderWorkerProcess)
                maxRemainderWorker = i

        if maxRemainderWorker and maxRemainder > cfg.maxReassignSize.value * 1048576:  # 转换成 MB
            # 平均分配工作量
            baseShare = maxRemainder // 2
            remainder = maxRemainder % 2

            maxRemainderWorker.endPos = maxRemainderWorkerProcess + baseShare + remainder  # 直接修改好像也不会怎么样

            # 安配新的工人
            s_pos = maxRemainderWorkerProcess + baseShare + remainder + 1

            newWorker = DownloadWorker(s_pos, s_pos, maxRemainderWorkerEnd, self.client)

            newTask = self.loop.create_task(self.__handleWorker(newWorker))

            self.workers.insert(self.workers.index(maxRemainderWorker) + 1, newWorker)
            self.tasks.append(newTask)

            logger.info(
                f"Task{self.fileName} 分配新线程成功, 剩余量：{getReadableSize(maxRemainder)}，修改后的EndPos：{maxRemainderWorker.endPos}，新线程：{newWorker}，新线程的StartPos：{s_pos}")

        else:
            logger.info(
                f"Task{self.fileName} 欲分配新线程失败, 剩余量小于最小分块大小, 剩余量：{getReadableSize(maxRemainder)}")

    def __clacDivisionalRange(self):
        step = self.fileSize // self.maxBlockNum  # 每块大小
        arr = list(range(0, self.fileSize, step))

        # 否则线程数可能会不按预期地少一个
        if self.fileSize % self.maxBlockNum == 0:
            arr.append(self.fileSize)

        step_list = []

        for i in range(len(arr) - 1):  #

            s_pos, e_pos = arr[i], arr[i + 1] - 1
            step_list.append([s_pos, e_pos])

        step_list[-1][-1] = self.fileSize - 1  # 修正

        return step_list

    def __getLinkInfo(self):
        try:
            self.url, self.fileName, self.fileSize = getLinkInfo(self.url, Headers, self.fileName)

            if self.fileSize:
                self.ableToParallelDownload = True
            else:
                self.ableToParallelDownload = False  # TODO 处理无法并行下载的情况

            # 获取文件路径
            if not self.filePath and Path(self.filePath).is_dir() == False:
                self.filePath = Path.cwd()

            else:
                self.filePath = Path(self.filePath)
                if not self.filePath.exists():
                    self.filePath.mkdir()

            self.taskInited.emit()

        except Exception as e:  # 重试也没用
            self.gotWrong.emit(str(e))

    def __loadWorkers(self):
        # 如果 .ghd 文件存在，读取并解析二进制数据
        filePath = Path(f"{self.filePath}/{self.fileName}.ghd")
        if filePath.exists():
            try:
                with open(filePath, "rb") as f:
                    while True:
                        data = f.read(24)  # 每个 worker 有 3 个 64 位的无符号整数，共 24 字节

                        if not data:
                            break

                        start, process, end = struct.unpack("<QQQ", data)
                        self.workers.append(
                            DownloadWorker(start, process, end, self.client))

            except Exception as e:
                logger.error(f"Failed to load workers: {e}")
                stepList = self.__clacDivisionalRange()

                for i in range(self.maxBlockNum):
                    self.workers.append(
                        DownloadWorker(stepList[i][0], stepList[i][0], stepList[i][1], self.client))
        else:
            stepList = self.__clacDivisionalRange()

            for i in range(self.maxBlockNum):
                self.workers.append(
                    DownloadWorker(stepList[i][0], stepList[i][0], stepList[i][1], self.client))

    async def __handleWorker(self, worker: DownloadWorker):
        if worker.process < worker.endPos:  # 因为可能会创建空线程
            finished = False
            while not finished:
                try:
                    download_headers = Headers.copy()
                    download_headers["range"] = f"bytes={worker.process}-{worker.endPos}"  # 添加范围

                    async with worker.client.stream(url=self.url, headers=download_headers, timeout=30,
                                                    method="GET") as res:
                        async for chunk in res.aiter_raw(chunk_size=65536):  # aiter_content 的单位是字节, 即每64K写一次文件
                            if worker.endPos <= worker.process:
                                break
                            if chunk:
                                self.file.seek(worker.process)
                                self.file.write(chunk)
                                worker.process += 65536

                    if worker.process >= worker.endPos:
                        worker.process = worker.endPos

                    finished = True

                except httpx.HTTPError as e:
                    logger.info(
                        f"Task: {self.fileName}, Thread {worker} is reconnecting to the server, Error: {repr(e)}")

                    self.gotWrong.emit(repr(e))

                    await asyncio.sleep(5)

            worker.process = worker.endPos
        self.__reassignWorker()

    async def __supervisor(self):
        """实时统计进度并写入历史记录文件"""

        while not self.process == self.fileSize:

            self.ghdFile.seek(0)
            info = []
            self.process = 0

            for i in self.workers:
                info.append({"start": i.startPos, "process": i.process, "end": i.endPos})

                self.process += (i.process - i.startPos + 1)

                # 保存 workers 信息为二进制格式
                data = struct.pack("<QQQ", i.startPos, i.process, i.endPos)
                self.ghdFile.write(data)

            self.ghdFile.flush()
            self.ghdFile.truncate()

            self.workerInfoChange.emit(info)

            await asyncio.sleep(1)

    async def __main(self):
        try:
            # 打开下载文件
            self.file = open(f"{self.filePath}/{self.fileName}", "rb+")

            # 启动 Worker
            for i in self.workers:
                logger.debug(f"Task {self.fileName}, starting the thread {i}...")

                _ = asyncio.create_task(self.__handleWorker(i))

                self.tasks.append(_)

            self.ghdFile = open(f"{self.filePath}/{self.fileName}.ghd", "wb")
            self.supervisorTask = asyncio.create_task(self.__supervisor())

            # 仅仅需要等待 supervisorTask
            try:
                await self.supervisorTask  # supervisorTask 被 cancel 后，会抛出 CancelledError, 所以之后的代码不会执行
            except asyncio.CancelledError:
                await self.client.aclose()

            # 关闭
            await self.client.aclose()

            self.file.close()
            self.ghdFile.close()

            if self.process == self.fileSize:
                # 删除历史记录文件
                try:
                    Path(f"{self.filePath}/{self.fileName}.ghd").unlink()

                except Exception as e:
                    logger.error(f"Failed to delete the history file, please delete it manually. Err: {e}")

                logger.info(f"Task {self.fileName} finished!")

                self.taskFinished.emit()

        except Exception as e:
            self.gotWrong.emit(repr(e))

    def stop(self):
        for task in self.tasks:
            task.cancel()

        # 关闭
        try:
            self.supervisorTask.cancel()
        finally:
            self.file.close()
            self.ghdFile.close()

        while not all(task.done() for task in self.tasks):  # 等待所有任务完成
            for task in self.tasks:
                try:
                    task.cancel()
                except RuntimeError:
                    pass
                except Exception as e:
                    raise e

            time.sleep(0.05)

    # @retry(3, 0.1)
    def run(self):
        self.__tempThread.join()

        # 创建空文件
        Path(f"{self.filePath}/{self.fileName}").touch()

        # TODO 发消息给主线程
        if not self.ableToParallelDownload:
            self.maxBlockNum = 1

        # 加载分块
        self.__loadWorkers()

        # 主逻辑, 使用事件循环启动异步任务
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        try:
            self.loop.run_until_complete(self.__main())
        except asyncio.CancelledError as e:
            print(e)
        finally:
            self.loop.run_until_complete(self.loop.shutdown_asyncgens())
            self.loop.close()
