from abc import abstractmethod

from PySide6.QtCore import QObject, Signal


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

    def __init__(self, url, headers, preTaskNum: int, filePath: str, fileName: str = None,
                 fileSize: int = -1, parent=None):
        super().__init__(parent)
        self.url = url
        self.headers = headers
        self.fileName = fileName
        self.filePath = filePath
        self.preBlockNum = preTaskNum
        self.fileSize = fileSize

        self.task = None

    @abstractmethod
    def start(self):
        pass

    @abstractmethod
    def stop(self):
        pass

    @abstractmethod
    def updateTaskRecord(self, newStatus: str):
        pass

    @abstractmethod
    def cancel(self, completely: bool=False):
        pass

    @abstractmethod
    def __onTaskInited(self, ableToParallelDownload: bool):
        pass
