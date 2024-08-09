import re
from pathlib import Path
from time import sleep

import requests
from PySide6.QtCore import QThread, Signal

from loguru import logger

from app.common.methods import getWindowsProxy, getReadableSize
from app.common.utils import UrlUtils

Headers = UrlUtils.headers
urlRe = UrlUtils.urlRe

MAX_REASSIGN_SIZE = 15*1024*1024  # 15M


class DownloadTask(QThread):
    """作用相当于包工头"""

    refreshLastProgress = Signal(str)  # 用于读取历史记录后刷新进度
    # processChange = Signal(str)  # 目前进度 且因为C++ int最大值仅支持到2^31 PyQt又没有Qint类 故只能使用str代替
    workerInfoChange = Signal(list)  # 目前进度 3.2版本引进了分段式进度条
    taskFinished = Signal()  # 内置信号的不好用

    def __init__(self, url, maxBlockNum: int = 8, filePath=None, fileName=None, parent=None):
        super().__init__(parent)

        # 获取真实URL
        url = UrlUtils.getRealUrl(url, getWindowsProxy())

        head = requests.head(url, headers=Headers, proxies=getWindowsProxy()).headers

        # 获取文件大小, 判断是否可以分块下载
        if "content-length" not in head:
            # 如果 文件大小无法获取 则默认1，否则会导致clacDivisionalRange，创建step错误
            self.fileSize = 1
            self.ableToParallelDownload = False
        else:
            self.fileSize = int(head["content-length"])
            self.ableToParallelDownload = True

        # 获取文件名
        if not fileName:
            fileName = UrlUtils.byUrlGetFileName(url, getWindowsProxy())

        # 获取文件路径
        if not filePath and Path(filePath).is_dir() == False:
            filePath = Path.cwd()
        else:
            filePath = Path(filePath)
            if not filePath.exists():
                filePath.mkdir()

        # 创建空文件
        Path(f"{filePath}/{fileName}").touch()

        self.process = []
        self.url = url
        self.fileName = fileName
        self.filePath = filePath
        self.maxBlockNum = maxBlockNum
        self.workers: list[DownloadWorker] = []

    def __reassignWorker(self):

        # 找到剩余进度最多的线程
        maxRemainder = 0
        maxRemainderWorker: DownloadWorker = None

        for i in self.workers:
            if (i.endPos - i.process) > maxRemainder:  # TODO 其实逻辑有一点问题, 但是影响不大
                maxRemainderWorkerProcess = i.process
                maxRemainderWorkerEnd = i.endPos
                maxRemainder = (maxRemainderWorkerEnd - maxRemainderWorkerProcess)
                maxRemainderWorker = i

        if maxRemainderWorker and maxRemainder > MAX_REASSIGN_SIZE:
            # 平均分配工作量
            baseShare = maxRemainder // 2
            remainder = maxRemainder % 2


            maxRemainderWorker.endPos = maxRemainderWorkerProcess + baseShare + remainder  # 直接修改好像也不会怎么样

            # 安配新的工人
            s_pos = maxRemainderWorkerProcess + baseShare + remainder + 1

            _ = DownloadWorker(s_pos, s_pos, maxRemainderWorkerEnd, self.url, self.filePath,
                               self.fileName)
            _.workerFinished.connect(self.__reassignWorker)
            _.start()
            self.workers.insert(self.workers.index(maxRemainderWorker) + 1, _)

            logger.info(f"Task{self.fileName} 分配新线程成功, 剩余量：{getReadableSize(maxRemainder)}，修改后的EndPos：{maxRemainderWorker.endPos}，新线程：{_}，新线程的StartPos：{s_pos}")

        else:
            logger.info(f"Task{self.fileName} 欲分配新线程失败, 剩余量小于最小分块大小, 剩余量：{getReadableSize(maxRemainder)}")

    def clacDivisionalRange(self):
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

    def run(self):
        # TODO 发消息给主线程
        if not self.ableToParallelDownload:
            self.maxBlockNum = 1
        # 读取历史记录
        # 历史记录.ghd文件采用格式示例: ["start": 0, "process": 0, "end": 100, }, {"start": 101, "process": 111, "end": 200}]
        if Path(f"{self.filePath}/{self.fileName}.ghd").exists():
            try:
                with open(f"{self.filePath}/{self.fileName}.ghd", "r", encoding="utf-8") as f:
                    workersInfo = eval(f.read())
                    logger.debug(f"Task:{self.fileName}, history info is: {workersInfo}")
                    for i in workersInfo:
                        self.workers.append(
                            DownloadWorker(i["start"], i["process"], i["end"], self.url, self.filePath,
                                           self.fileName))

                self.refreshLastProgress.emit(str(sum([i.process for i in self.workers])))  # 要不然速度会错
            # TODO 错误处理
            except:
                for i in range(self.maxBlockNum):
                    stepList = self.clacDivisionalRange()
                    self.workers.append(
                        DownloadWorker(stepList[i][0], stepList[i][0], stepList[i][1], self.url, self.filePath,
                                       self.fileName))
        else:
            for i in range(self.maxBlockNum):
                stepList = self.clacDivisionalRange()
                self.workers.append(
                    DownloadWorker(stepList[i][0], stepList[i][0], stepList[i][1], self.url, self.filePath,
                                   self.fileName))

        for i in self.workers:
            logger.debug(f"Task {self.fileName}, starting the thread {i}...")
            i.workerFinished.connect(self.__reassignWorker)
            i.start()

        # fileResolve = Path(f"{self.filePath}/{self.fileName}")
        # 实时统计进度并写入历史记录文件
        while not self.process == self.fileSize:
            with open(f"{self.filePath}/{self.fileName}.ghd", "w", encoding="utf-8") as f:
                info = [{"start": i.startPos, "process": i.process, "end": i.endPos} for i in self.workers]
                f.write(str(info))
                f.flush()

            # self.process = os.path.getsize(fileResolve)
            # self.process = sum([i.process - i.startProcess + 1 for i in self.workers])
            # self.processChange.emit(str(self.process))

            self.process = sum([i.process - i.startPos + 1 for i in self.workers])

            self.workerInfoChange.emit(info)

            # print(self.process, self.fileSize)

            sleep(1)

        # 删除历史记录文件
        try:
            Path(f"{self.filePath}/{self.fileName}.ghd").unlink()

        except Exception as e:
            logger.error(f"Failed to delete the history file, please delete it manually. Err: {e}")

        logger.info(f"Task {self.fileName} finished!")

        self.taskFinished.emit()


class DownloadWorker(QThread):
    """只能出卖劳动力的最底层工作者"""

    workerFinished = Signal()  # 内置的信号不好用

    def __init__(self, start, process, end, url, filePath, fileName, parent=None):
        super().__init__(parent)
        self.startPos = start
        self.process = process
        self.endPos = end
        self.url = url
        self.filePath = filePath
        self.fileName = fileName

    def run(self):
        if self.process < self.endPos:  # 因为可能会创建空线程
            finished = False
            while not finished:
                try:
                    download_headers = {"Range": f"bytes={self.process}-{self.endPos}",
                                        "User-Agent": Headers["User-Agent"]}

                    res = requests.get(self.url, headers=download_headers, proxies=getWindowsProxy(), stream=True,
                                       timeout=60)

                    self.file = open(f"{self.filePath}/{self.fileName}", "rb+")
                    self.file.seek(self.process)
                    for chunk in res.iter_content(chunk_size=65536):  # iter_content 的单位是字节, 即每64K写一次文件
                        if self.endPos <= self.process:
                            break
                        if chunk:
                            self.file.write(chunk)
                            self.process += 65536

                    if self.process >= self.endPos:
                        self.process = self.endPos

                    try:
                        self.file.close()
                    except:
                        pass

                    finished = True

                except Exception as e:
                    logger.info(f"Task: {self.fileName}, Thread {self} is reconnecting to the server, Error: {e}")

                    try:
                        self.file.close()
                    except:
                        pass

                    sleep(5)

            self.process = self.endPos
            self.workerFinished.emit()
