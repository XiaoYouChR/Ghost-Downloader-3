import pickle
from abc import abstractmethod
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from loguru import logger

from app.common.config import cfg


class TaskManagerBase(QObject):
    """
    用于存放基本任务数据和管理任务, 用于跟 TaskCard 通信
    :param: fileSize == -1 表示自动获取; == 0 表示不能并行下载; else 表示正常分段下载
    """
    taskInited = Signal(bool)  # 线程初始化成功, 并传递是否支持并行下载的信息 (是否支持并行下载即任务进度条是否不确定)
    taskFinished = Signal()  # 内置的完成信号不好用
    taskGotWrong = Signal(str)  # 任务报错 😭
    progressInfoChanged = Signal(list)  # 目前进度 用于显示 v3.2 引进的分段式进度条
    speedChanged = Signal(int)  # 平均速度 因为 autoSpeedUp 功能需要实时计算平均速度 v3.4.4 起移入后端计算速度, 每秒速度可能超过 2^31 Bytes 吗？

    def __init__(self, url, headers, preBlockNum: int, filePath: str, fileName: str = None,
                 fileSize: int = -1, parent=None):
        super().__init__(parent)
        self.url = url
        self.headers = headers
        self.fileName = fileName
        self.filePath = filePath
        self.preBlockNum = preBlockNum
        self.fileSize = fileSize

        self.task = None
        self.progress = 0

    @classmethod
    def getClsAttr(cls):
        return "plugins.{}".format(cls.__module__), cls.__name__

    @abstractmethod
    def start(self):
        pass

    @abstractmethod
    def stop(self):
        pass

    @abstractmethod
    def updateTaskRecord(self, newStatus: str):
        recordPath = "{}/Ghost Downloader 记录文件".format(cfg.appPath)

        clsModule, clsName = self.getClsAttr()

        # 读取所有记录
        records = []
        try:
            with open(recordPath, "rb") as f:
                while True:
                    try:
                        record = pickle.load(f)
                        records.append(record)
                    except EOFError:
                        break
        except FileNotFoundError:
            pass

        # 检查是否已有匹配的记录
        found = False
        updatedRecords = []

        for record in records:  # 遍历所有记录, 替换 newStatus
            if (record["url"] == self.url and
                    record["fileName"] == self.fileName and
                    record["filePath"] == str(self.filePath) and
                    record["blockNum"] == self.preBlockNum and
                    record["headers"] == self.headers and
                    record["clsModule"] == clsModule and
                    record["clsName"] == clsName):

                found = True
                if newStatus != "deleted":
                    record["status"] = newStatus
                    updatedRecords.append(record)
            else:
                updatedRecords.append(record)

        # 如果没有找到匹配的记录且 newStatus 不是 "deleted"，则添加新记录
        if not found and newStatus != "deleted":
            updatedRecords.append({
                "url": self.url,
                "fileName": self.fileName,
                "filePath": str(self.filePath),
                "blockNum": self.preBlockNum,
                "status": newStatus,
                "headers": self.headers,
                "fileSize": self.fileSize,
                "clsModule": clsModule,
                "clsName": clsName
            })

        # 写回记录文件
        with open(recordPath, "wb") as f:
            for record in updatedRecords:
                pickle.dump(record, f)

    @abstractmethod
    def cancel(self, completely: bool=False):
        self.stop()
        if completely:  # 删除文件
            try:
                Path(f"{self.filePath}/{self.fileName}").unlink()
                Path(f"{self.filePath}/{self.fileName}.ghd").unlink()
                logger.info(f"self:{self.fileName}, delete file successfully!")

            except FileNotFoundError:
                pass

            except Exception as e:
                raise e
    @abstractmethod
    def _onTaskInited(self, ableToParallelDownload: bool):
        self.fileName = self.task.fileName
        self.fileSize = self.task.fileSize
        self.taskInited.emit(ableToParallelDownload)