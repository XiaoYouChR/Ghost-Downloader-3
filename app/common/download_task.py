import asyncio
import struct
import sys
import time
from asyncio import Task
from pathlib import Path
from threading import Thread

import aiofiles
import httpx
from PySide6.QtCore import QThread, Signal
from loguru import logger

from app.common.config import cfg
from app.common.methods import getProxy, getReadableSize, getLinkInfo

Headers = {
    "accept-encoding": "deflate, br, gzip",
    "accept-language": "zh-CN,zh;q=0.9",
    "cookie": "down_ip=1",
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "none",
    "sec-fetch-user": "?1",
    "upgrade-insecure-requests": "1",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36 Edg/112.0.1722.64"}

class SpeedRecoder:
    def __init__(self,process = 0):
        self.process = process
        self.start_time = time.time()

    def reset(self, process):
        self.process = process
        self.start_time = time.time()

    def flash(self, process):
        
        d_time = time.time() - self.start_time
        if d_time != 0:
            speed = (process - self.process) / (time.time() - self.start_time)
        else:
            speed = 0
            d_time = 0.01#天天出花里胡哨的bug烦死我了
        return SpeedInfo(speed, d_time)


class SpeedInfo:
    def __init__(self, speed = 0, time = 1):
        if time != 0:
            self.speed = speed
            self.time = time
        else:
            raise ValueError("Time cannot be zero")

class DownloadWorker:
    """只能出卖劳动力的最底层工作者"""

    def __init__(self, start, process, end, client: httpx.AsyncClient,*, running = True):
        self.startPos = start
        self.process = process
        self.endPos = end

        self.client = client

    @property
    def task(self):
        if hasattr(self, "_task"):
            return self._task
        else:
            logger.error("Task not set yet")

    @task.setter
    def task(self, task:asyncio.Task):
        if not self.running:
            self._task = task
        else:
            self._task.cancel()
            self._task = task
            logger.warning("Task is running, cannot set task")


    @property
    def running(self):
        if hasattr(self, "_task"):
            return not self._task.done()
        else:
            return False

    def cancel(self):
        if hasattr(self, "_task"):
            self._task.cancel()



class DownloadTask(QThread):
    """TaskManager"""

    taskInited = Signal()  # 线程初始化成功
    # processChange = Signal(str)  # 目前进度 且因为C++ int最大值仅支持到2^31 PyQt又没有Qint类 故只能使用str代替
    workerInfoChanged = Signal(list)  # 目前进度 v3.2版本引进了分段式进度条
    speedChanged = Signal(int)  # 平均速度 因为 autoSpeedUp 功能需要实时计算平均速度 v3.4.4 起移入后端计算速度, 每秒速度可能超过 2^31 Bytes 吗？
    taskFinished = Signal()  # 内置信号的不好用
    gotWrong = Signal(str)  # 😭 我出问题了

    def __init__(self, url, preTaskNum: int = 8, filePath=None, fileName=None, autoSpeedUp=cfg.autoSpeedUp.value, parent=None):
        super().__init__(parent)

        self.aioLock = asyncio.Lock()
        self.process = 0
        self.url = url
        self.fileName = fileName
        self.filePath = filePath
        self.preBlockNum = preTaskNum
        self.autoSpeedUp = autoSpeedUp

        self.workers: list[DownloadWorker] = []
        self.tasks: list[Task] = []
        self._taskNum = 0

        self.client = httpx.AsyncClient(headers=Headers, verify=False,
                                        proxy=getProxy(), limits=httpx.Limits(max_connections=256))

        self.__tempThread = Thread(target=self.__getLinkInfo, daemon=True)  # TODO 获取文件名和文件大小的线程等信息, 暂时使用线程方式
        self.__tempThread.start()

    def __divitionTask(self, startPos:int):
        """根据开始位置创建新线程，并将原线程分割"""
        if len(self.workers) > 0 and startPos < self.workers[-1].endPos: #判断是否需要进行分割
            match = False
            for oldWorker in self.workers:
                if oldWorker.process < startPos < oldWorker.endPos:
                    match = True
                    newWorker = DownloadWorker(startPos, startPos, oldWorker.endPos, self.client, running = True) #分割
                    oldWorker.endPos = startPos
                    self.workers.insert(self.workers.index(oldWorker)+1, newWorker)
                    break
            if not match:
                logger.warning("无法分割任务")
        else:
            #无需分割的情况
            newWorker = DownloadWorker(startPos, startPos, self.fileSize, self.client, running = True)
            self.workers.append(newWorker)
  
        self.start_worker(newWorker)

    def __reassignWorker(self):
        """自动在合适的位置创建一个新线程"""
        maxRemain = 0
        match = False

        for work in self.workers:
            if work.running:
                if (work.endPos - work.process) // 2 > maxRemain:
                    maxRemain = (work.endPos - work.process)//2
                    maxWorker = work
                    match = True
            else:
                if work.endPos - work.process > maxRemain:
                    maxRemain = work.endPos - work.process
                    maxWorker = work
                    match = True
        if match:
            if maxWorker.running:
                if maxRemain >= cfg.maxReassignSize.value * 1048576:#1MB
                    self.__divitionTask((maxWorker.process + maxWorker.endPos)//2)
                    logger.info(
                        f'Task{self.fileName} 分配新线程成功, 剩余量：{getReadableSize(maxRemain)}')
                else:
                    logger.info(
                        f"Task{self.fileName} 欲分配新线程失败, 剩余量小于最小分块大小, 剩余量：{getReadableSize(maxRemain)}")
            else:
                if maxRemain > 0:
                    logger.info("启动已有worker")
                    self.start_worker(maxWorker)

    def start_worker(self, worker: DownloadWorker):
        """启动worker"""
        _ = asyncio.create_task(self.__handleWorker(worker))
        worker.task = _
        self.tasks.append(_)
        self._taskNum += 1

    def __clacDivisionalWorker(self):
        """预创建线程"""
        block_size = self.fileSize // self.preBlockNum
        if self.preBlockNum != 0:
            for i in range(0, self.fileSize - self.preBlockNum, block_size):
                self.__divitionTask(i)

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

        except Exception as e:  # 重试也没用
            self.gotWrong.emit(str(e))

    def __loadWorkers(self):
        """初始化并运行任务"""
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

                    logger.debug(f"pretasknum: {self.preBlockNum}")

                    for i in range(self.preBlockNum):
                        self.__reassignWorker()

            except Exception as e:
                logger.error(f"Failed to load workers: {e}")
                self.__clacDivisionalWorker()
        else:
            self.__clacDivisionalWorker()

    async def __handleWorker(self, worker: DownloadWorker):
        try:
            download_headers = Headers.copy()
            download_headers["range"] = f"bytes={worker.process}-{worker.endPos - 1}"  # 添加范围

            async with worker.client.stream(url=self.url, headers=download_headers, timeout=30,
                                            method="GET") as res:
                async for chunk in res.aiter_bytes(chunk_size=64 * 1024):
                    if worker.endPos <= worker.process:
                        break
                    if chunk:
                        self.file.seek(worker.process)
                        self.file.write(chunk)
                        worker.process += len(chunk)

            if worker.process >= worker.endPos:
                worker.process = worker.endPos


        except Exception as e:
            logger.info(
                f"Task: {self.fileName}, Thread {worker} is reconnecting to the server, Error: {repr(e)}")
            self.gotWrong.emit(repr(e))
            if not self.autoSpeedUp:
                await asyncio.sleep(5)
                self.__reassignWorker()

        except asyncio.CancelledError:
            logger.debug('task Canceled')

        else:
            #self.workers.remove(worker)
            worker.process = worker.endPos
            if not self.autoSpeedUp:
                self.__reassignWorker()

        finally:
            self._taskNum -= 1
            

    @property
    def task_num(self):#供TaskCard使用的只读属性
        return self._taskNum
    
    async def __supervisor(self):
        """实时统计进度并写入历史记录文件"""

        for i in self.workers:
            self.process += (i.process - i.startPos + 1)
            LastProcess = self.process

        if self.autoSpeedUp:
            # 初始化变量
            for i in self.workers:
                self.process += i.process - i.startPos  # 最初为计算每个线程的平均速度

            recorder = SpeedRecoder(self.process)
            threshold = 0.1 # 判断阈值
            accuracy = 1  # 判断精度

            maxSpeedPerConnect = 1  # 防止除以0

            info = SpeedInfo()
            formerInfo = SpeedInfo()
            formerTaskNum = taskNum = 0

        while not self.process == self.fileSize:

            self.ghdFile.seek(0)
            process_info = []
            self.process = 0

            for i in self.workers:
                process_info.append({"start": i.startPos, "process": i.process, "end": i.endPos})

                self.process += i.process - i.startPos

                # 保存 workers 信息为二进制格式
                data = struct.pack("<QQQ", i.startPos, i.process, i.endPos)
                await self.ghdFile.write(data)

            await self.ghdFile.flush()
            await self.ghdFile.truncate()

            self.workerInfoChange.emit(process_info)
            
            
            if self.autoSpeedUp:
                
                if self._taskNum > 0:#更新speedPerConnect，maxSpeedPerConnect
                    speedPerConnect = info.speed / self._taskNum
                    if speedPerConnect > maxSpeedPerConnect:
                        maxSpeedPerConnect = speedPerConnect
                
                if taskNum != self._taskNum:#更新taskNum， formerTaskNum，formerInfo，重置recorder
                    formerTaskNum = taskNum
                    taskNum = self._taskNum
                    formerInfo = info
                    recorder.reset(self.process)
                
                info = recorder.flash(self.process) #更新info

                #print(f'new_task_num{taskNum - formerTaskNum}   info.time{info.time}  info_cache.time{formerInfo.time}  max{maxSpeedPerConnect}')
                
                speedDeltaPerNewThread = (info.speed - formerInfo.speed) / (taskNum - formerTaskNum)# 平均速度增量
                #logger.debug(f'{getReadableSize(info.speed - formerInfo.speed)} / {taskNum - formerTaskNum} ')
                offset = (1 / info.time) * accuracy#误差补偿偏移
                efficiency = speedDeltaPerNewThread / maxSpeedPerConnect# 线程效率
                logger.debug(f'{getReadableSize(info.speed - formerInfo.speed)}/s / {taskNum - formerTaskNum} / maxSpeedPerThread {getReadableSize(maxSpeedPerConnect)}/s = efficiency {efficiency}')
                if efficiency >= threshold + offset:
                    logger.debug(f'自动提速增加新线程  {efficiency}')

                    if self._taskNum  < 256:
                        self.__reassignWorker()  # 新增线程
                
                if self._taskNum == 0 and self.process < self.fileSize:
                    logger.warning(f'线程意外消失')
                    self.__reassignWorker()  # 防止最后一个线程意外消失
                
            await asyncio.sleep(1)
                
                


            

    async def __main(self):
        try:
            # 打开下载文件
            self.file = await aiofiles.open(f"{self.filePath}/{self.fileName}", "rb+")

            self.__loadWorkers()

            self.ghdFile = await aiofiles.open(f"{self.filePath}/{self.fileName}.ghd", "wb")
            self.supervisorTask = asyncio.create_task(self.__supervisor())

            # 仅仅需要等待 supervisorTask
            try:
                await self.supervisorTask
            except asyncio.CancelledError:
                await self.client.aclose()

            # 关闭
            await self.client.aclose()

            await self.file.close()
            await self.ghdFile.close()

            if self.process == self.fileSize:
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

    # @retry(3, 0.1)
    def run(self):
        self.__tempThread.join()

        # 检验文件合法性并自动重命名
        if sys.platform == "win32":
            self.fileName = ''.join([i for i in self.fileName if i not in r'\/:*?"<>|'])  # 去除Windows系统不允许的字符
        if len(self.fileName) > 255:
            self.fileName = self.fileName[:255]

        Path(f"{self.filePath}/{self.fileName}").touch()

        # 任务初始化完成
        self.taskInited.emit()

        # TODO 发消息给主线程
        if not self.ableToParallelDownload:
            self.preBlockNum = 1

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
