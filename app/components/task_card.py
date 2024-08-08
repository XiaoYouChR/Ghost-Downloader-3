import hashlib
import os
from pathlib import Path
from time import sleep

from PySide6.QtCore import QThread, Signal, QFileInfo
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFileIconProvider
from loguru import logger
from qfluentwidgets import CardWidget
from qfluentwidgets import FluentIcon as FIF

from .Ui_TaskCard import Ui_TaskCard
from .task_progress_bar import TaskProgressBar
from ..common.download_task import DownloadTask
from ..common.methods import getWindowsProxy, getReadableSize

Headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36 Edg/112.0.1722.64"}


# 获取系统代理
proxy = getWindowsProxy()


class TaskCard(CardWidget, Ui_TaskCard):
    # removeTaskSignal = Signal(int, bool)
    def __init__(self, url, path, maxBlockNum: int, pixmap: QPixmap = None, name: str = None, status: str = "working",
                 parent=None,
                 autoCreated=False):
        super().__init__(parent=parent)

        self.setupUi(self)

        # 初始化参数

        self.url = url
        self.filePath = path
        self.maxBlockNum = maxBlockNum
        self.status = status  # working paused finished canceled
        self.lastProcess = 0

        # self.number = number
        self.progressBar = TaskProgressBar(maxBlockNum, self)
        self.progressBar.setObjectName(u"progressBar")

        self.verticalLayout.addWidget(self.progressBar)

        def _(progress: str):  # 用于赋值
            self.lastProcess = int(progress)

        if name:
            self.fileName = name

        if not self.status == "finished":  # 不是已完成的任务才要进行的操作
            if name:
                self.task = DownloadTask(url, maxBlockNum, path, name)
            else:
                self.task = DownloadTask(url, maxBlockNum, path)
                self.fileName = self.task.fileName

            self.task.refreshLastProgress.connect(_)
            self.task.workerInfoChange.connect(self.__changeInfo)
            self.task.taskFinished.connect(self.taskFinished)

        elif self.status == "finished":
            self.taskFinished()

        if not pixmap:
            # TODO 超分辨率触发条件
            # _ = QFileIconProvider().icon(QFileInfo(f"{self.filePath}/{self.fileName}")).pixmap(48, 48).scaled(91, 91, aspectMode=Qt.AspectRatioMode.KeepAspectRatio,
            #                            mode=Qt.TransformationMode.SmoothTransformation)  # 自动获取图标
            _ = QFileIconProvider().icon(QFileInfo(f"{self.filePath}/{self.fileName}")).pixmap(128, 128)  # 自动获取图标


            if _:
                pixmap = _
            else:
                pixmap = QPixmap(":/image/logo.png")

        # 显示信息
        self.TitleLabel.setText(self.fileName)
        self.LogoPixmapLabel.setPixmap(pixmap)
        self.LogoPixmapLabel.setFixedSize(91, 91)
        # self.processLabel.setText(f"0B/{getReadableSize(self.task.fileSize)}")

        # 连接信号到槽
        self.pauseButton.clicked.connect(self.pauseTask)
        self.delAction.triggered.connect(lambda: self.cancelTask(False))
        self.completelyDelAction.triggered.connect(lambda: self.cancelTask(True))
        self.folderButton.clicked.connect(lambda: os.startfile(path))

        # 写入未完成任务记录文件，以供下次打开时继续下载
        if not autoCreated:
            with open("./Ghost Downloader 记录文件", "a", encoding="utf-8") as f:
                _ = {"url": self.url, "fileName": self.fileName, "filePath": str(self.filePath),
                     "blockNum": self.maxBlockNum, "status": self.status}
                f.write(str(_) + "\n")

        if self.status == "working":
            # 开始下载
            self.task.start()
        elif self.status == "paused":
            self.pauseButton.setIcon(FIF.PLAY)

    def pauseTask(self):
        if self.status == "working":  # 暂停
            self.pauseButton.setDisabled(True)
            self.pauseButton.setIcon(FIF.PLAY)
            for i in self.task.workers:
                try:
                    i.file.close()
                except Exception as e:
                    logger.warning(
                        f"Task:{self.fileName}, it seems that cannot cancel thread {i} occupancy of the file, error: {e}")
                i.terminate()
            self.task.terminate()

            # 改变记录状态
            with open("./Ghost Downloader 记录文件", "r", encoding="utf-8") as f:
                _ = f.read()

            _ = _.replace(str({"url": self.url, "fileName": self.fileName, "filePath": str(self.filePath),
                               "blockNum": self.maxBlockNum, "status": self.status}) + "\n",
                          str({"url": self.url, "fileName": self.fileName, "filePath": str(self.filePath),
                               "blockNum": self.maxBlockNum, "status": "paused"}) + "\n")

            with open("./Ghost Downloader 记录文件", "w", encoding="utf-8") as f:
                f.write(_)

            self.speedLable.setText("任务已经暂停")
            self.status = "paused"
            self.pauseButton.setEnabled(True)

        elif self.status == "paused":  # 继续
            self.pauseButton.setDisabled(True)
            self.pauseButton.setIcon(FIF.PAUSE)
            self.task = DownloadTask(self.url, self.maxBlockNum, self.filePath, self.fileName)
            self.task.start()
            self.task.workerInfoChange.connect(self.__changeInfo)
            self.task.taskFinished.connect(self.taskFinished)

            # 改变记录状态
            with open("./Ghost Downloader 记录文件", "r", encoding="utf-8") as f:
                _ = f.read()

            _ = _.replace(str({"url": self.url, "fileName": self.fileName, "filePath": str(self.filePath),
                               "blockNum": self.maxBlockNum, "status": self.status}) + "\n",
                          str({"url": self.url, "fileName": self.fileName, "filePath": str(self.filePath),
                               "blockNum": self.maxBlockNum, "status": "working"}) + "\n")

            with open("./Ghost Downloader 记录文件", "w", encoding="utf-8") as f:
                f.write(_)

            self.speedLable.setText("任务正在开始")
            self.status = "working"
            self.pauseButton.setEnabled(True)

    def cancelTask(self, completely: bool = False):
        self.pauseButton.setDisabled(True)
        self.cancelButton.setDisabled(True)

        if self.status == "working":
            self.pauseTask()

        if completely:
            # 删除文件
            tryCount = 0
            isDeleted = False
            while not isDeleted and tryCount < 3:
                try:
                    Path(f"{self.filePath}/{self.fileName}").unlink()
                    Path(f"{self.filePath}/{self.fileName}.ghd").unlink()
                    logger.info(f"self:{self.fileName}, delete file successfully!")

                    isDeleted = True
                    tryCount = 5

                except FileNotFoundError:
                    isDeleted = True
                    tryCount = 5
                except Exception as e:
                    logger.error(f"Task:{self.fileName}, it seems that cannot delete file, error: {e}")
                    tryCount += 1

                sleep(0.1)

        # 删除记录文件
        with open("./Ghost Downloader 记录文件", "r", encoding="utf-8") as f:
            _ = f.read()

        _ = _.replace(str({"url": self.url, "fileName": self.fileName, "filePath": str(self.filePath),
                           "blockNum": self.maxBlockNum, "status": self.status}) + "\n", "")

        with open("./Ghost Downloader 记录文件", "w", encoding="utf-8") as f:
            f.write(_)

        self.status = "canceled"

        self.parent().parent().parent().expandLayout.removeWidget(self)

        self.hide()

    def __changeInfo(self, content: list):
        # 理论来说 worker 直增不减 所以ProgressBar不用考虑线程减少的问题
        # process = int(content)
        _ = len(content) - self.progressBar.blockNum
        if _:
            for i in range(_):
                self.progressBar.addProgressBar()

        process = 0


        for e, i in enumerate(content):
            process += i["process"] - i["start"]
            self.progressBar.HBoxLayout.setStretch(e, int((i["end"] - i["start"]) / 1048576))  # 除以1MB
            try:
                self.progressBar.progressBarList[e].setValue( ( (i["process"] - i["start"]) / (i["end"] - i["start"]) ) * 100)
            except ZeroDivisionError as ZDE:
                # 因为 下载速度为0 导致进度条无法显示，也有可能是文件的内容为空 所以直接跳过
                logger.error(f"Task:{self.fileName}, it seems that cannot change progress bar, error: {ZDE}")
                continue

        duringLastSecondProcess = process - self.lastProcess

        self.speedLable.setText(f"{getReadableSize(duringLastSecondProcess)}/s")
        self.processLabel.setText(f"{getReadableSize(process)}/{getReadableSize(self.task.fileSize)}")
        # self.ProgressBar.setValue((process / self.task.fileSize) * 100)

        self.lastProcess = process

    def taskFinished(self):
        self.pauseButton.setDisabled(True)
        self.cancelButton.setDisabled(True)
        self.speedLable.setText("任务已经完成")

        if not self.status == "finished":  # 不是自动创建的已完成任务
            # 改变记录状态
            with open("./Ghost Downloader 记录文件", "r", encoding="utf-8") as f:
                _ = f.read()

            _ = _.replace(str({"url": self.url, "fileName": self.fileName, "filePath": str(self.filePath),
                               "blockNum": self.maxBlockNum, "status": self.status}) + "\n",
                          str({"url": self.url, "fileName": self.fileName, "filePath": str(self.filePath),
                               "blockNum": self.maxBlockNum, "status": "finished"}) + "\n")

            with open("./Ghost Downloader 记录文件", "w", encoding="utf-8") as f:
                f.write(_)

            # 再获取一次图标
            _ = QFileIconProvider().icon(QFileInfo(f"{self.filePath}/{self.fileName}")).pixmap(128, 128)  # 自动获取图标
            if _:
                pass
            else:
                _ = QPixmap(":/image/logo.png")
            self.LogoPixmapLabel.setPixmap(_)
            self.LogoPixmapLabel.setFixedSize(91, 91)

        self.status = "finished"

        # 将暂停按钮改成校验按钮
        self.pauseButton.setIcon(FIF.UPDATE)
        self.pauseButton.clicked.connect(self.runClacTask)
        self.pauseButton.setDisabled(False)
        self.cancelButton.setDisabled(False)


    def runClacTask(self):
        self.speedLable.setText("正在校验MD5...")
        self.clacTask = ClacMD5Thread(f"{self.filePath}/{self.fileName}")
        self.clacTask.returnMD5.connect(lambda x: self.speedLable.setText(f"校验完成！文件的MD5值是：{x}"))
        self.clacTask.start()


class ClacMD5Thread(QThread):
    returnMD5 = Signal(str)

    def __init__(self, fileResolvedPath: str, parent=None):
        super().__init__(parent=parent)
        self.fileResolvedPath = fileResolvedPath

    def run(self):
        hash_algorithm = getattr(hashlib, "md5")()

        with open(self.fileResolvedPath, "rb") as file:
            chunk_size = 65536  # 64 KiB chunks
            while True:
                chunk = file.read(chunk_size)
                if not chunk:
                    break
                hash_algorithm.update(chunk)

        result = hash_algorithm.hexdigest()

        self.returnMD5.emit(result)
