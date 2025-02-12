import asyncio
import struct
import sys
import time
from asyncio import Task
from os import system
from pathlib import Path
from threading import Thread

import aiofiles
import httpx
from PySide6.QtCore import QThread, Signal
from loguru import logger

from app.common.config import cfg
from app.common.methods import getProxy, getReadableSize, getLinkInfo


class DownloadWorker:
    """只能出卖劳动力的最底层工作者"""

    def __init__(self, start, progress, end, client: httpx.AsyncClient):
        self.startPos = start
        self.progress = progress
        self.endPos = end

        self.client = client


class DownloadTask(QThread):
    """ Task Manager
        self.fileSize == -1 表示自动获取; == 0 表示不能并行下载; else 表示正常"""

    taskInited = Signal(bool)  # 线程初始化成功, 并传递是否支持并行下载的信息
    # processChange = Signal(str)  # 目前进度 且因为C++ int最大值仅支持到2^31 PyQt又没有Qint类 故只能使用str代替
    workerInfoChanged = Signal(list)  # 目前进度 v3.2版本引进了分段式进度条
    speedChanged = Signal(int)  # 平均速度 因为 autoSpeedUp 功能需要实时计算平均速度 v3.4.4 起移入后端计算速度, 每秒速度可能超过 2^31 Bytes 吗？
    taskFinished = Signal()  # 内置信号的不好用
    gotWrong = Signal(str)  # 😭 我出问题了

    def __init__(self, url, headers, preTaskNum: int = 8, filePath:str=None, fileName:str=None, autoSpeedUp:bool=False, fileSize:int=-1, parent=None):
        super().__init__(parent)

        self.aioLock = asyncio.Lock()
        self.progress = 0
        self.url = url
        self.headers = headers
        self.fileName = fileName
        self.filePath = filePath
        self.preBlockNum = preTaskNum
        self.autoSpeedUp = autoSpeedUp
        self.fileSize = fileSize
        self.ableToParallelDownload:bool

        self.workers: list[DownloadWorker] = []
        self.tasks: list[Task] = []
        self.historySpeed = [0] * 10  # 历史速度 10 秒内的平均速度

        self.client = httpx.AsyncClient(headers=headers, verify=False,
                                        proxy=getProxy(), limits=httpx.Limits(max_connections=256))

        self.__initThread = Thread(target=self.__initTask, daemon=True)  # TODO 获取文件名和文件大小的线程等信息, 暂时使用线程方式
        self.__initThread.start()

    def __reassignWorker(self):

        # 找到剩余进度最多的线程
        maxRemainder = 0
        maxRemainderWorkerProcess = 0
        maxRemainderWorkerEnd = 0
        maxRemainderWorker: DownloadWorker = None

        for i in self.workers:
            if (i.endPos - i.progress) > maxRemainder:  # 其实逻辑有一点问题, 但是影响不大
                maxRemainderWorkerProcess = i.progress
                maxRemainderWorkerEnd = i.endPos
                maxRemainder = (maxRemainderWorkerEnd - maxRemainderWorkerProcess)
                maxRemainderWorker = i

        if maxRemainderWorker and maxRemainder > cfg.maxReassignSize.value * 1048576:  # 转换成 MB
            # 平均分配工作量
            baseShare = maxRemainder // 2
            remainder = maxRemainder % 2

            maxRemainderWorker.endPos = maxRemainderWorkerProcess + baseShare + remainder  # 直接修改好像也不会怎么样

            # 安配新的工人
            startPos = maxRemainderWorkerProcess + baseShare + remainder + 1

            newWorker = DownloadWorker(startPos, startPos, maxRemainderWorkerEnd, self.client)

            newTask = self.loop.create_task(self.__handleWorker(newWorker))

            self.workers.insert(self.workers.index(maxRemainderWorker) + 1, newWorker)
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

    def __initTask(self):
        """获取链接信息并初始化线程"""
        try:
            if self.fileSize == -1 or not self.fileName:
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

            # 检验文件合法性并自动重命名
            if sys.platform == "win32":
                self.fileName = ''.join([i for i in self.fileName if i not in r'\/:*?"<>|'])  # 去除Windows系统不允许的字符
            if len(self.fileName) > 255:
                self.fileName = self.fileName[:255]

            if sys.platform == "win32":
                system(f'fsutil file createnew "{self.filePath}/{self.fileName}" {self.fileSize}')
            else:
                Path(f"{self.filePath}/{self.fileName}").touch()

            # 任务初始化完成
            if self.ableToParallelDownload:
                self.taskInited.emit(True)
            else:
                self.taskInited.emit(False)
                self.preBlockNum = 1

        except Exception as e:  # 重试也没用
            self.gotWrong.emit(repr(e))

    def __loadWorkers(self):
        if not self.ableToParallelDownload:
            # 如果无法并行下载，创建一个单线程的 worker
            self.workers.append(DownloadWorker(0, 0, 1, self.client))
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

                        start, process, end = struct.unpack("<QQQ", data)
                        self.workers.append(
                            DownloadWorker(start, process, end, self.client))

            except Exception as e:
                logger.error(f"Failed to load workers: {e}")
                stepList = self.__calcDivisionalRange()

                for i in range(self.preBlockNum):
                    self.workers.append(
                        DownloadWorker(stepList[i][0], stepList[i][0], stepList[i][1], self.client))
        else:
            stepList = self.__calcDivisionalRange()

            for i in range(self.preBlockNum):
                self.workers.append(
                    DownloadWorker(stepList[i][0], stepList[i][0], stepList[i][1], self.client))


    # 主下载逻辑
    async def __handleWorker(self, worker: DownloadWorker):
        if worker.progress < worker.endPos:  # 因为可能会创建空线程
            finished = False
            while not finished:
                try:
                    workingRangeHeaders = self.headers.copy()

                    workingRangeHeaders["range"] = f"bytes={worker.progress}-{worker.endPos}"  # 添加范围

                    async with worker.client.stream(url=self.url, headers=workingRangeHeaders, timeout=30,
                                                    method="GET") as res:
                        async for chunk in res.aiter_bytes():
                            if worker.endPos <= worker.progress:
                                break
                            if chunk:
                                async with self.aioLock:
                                    await self.file.seek(worker.progress)
                                    await self.file.write(chunk)
                                    _ = len(chunk)
                                    worker.progress += _
                                    cfg.globalSpeed += _
                                    if cfg.speedLimitation.value:
                                        if cfg.globalSpeed >= cfg.speedLimitation.value:
                                            await asyncio.sleep(1)  # 在锁里面睡，只阻塞 worker, 不阻塞 supervisor

                    if worker.progress >= worker.endPos:
                        worker.progress = worker.endPos

                    finished = True

                except httpx.HTTPError as e:
                    logger.info(
                        f"Task: {self.fileName}, Thread {worker} is reconnecting to the server, Error: {repr(e)}")

                    self.gotWrong.emit(repr(e))

                    await asyncio.sleep(5)  # 5s 后重试

            worker.progress = worker.endPos

        self.__reassignWorker()

    async def __handleWorkerWhenUnableToParallelDownload(self, worker: DownloadWorker):
        if worker.progress < worker.endPos:  # 因为可能会创建空线程
            finished = False
            while not finished:
                try:
                    WorkingRangeHeaders = self.headers.copy()
                    async with worker.client.stream(url=self.url, headers=WorkingRangeHeaders, timeout=30,
                                                    method="GET") as res:
                        async for chunk in res.aiter_bytes():

                            if chunk:
                                await self.file.seek(worker.progress)
                                await self.file.write(chunk)
                                _ = len(chunk)
                                worker.progress += _
                                cfg.globalSpeed += _
                                if cfg.speedLimitation.value:
                                    if cfg.globalSpeed >= cfg.speedLimitation.value:
                                        await asyncio.sleep(1)  # 在锁里面睡，只阻塞 worker, 不阻塞 supervisor

                    self.ableToParallelDownload = True # 事实上用来表示任务已经完成

                    finished = True

                except httpx.HTTPError as e:
                    logger.info(
                        f"Task: {self.fileName}, Thread {worker} is reconnecting to the server, Error: {repr(e)}")

                    self.gotWrong.emit(repr(e))

                    await asyncio.sleep(5)

            worker.progress = worker.endPos

    async def __supervisor(self):
        """实时统计进度并写入历史记录文件"""
        for i in self.workers:
            self.progress += (i.progress - i.startPos + 1)
            LastProcess = self.progress

        if self.ableToParallelDownload:
            if self.autoSpeedUp:
                # 初始化变量
                maxSpeedPerConnect = 1 # 防止除以0
                additionalTaskNum = len(self.tasks) # 最初为计算每个线程的平均速度
                formerAvgSpeed = 0 # 提速之前的平均速度
                duringTime = 0 # 计算平均速度的时间间隔, 为 10 秒

            while not self.progress == self.fileSize:

                info = []
                # 记录每块信息
                await self.ghdFile.seek(0)

                self.progress = 0

                for i in self.workers:
                    info.append({"start": i.startPos, "progress": i.progress, "end": i.endPos})

                    self.progress += (i.progress - i.startPos + 1)

                    # 保存 workers 信息为二进制格式
                    data = struct.pack("<QQQ", i.startPos, i.progress, i.endPos)
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
                        if speedPerConnect > maxSpeedPerConnect:
                            maxSpeedPerConnect = speedPerConnect
                            _ = (0.85 * maxSpeedPerConnect * additionalTaskNum) + formerAvgSpeed

                        # if maxSpeedPerConnect <= 1:
                        #     await asyncio.sleep(1)
                        #     continue

                        # logger.debug(f"当前效率: {(avgSpeed - formerAvgSpeed) / additionalTaskNum / maxSpeedPerConnect}, speed: {speed}, formerAvgSpeed: {formerAvgSpeed}, additionalTaskNum: {additionalTaskNum}, maxSpeedPerConnect: {maxSpeedPerConnect}")
                        
                        #原公式：(avgSpeed - formerAvgSpeed) / additionalTaskNum / maxSpeedPerConnect >= 0.85
                        #然后将不等号左边的计算全部移到右边
                        if avgSpeed >= _:
                            #  新增加线程的效率 >= 0.85 时，新增线程
                            # logger.debug(f'自动提速增加新线程, 当前效率: {(avgSpeed - formerAvgSpeed) / additionalTaskNum / maxSpeedPerConnect}')
                            formerAvgSpeed = avgSpeed
                            additionalTaskNum = 4
                            _ = (0.85 * maxSpeedPerConnect * additionalTaskNum) + formerAvgSpeed

                            if len(self.tasks)  < 253:
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

                    _ = asyncio.create_task(self.__handleWorker(i))

                    self.tasks.append(_)

                self.ghdFile = await aiofiles.open(f"{self.filePath}/{self.fileName}.ghd", "wb")
            else:
                logger.debug(f"Task {self.fileName}, starting single thread...")
                _ = asyncio.create_task(self.__handleWorkerWhenUnableToParallelDownload(self.workers[0]))
                self.tasks.append(_)

            self.supervisorTask = asyncio.create_task(self.__supervisor())

            # 仅仅需要等待 supervisorTask
            try:
                await self.supervisorTask
            except asyncio.CancelledError:
                await self.client.aclose()

            # 关闭
            await self.client.aclose()

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
        for task in self.tasks:
            task.cancel()

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


    def run(self):
        self.__initThread.join()

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
