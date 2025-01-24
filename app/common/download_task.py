import asyncio
import re
import struct
import sys
import time
from asyncio import Task
from pathlib import Path
from threading import Thread

import aiofiles
import aiohttp
from PySide6.QtCore import QThread, Signal
from app.common.config import cfg
from app.common.methods import getProxy, getReadableSize, getLinkInfo
from loguru import logger


class DownloadWorker:
    """只能出卖劳动力的最底层工作者"""

    __slots__ = [
        'url', 'startPos', 'completedSize', 'endPos', 'headers', 'fileName',
        'session', 'gotWrong', 'file', 'lock', 'smoothFactor', 'dynamicChunkSize',
        'task', 'minimumChunkSize', 'response'
    ]

    def __init__(
            self,
            url,
            start, completedSize, end,
            session: aiohttp.ClientSession, headers,
            fileName, gotWrong_Signal,
            asyncFd, asyncLock
    ):
        self.url = url
        self.startPos = start
        self.completedSize = completedSize
        self.endPos = end

        self.headers = headers
        self.fileName = fileName

        self.session = session
        self.response = None
        self.gotWrong = gotWrong_Signal

        self.file = asyncFd
        self.lock = asyncLock

        self.smoothFactor = 0.1
        self.dynamicChunkSize = 65536
        self.minimumChunkSize = 1024

        self.task = None

    def calcChunkSize(self, chunkSize):
        if chunkSize < self.dynamicChunkSize * 0.8:  # 容错: 读取到的chunk大小保持在动态大小的 0.8~1 之间
            self.dynamicChunkSize -= int(self.dynamicChunkSize * self.smoothFactor)
        if chunkSize == self.dynamicChunkSize:
            self.dynamicChunkSize += int(self.dynamicChunkSize * self.smoothFactor)
        self.dynamicChunkSize = max(self.dynamicChunkSize, self.minimumChunkSize)  # 避免动态分块大小过小

    def __str__(self):
        return (f'{type(self).__name__}'
                f'(start={repr(self.startPos)}, '
                f'completedSize={repr(self.completedSize)}, '
                f'endPos={repr(self.endPos)})')

    __repr__ = __str__

    @property
    def size(self):
        return self.endPos - self.startPos + 1

    @property
    def noSize(self):
        return self.size == 0  # 所以,如果表示无法并行下载,应该把endPos设置为-1

    @property
    def remain(self):
        return self.size - self.completedSize

    @property
    def progress(self):
        return self.startPos + self.completedSize

    @property
    def finished(self):
        return self.progress >= self.endPos

    async def update(self, chunk):
        if not chunk: return False

        self.completedSize += len(chunk)

        async with self.lock:
            await self.file.seek(self.progress)
            await self.file.write(chunk)

        if self.completedSize > self.size:  # 避免进度超过文件总大小
            self.completedSize = self.size

        if self.noSize:
            return self.__isResponseAlived(self.response)
        else:
            return self.finished

    def __isResponseAlived(self, response):  # 实则是检查服务器是否结束了连接
        return response.connection and not response.connection.transport.is_closing()

    async def download(self):
        if self.progress > self.endPos:
            return
        finished = False  # 下载结束标志
        noDataTime = None  # 没有收到数据的起始时间
        while not finished:  # 整体逻辑,如果没有结束那么一直尝试继续下载
            try:  # 如果发生错误,那么会重新连接服务器
                headers = self.headers.copy()
                headers['range'] = f'bytes={self.progress}-{self.endPos}'
                self.response = None
                async with self.session.get(self.url, headers=headers, proxy=getProxy(), timeout=30) as response:
                    response.raise_for_status()  # 如果状态码不是 2xx，抛出异常
                    self.response = response
                    while not finished:  # 循环读取
                        chunk = await response.content.read(self.dynamicChunkSize)
                        if not chunk:
                            if noDataTime:  # 否则检查是否已经超过5秒没有收到数据
                                if time.time() - noDataTime > 5:
                                    raise TimeoutError('No data received for 5 seconds')  # 超过5秒并抛出错误后,循环会再次引导程序连接服务器
                            else:  # 如果是第一次没有收到数据,那么记录时间
                                noDataTime = time.time()
                        else:
                            noDataTime = None
                        finished = await self.update(chunk)  # update函数在写入文件和更新进度后同时返回是否结束
                        self.calcChunkSize(len(chunk))  # 更新动态分块大小

            except (aiohttp.ClientError, TimeoutError) as e:
                logger.info(
                    f"Task: {self.fileName}, Thread {self} is reconnecting to the server, Error: {repr(e)}")

    def startDownload(self):
        self.task = asyncio.create_task(self.download())
        return self.task

    def stopDownload(self):
        self.task.cancel()


class DownloadTask(QThread):
    """TaskManager"""

    taskInited = Signal(bool)  # 线程初始化成功, 并传递是否支持并行下载的信息
    # processChange = Signal(str)  # 目前进度 且因为C++ int最大值仅支持到2^31 PyQt又没有Qint类 故只能使用str代替
    workerInfoChanged = Signal(list)  # 目前进度 v3.2版本引进了分段式进度条
    speedChanged = Signal(int)  # 平均速度 因为 autoSpeedUp 功能需要实时计算平均速度 v3.4.4 起移入后端计算速度, 每秒速度可能超过 2^31 Bytes 吗？
    taskFinished = Signal()  # 内置信号的不好用
    gotWrong = Signal(str)  # 😭 我出问题了

    def __init__(self, url, headers, preTaskNum: int = 8, filePath=None, fileName=None,
                 autoSpeedUp=cfg.autoSpeedUp.value, parent=None):
        super().__init__(parent)

        self.aioLock = asyncio.Lock()
        self.progress = 0
        self.url = url
        self.headers = headers
        self.fileName = fileName
        self.filePath = filePath
        self.preBlockNum = preTaskNum
        self.autoSpeedUp = autoSpeedUp
        self.ableToParallelDownload: bool

        self.workers: list[DownloadWorker] = []
        self.tasks: list[Task] = []
        self.historySpeed = [0] * 10  # 历史速度 10 秒内的平均速度

        self.session = aiohttp.ClientSession()

        self.__tempThread = Thread(target=self.__getLinkInfo, daemon=True)  # TODO 获取文件名和文件大小的线程等信息, 暂时使用线程方式
        self.__tempThread.start()

    def create_new_worker(self, startPos: int, endPos: int, completedSize: int):
        return DownloadWorker(
            self.url, startPos, completedSize, endPos,
            self.session, self.headers, self.fileName,
            self.gotWrong, self.file, self.aioLock)

    def __reassignWorker(self):

        # 找到剩余进度最多的线程
        maxRemainderWorker: DownloadWorker = None
        index = 0
        for i, w in enumerate(self.workers):
            if w.remain > maxRemainderWorker.remain:  # 其实逻辑有一点问题, 但是影响不大
                maxRemainderWorker = w  # Update by LS2024: 我也不知道现在对不对
                index = i

        maxRemainder = maxRemainderWorker.remain
        maxRemainderWorkerProcess = maxRemainderWorker.progress
        maxRemainderWorkerEnd = maxRemainderWorker.endPos

        if maxRemainderWorker and maxRemainder > cfg.maxReassignSize.value * 1048576:  # 从MB转换
            # 平均分配工作量
            baseShare = maxRemainder // 2
            remainder = maxRemainder % 2

            maxRemainderWorker.endPos = maxRemainderWorkerProcess + baseShare + remainder  # 直接修改好像也不会怎么样

            # 安配新的工人
            startPos = maxRemainderWorker.endPos
            newWorker = self.create_new_worker(startPos, maxRemainderWorkerEnd, 0)

            newTask = newWorker.startDownload()

            self.workers.insert(index + 1, newWorker)
            self.tasks.append(newTask)

            logger.info(
                f"Task{self.fileName} 分配新线程成功, 剩余量：{getReadableSize(maxRemainder)}，修改后的EndPos：{maxRemainderWorker.endPos}，新线程：{newWorker}，新线程的StartPos：{startPos}")

        else:
            logger.info(
                f"Task{self.fileName} 欲分配新线程失败, 剩余量小于最小分块大小, 剩余量：{getReadableSize(maxRemainder)}")

    def __calcDivisionalRange(self):
        step = self.fileSize // self.preBlockNum  # 每块大小
        arr = list(range(0, self.fileSize, step))

        # 否则线程数可能会不按预期地少一个
        if self.fileSize % self.preBlockNum == 0:
            arr.append(self.fileSize)

        stepList = []

        for i in range(len(arr) - 1):  #

            startPos, endPos = arr[i], arr[i + 1] - 1
            stepList.append([startPos, endPos])

        stepList[-1][-1] = self.fileSize - 1  # 修正

        return stepList

    def __getLinkInfo(self):
        try:
            self.url, self.fileName, self.fileSize = getLinkInfo(self.url, self.headers, self.fileName)

            if self.fileSize:
                self.ableToParallelDownload = True
            else:
                self.ableToParallelDownload = False  # 处理无法并行下载的情况

            # 获取文件路径
            if not self.filePath and Path(self.filePath).is_dir() == False:
                self.filePath = Path.cwd()

            else:
                self.filePath = Path(self.filePath)
                if not self.filePath.exists():
                    self.filePath.mkdir()

        except Exception as e:  # 重试也没用
            self.gotWrong.emit(str(e))

    def __loadWorkers(self):
        if not self.ableToParallelDownload:
            # 如果无法并行下载，创建一个单线程的 worker
            self.workers.append(self.create_new_worker(0, -1, 0))  # -1对于Worker来说表示无法获取大小
            return

        # 如果 .ghd 文件存在，读取并解析二进制数据
        filePath = Path(f"{self.filePath}/{self.fileName}.ghd")
        if filePath.exists():
            try:
                with open(filePath, "rb") as f:
                    while True:
                        data = f.read(24)  # 每个 worker 有 3 个 64 位的无符号整数，共 24 字节

                        if not data:
                            break

                        start, end, completedSize = struct.unpack("<QQQ", data)
                        self.workers.append(self.create_new_worker(start, end, completedSize))

            except Exception as e:
                logger.error(f"Failed to load workers: {e}")
                stepList = self.__calcDivisionalRange()

                for i in range(self.preBlockNum):
                    self.workers.append(
                        DownloadWorker(stepList[i][0], stepList[i][0], stepList[i][1], self.session))
        else:
            stepList = self.__calcDivisionalRange()

            for i in range(self.preBlockNum):
                self.workers.append(
                    DownloadWorker(stepList[i][0], stepList[i][0], stepList[i][1], self.session))

    async def __supervisor(self):
        """实时统计进度并写入历史记录文件"""
        for i in self.workers:
            self.progress += (i.progress - i.startPos + 1)
            LastProcess = self.progress

        if self.ableToParallelDownload:
            if self.autoSpeedUp:
                # 初始化变量
                maxSpeedPerConnect = 1  # 防止除以0
                additionalTaskNum = len(self.tasks)  # 最初为计算每个线程的平均速度
                formerAvgSpeed = 0  # 提速之前的平均速度
                duringTime = 0  # 计算平均速度的时间间隔, 为 10 秒

            while not self.progress == self.fileSize:

                info = []
                # 记录每块信息
                await self.ghdFile.seek(0)

                self.progress = 0

                for i in self.workers:
                    info.append({"start": i.startPos, "progress": i.progress, "end": i.endPos})

                    self.progress += (i.progress - i.startPos + 1)

                    # 保存 workers 信息为二进制格式
                    data = struct.pack("<QQQ", i.startPos, i.endPos, i.completedSize)
                    await self.ghdFile.write(data)

                await self.ghdFile.flush()
                await self.ghdFile.truncate()

                self.workerInfoChanged.emit(info)

                # 计算速度
                speed = (self.progress - LastProcess)
                # print(f"speed: {speed}, progress: {self.progress}, LastProcess: {LastProcess}")
                LastProcess = self.progress
                self.historySpeed.pop(0)
                self.historySpeed.append(speed)
                avgSpeed = sum(self.historySpeed) / 10

                self.speedChanged.emit(avgSpeed)

                # print(f"avgSpeed: {avgSpeed}, historySpeed: {self.historySpeed}")

                if self.autoSpeedUp:
                    if duringTime < 10:
                        duringTime += 1
                    else:
                        duringTime = 0

                        speedPerConnect = avgSpeed / len(self.tasks)
                        # print(f"taskNum: {len(self.tasks)}, speedPerConnect: {speedPerConnect}, maxSpeedPerConnect: {maxSpeedPerConnect}")

                        if speedPerConnect > maxSpeedPerConnect:
                            maxSpeedPerConnect = speedPerConnect

                        # if maxSpeedPerConnect <= 1:
                        #     await asyncio.sleep(1)
                        #     continue

                        # logger.debug(f"当前效率: {(avgSpeed - formerAvgSpeed) / additionalTaskNum / maxSpeedPerConnect}, speed: {speed}, formerAvgSpeed: {formerAvgSpeed}, additionalTaskNum: {additionalTaskNum}, maxSpeedPerConnect: {maxSpeedPerConnect}")

                        if (avgSpeed - formerAvgSpeed) / additionalTaskNum / maxSpeedPerConnect >= 0.85:
                            #  新增加线程的效率 >= 0.85 时，新增线程
                            # logger.debug(f'自动提速增加新线程, 当前效率: {(avgSpeed - formerAvgSpeed) / additionalTaskNum / maxSpeedPerConnect}')
                            formerAvgSpeed = avgSpeed
                            additionalTaskNum = 4

                            if len(self.tasks) < 253:
                                for i in range(4):
                                    self.__reassignWorker()  # 新增线程

                await asyncio.sleep(1)
        else:
            while not self.ableToParallelDownload:  # 实际上此时 self.ableToParallelDownload 用于记录任务是否完成
                self.progress = 0

                for i in self.workers:
                    self.progress += (i.progress - i.startPos + 1)

                self.workerInfoChanged.emit([])

                # 计算速度
                speed = (self.progress - LastProcess)
                LastProcess = self.progress
                self.historySpeed.pop(0)
                self.historySpeed.append(speed)
                avgSpeed = sum(self.historySpeed) / 10

                self.speedChanged.emit(avgSpeed)

                await asyncio.sleep(1)

    async def __main(self):
        try:
            # 打开下载文件
            self.file = await aiofiles.open(f"{self.filePath}/{self.fileName}", "rb+")

            if self.ableToParallelDownload:
                for i in self.workers:  # 启动 Worker
                    logger.debug(f"Task {self.fileName}, starting the thread {i}...")

                    _ = i.startDownload()

                    self.tasks.append(_)

                self.ghdFile = await aiofiles.open(f"{self.filePath}/{self.fileName}.ghd", "wb")
            else:
                logger.debug(f"Task {self.fileName}, starting single thread...")
                _ = self.workers[0].startDownload()
                self.tasks.append(_)

            self.supervisorTask = asyncio.create_task(self.__supervisor())

            # 仅仅需要等待 supervisorTask
            try:
                await self.supervisorTask
            except asyncio.CancelledError:
                await self.session.close()

            # 关闭
            await self.session.close()

            await self.file.close()

            if self.fileSize:  # 事实上表示 ableToParallelDownload 为 False
                await self.ghdFile.close()
            else:
                logger.info(f"Task {self.fileName} finished!")
                self.taskFinished.emit()

            if self.progress == self.fileSize:
                # 下载完成时删除历史记录文件, 防止没下载完时误删
                try:
                    Path(f"{self.filePath}/{self.fileName}.ghd").unlink()

                except Exception as e:
                    logger.error(f"Failed to delete the history file, please delete it manually. Err: {e}")

                logger.info(f"Task {self.fileName} finished!")

                self.taskFinished.emit()

        except Exception as e:
            self.gotWrong.emit(repr(e))

    def stop(self):
        for worker in self.workers:
            worker.stopDownload()
        for task in self.tasks:
            task.cancel()

        asyncio.get_running_loop().run_until_complete(self.session.close())

        # 关闭
        try:
            self.supervisorTask.cancel()
        finally:

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

        # 检验文件合法性并自动重命名
        if sys.platform == "win32":
            self.fileName = re.sub(re.escape(r'\/:*?"<>|'), '', self.fileName)  # 去除Windows系统不允许的字符
        if len(self.fileName) > 255:
            self.fileName = self.fileName[:255]

        Path(f"{self.filePath}/{self.fileName}").touch()

        # 任务初始化完成
        if self.ableToParallelDownload:
            self.taskInited.emit(True)
        else:
            self.taskInited.emit(False)
            self.preBlockNum = 1

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
