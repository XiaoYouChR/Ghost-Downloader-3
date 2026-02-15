import asyncio
import struct
import sys
import time
from pathlib import Path
from threading import Thread

import curl_cffi
from PySide6.QtCore import QThread, Signal
from loguru import logger

from app.common.config import cfg
from app.common.methods import getProxy, getReadableSize, getLinkInfo, createSparseFile


class DownloadWorker:
    """只能出卖劳动力的最底层工作者"""

    def __init__(self, start, progress, end):
        self.startPos = start
        self.progress = progress
        self.endPos = end


class MutiThreadContext:
    """多线程句柄，如果DownloadTask的方法需要使用多线程，则需要将该类作为参数传入"""

    def __init__(self, fileSize):
        self.workers: list[DownloadWorker] = []
        self.taskgroup = asyncio.TaskGroup()
        self.running_task_count: int = 0
        self.fileSize: int = fileSize
        self.done: bool = False


class DownloadTask(QThread):
    """Task Manager
    self.fileSize == -1 表示自动获取; == 0 表示不能并行下载; else 表示正常"""

    taskInited = Signal(bool)  # 线程初始化成功, 并传递是否支持并行下载的信息
    # processChange = Signal(str)  # 目前进度 且因为C++ int最大值仅支持到2^31 PyQt又没有Qint类 故只能使用str代替
    workerInfoChanged = Signal(list)  # 目前进度 v3.2版本引进了分段式进度条
    speedChanged = Signal(
        int
    )  # 平均速度 因为 autoSpeedUp 功能需要实时计算平均速度 v3.4.4 起移入后端计算速度, 每秒速度可能超过 2^31 Bytes 吗？
    taskFinished = Signal()  # 内置信号的不好用
    gotWrong = Signal(str)  # 😭 我出问题了

    def __init__(
        self,
        url,
        headers,
        preTaskNum: int = 8,
        filePath: str = None,
        fileName: str = None,
        autoSpeedUp: bool = False,
        fileSize: int = -1,
        parent=None,
    ):
        super().__init__(parent)

        self.progress = 0
        self.url = url
        self.headers = headers
        self.fileName = fileName
        self.filePath = filePath
        self.preBlockNum = preTaskNum
        self.autoSpeedUp = autoSpeedUp
        self.fileSize = fileSize
        self.ableToParallelDownload: bool

        self.historySpeed = [0] * 100  # 历史速度 10 秒内的平均速度

        proxy = getProxy()

        self.client = curl_cffi.AsyncSession(
            headers=headers,
            verify=cfg.SSLVerify.value,
            proxy=proxy,
            max_clients=256,
            trust_env=False,
            allow_redirects=True,
            impersonate="chrome",
            http_version="v3",
        )

        self.__initThread = Thread(
            target=self.__initTask, daemon=True
        )  # TODO 获取文件名和文件大小的线程等信息, 暂时使用线程方式
        self.__initThread.start()

    def __reassignWorker(self, context: MutiThreadContext):

        # 找到剩余进度最多的线程
        maxRemainder = 0
        maxRemainderWorkerProcess = 0
        maxRemainderWorkerEnd = 0
        maxRemainderWorker: DownloadWorker = None

        for i in context.workers:
            if (
                i.endPos - i.progress
            ) > maxRemainder:  # 其实逻辑有一点问题, 但是影响不大
                maxRemainderWorkerProcess = i.progress
                maxRemainderWorkerEnd = i.endPos
                maxRemainder = maxRemainderWorkerEnd - maxRemainderWorkerProcess
                maxRemainderWorker = i

        if (
            maxRemainderWorker and maxRemainder > cfg.maxReassignSize.value * 1048576
        ):  # 转换成 MB
            # 平均分配工作量
            baseShare = maxRemainder // 2
            remainder = maxRemainder % 2

            maxRemainderWorker.endPos = (
                maxRemainderWorkerProcess + baseShare + remainder
            )  # 直接修改好像也不会怎么样

            # 安配新的工人
            startPos = (
                maxRemainderWorkerProcess + baseShare + remainder + 1
            )  # 除以2向上取整

            newWorker = DownloadWorker(startPos, startPos, maxRemainderWorkerEnd)

            context.taskgroup.create_task(self.__handleWorker(newWorker, context))
            context.workers.insert(
                context.workers.index(maxRemainderWorker) + 1, newWorker
            )
            context.running_task_count += 1
            logger.info(
                f"Task{self.fileName} 分配新线程成功, 剩余量：{getReadableSize(maxRemainder)}，修改后的EndPos：{maxRemainderWorker.endPos}，新线程：{newWorker}，新线程的StartPos：{startPos}"
            )

        else:
            logger.info(
                f"Task{self.fileName} 欲分配新线程失败, 剩余量小于最小分块大小, 剩余量：{getReadableSize(maxRemainder)}"
            )


    def __calcDivisionalRange(self, context: MutiThreadContext):
        step = context.fileSize // self.preBlockNum  # 每块大小
        start = 0
        for i in range(self.preBlockNum - 1):
            end = start + step - 1
            yield DownloadWorker(start, start, end)
            start = end + 1

        yield DownloadWorker(start, start, context.fileSize - 1)


    def __initTask(self):
        """获取链接信息并初始化线程"""
        try:
            if self.fileSize == -1 or not self.fileName:
                self.url, self.fileName, self.fileSize = getLinkInfo(
                    self.url, self.headers, self.fileName
                )

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
                self.fileName = "".join(
                    [i for i in self.fileName if i not in r'\/:*?"<>|']
                )  # 去除Windows系统不允许的字符
            if len(self.fileName) > 255:
                self.fileName = self.fileName[:255]

            filePath = Path(f"{self.filePath}/{self.fileName}")

            if not filePath.exists():
                filePath.touch()
                try:
                    createSparseFile(filePath)
                except Exception as e:
                    logger.warning("创建稀疏文件失败", repr(e))

            # 任务初始化完成
            if self.ableToParallelDownload:
                self.taskInited.emit(True)
            else:
                self.taskInited.emit(False)
                self.preBlockNum = 1

        except Exception as e:  # 重试也没用
            self.gotWrong.emit(repr(e))

    def __loadWorkers(self, context: MutiThreadContext):
        """可续传的情况下读取已存在的 .ghd 文件"""
        # if not self.ableToParallelDownload:
        #     # 如果无法并行下载，创建一个单线程的 worker
        #     self.workers.append(DownloadWorker(0, 0, 1, self.client))
        #     return

        # 如果 .ghd 文件存在，读取并解析二进制数据
        filePath = Path(f"{self.filePath}/{self.fileName}.ghd")
        if filePath.exists():
            try:
                with open(filePath, "rb") as f:
                    while True:
                        data = f.read(
                            24
                        )  # 每个 worker 有 3 个 64 位的无符号整数，共 24 字节

                        if not data:
                            break

                        start, process, end = struct.unpack("<QQQ", data)
                        context.workers.append(DownloadWorker(start, process, end))

            except Exception as e:
                logger.error(f"Failed to load workers: {e}")

                for worker in self.__calcDivisionalRange(context):
                    context.workers.append(worker)
        else:

            for worker in self.__calcDivisionalRange(context):
                context.workers.append(worker)
            

    # 多线程主下载逻辑
    async def __handleWorker(self, worker: DownloadWorker, context: MutiThreadContext):
        logger.debug(
            f"{self.fileName} task is launching the worker {worker.startPos}-{worker.endPos}..."
        )
        if worker.progress < worker.endPos:  # 因为可能会创建空线程
            finished = False
            while not finished:
                try:
                    workingRangeHeaders = self.headers.copy()

                    workingRangeHeaders["range"] = (
                        f"bytes={worker.progress}-{worker.endPos}"  # 添加范围
                    )

                    res = await self.client.stream(
                        url=self.url,
                        headers=workingRangeHeaders,
                        timeout=30,
                        method="GET",
                    ).__aenter__()  # 直接使用async with暂停时会卡住，原因不明
                    try:
                        res: curl_cffi.Response
                        res.raise_for_status()
                        if res.status_code != 206:
                            raise Exception(
                                f"服务器拒绝了范围请求，状态码：{res.status_code}"
                            )
                        async for chunk in res.aiter_content():
                            if worker.endPos <= worker.progress:
                                break
                            if chunk:
                                self.file.seek(worker.progress)
                                self.file.write(chunk)
                                chunkSize = len(chunk)
                                worker.progress += chunkSize
                                cfg.globalSpeed += chunkSize
                                if cfg.speedLimitation.value:
                                    if cfg.globalSpeed >= cfg.speedLimitation.value:
                                        time.sleep(1)
                    finally:
                        # res: curl_cffi.Response
                        res.close()

                    if worker.progress >= worker.endPos:
                        worker.progress = worker.endPos

                    finished = True

                except Exception as e:
                    logger.info(
                        f"Task: {self.fileName}, Thread {worker} is reconnecting to the server, Error: {repr(e)}"
                    )

                    self.gotWrong.emit(repr(e))

                    await asyncio.sleep(5)

            worker.progress = worker.endPos

        if (
            not self.autoSpeedUp or context.running_task_count <= self.preBlockNum
        ):  # 如果开启了自动提速且添加了额外线程，则重新分配工作线程由自动提速控制
            self.__reassignWorker(context)
        context.running_task_count += 1

    async def __handleWorkerWhenUnableToParallelDownload(self):
        finished = False
        while not finished:
            # fix me: 单线程下载任务在重连后进度不正确，但直接将进度重置为0又会导致速度异常
            # self.progress = 0
            try:
                self.file.seek(0)
                WorkingRangeHeaders = self.headers.copy()
                async with self.client.stream(
                    url=self.url,
                    headers=WorkingRangeHeaders,
                    timeout=30,
                    method="GET",
                ) as res:
                    res.raise_for_status()
                    async for chunk in res.aiter_content():
                        if chunk:
                            self.file.write(chunk)
                            _ = len(chunk)
                            self.progress += _
                            cfg.globalSpeed += _
                            if cfg.speedLimitation.value:
                                if cfg.globalSpeed >= cfg.speedLimitation.value:
                                    time.sleep(1)

                self.ableToParallelDownload = True  # 事实上用来表示任务已经完成

                finished = True

            except Exception as e:
                logger.info(
                    f"Task: {self.fileName}, Thread {self} is reconnecting to the server, Error: {repr(e)}"
                )

                self.gotWrong.emit(repr(e))

                await asyncio.sleep(5)

        # worker.progress = worker.endPos

    async def __supervisor(self, context: MutiThreadContext):
        """实时统计进度并写入历史记录文件"""
        LastProgress = (
            0  # 可能会出现unbound error，所以将LastProgress提取为函数全局变量
        )

        for i in context.workers:
            self.progress += i.progress - i.startPos + 1
            LastProgress = self.progress

        if self.autoSpeedUp:
            # 初始化变量
            maxSpeedPerConnect = 1  # 防止除以 0
            additionalTaskNum = (
                context.running_task_count
            )  # 最初为计算每个线程的平均速度
            formerAvgSpeed = 0.0  # 提速之前的平均速度
            duringTime = 0  # 计算平均速度的时间间隔, 为 10 秒
            _ = 0
        ghdFile = open(f"{self.filePath}/{self.fileName}.ghd", "wb")
        try:
            while True:  # 由外层cancel退出

                info = []
                # 记录每块信息
                ghdFile.seek(0)
                self.progress = 0

                for i in context.workers:
                    info.append(
                        {"start": i.startPos, "progress": i.progress, "end": i.endPos}
                    )

                    self.progress += i.progress - i.startPos + 1

                    # 保存 workers 信息为二进制格式
                    data = struct.pack("<QQQ", i.startPos, i.progress, i.endPos)
                    ghdFile.write(data)

                ghdFile.flush()
                ghdFile.truncate()

                self.workerInfoChanged.emit(info)

                # 计算速度
                speed = self.progress - LastProgress
                # print(f"speed: {speed}, progress: {self.progress}, LastProgress: {LastProgress}")
                LastProgress = self.progress
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

                        speedPerConnect = avgSpeed / context.running_task_count
                        if speedPerConnect > maxSpeedPerConnect:
                            maxSpeedPerConnect = speedPerConnect
                            _ = (
                                0.9 * maxSpeedPerConnect * additionalTaskNum
                            ) + formerAvgSpeed
                        if avgSpeed >= _:
                            formerAvgSpeed = avgSpeed
                            additionalTaskNum = 4
                            _ = (
                                0.85 * maxSpeedPerConnect * additionalTaskNum
                            ) + formerAvgSpeed

                            if context.running_task_count < 253:
                                for i in range(4):
                                    self.__reassignWorker(context)  # 新增线程

                await asyncio.sleep(0.1) #加快刷新显示速度

        except Exception as e:
            logger.error(f"Supervisor error: {e}")
            self.gotWrong.emit(repr(e))

        finally:
            ghdFile.close()
            if context.done:
                try:
                    Path(f"{self.filePath}/{self.fileName}.ghd").unlink()
                except Exception as e:
                    logger.error(
                        f"Failed to delete the history file, please delete it manually. Err: {e}"
                    )

    async def __supervisorSingleThread(self):
        LastProgress = 0
        while True:

            self.workerInfoChanged.emit([])

            # 计算速度
            speed = self.progress - LastProgress
            LastProgress = self.progress
            self.historySpeed.pop(0)
            self.historySpeed.append(speed)
            avgSpeed = sum(self.historySpeed) / 10

            self.speedChanged.emit(avgSpeed)

            await asyncio.sleep(0.1) #加快刷新显示速度

    async def __main(self):
        try:
            # 打开下载文件
            self.file = open(f"{self.filePath}/{self.fileName}", "rb+")

            if self.ableToParallelDownload:
                # 多线程部分
                # 加载分块
                context = MutiThreadContext(self.fileSize)

                self.__loadWorkers(context)
                supervisorTask = asyncio.create_task(self.__supervisor(context))
                try:
                    async with context.taskgroup as tg:
                        for i in context.workers:  # 启动 Worker
                            tg.create_task(self.__handleWorker(i, context))
                            context.running_task_count += 1
                    context.done = True
                    logger.info(f"Task {self.fileName} finished!")
                    self.taskFinished.emit()

                finally:
                    supervisorTask.cancel()
                    await supervisorTask

            else:
                # 单线程部分
                supervisor = asyncio.create_task(self.__supervisorSingleThread())
                try:
                    await self.__handleWorkerWhenUnableToParallelDownload()
                finally:
                    self.taskFinished.emit()
                    supervisor.cancel()
                    await supervisor

        except Exception as e:
            self.gotWrong.emit(repr(e))

        finally:  # 关闭
            await self.client.close()
            self.file.close()
            # if not self.fileSize:
            #     logger.info(f"Task {self.fileName} finished!")
            #     self.taskFinished.emit()

            # if self.progress == self.fileSize:
            #     logger.info(f"Task {self.fileName} finished!")
            #     self.taskFinished.emit()

    def stop(self):
        self._mainTask.cancel()

    # @retry(3, 0.1)
    def run(self):
        self.__initThread.join()

        # 主逻辑, 使用事件循环启动异步任务
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        try:
            self._mainTask = self.loop.create_task(self.__main())
            self.loop.run_until_complete(self._mainTask)
        except asyncio.CancelledError as e:
            print(e)
        finally:
            self.loop.run_until_complete(self.loop.shutdown_asyncgens())
            self.loop.close()
