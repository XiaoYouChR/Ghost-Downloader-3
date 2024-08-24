import asyncio
import hashlib
import os
import re
import sys
from pathlib import Path
from time import sleep

from PySide6.QtCore import QThread, Signal, QFileInfo
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFileIconProvider, QApplication
from loguru import logger
from qfluentwidgets import CardWidget
from qfluentwidgets import FluentIcon as FIF

from .Ui_TaskCard import Ui_TaskCard
from .task_progress_bar import TaskProgressBar
from ..common.config import cfg
from ..common.download_task import DownloadTask
from ..common.methods import getProxy, getReadableSize, retry

Headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36 Edg/112.0.1722.64"}

urlRe = re.compile(r"^" +
                   "((?:https?|ftp)://)" +
                   "(?:\\S+(?::\\S*)?@)?" +
                   "(?:" +
                   "(?:[1-9]\\d?|1\\d\\d|2[01]\\d|22[0-3])" +
                   "(?:\\.(?:1?\\d{1,2}|2[0-4]\\d|25[0-5])){2}" +
                   "(\\.(?:[1-9]\\d?|1\\d\\d|2[0-4]\\d|25[0-4]))" +
                   "|" +
                   "((?:[a-z\\u00a1-\\uffff0-9]-*)*[a-z\\u00a1-\\uffff0-9]+)" +
                   '(?:\\.(?:[a-z\\u00a1-\\uffff0-9]-*)*[a-z\\u00a1-\\uffff0-9]+)*' +
                   "(\\.([a-z\\u00a1-\\uffff]{2,}))" +
                   ")" +
                   "(?::\\d{2,5})?" +
                   "(?:/\\S*)?" +
                   "$", re.IGNORECASE)

# 获取系统代理
proxy = getProxy()


class TaskCard(CardWidget, Ui_TaskCard):
    # removeTaskSignal = Signal(int, bool)
    def __init__(self, url, path, maxBlockNum: int, name: str = None, status: str = "working",
                 parent=None, autoCreated=False):
        super().__init__(parent=parent)

        self.setupUi(self)

        # 初始化参数

        self.url = url
        self.filePath = path
        self.maxBlockNum = maxBlockNum
        self.status = status  # working paused finished canceled
        self.lastProcess = 0
        self.autoCreated = autoCreated

        # Show Information
        self.speedLable.setText("若任务初始化过久，请检查网络连接后重试.")
        self.TitleLabel.setText("正在初始化任务...")

        self.LogoPixmapLabel.setPixmap(QPixmap(":/image/logo.png"))
        self.LogoPixmapLabel.setFixedSize(91, 91)

        self.progressBar = TaskProgressBar(maxBlockNum, self)
        self.progressBar.setObjectName(u"progressBar")

        self.verticalLayout.addWidget(self.progressBar)

        if name:
            self.fileName = name

        if not self.status == "finished":  # 不是已完成的任务才要进行的操作
            if name:
                self.task = DownloadTask(url, maxBlockNum, path, name)
            else:
                self.task = DownloadTask(url, maxBlockNum, path)

            self.task.taskInited.connect(self.__onTaskInited)
            self.task.workerInfoChange.connect(self.__changeInfo)
            self.task.taskFinished.connect(self.taskFinished)
            self.task.gotWrong.connect(self.__onTaskError)

        elif self.status == "finished":
            # TODO 超分辨率触发条件
            _ = QFileIconProvider().icon(QFileInfo(f"{self.filePath}/{self.fileName}")).pixmap(128, 128)  # 自动获取图标

            if _:
                pixmap = _
            else:
                pixmap = QPixmap(":/image/logo.png")

            self.TitleLabel.setText(self.fileName)
            self.LogoPixmapLabel.setPixmap(pixmap)
            self.LogoPixmapLabel.setFixedSize(91, 91)

            self.taskFinished()

        # 连接信号到槽
        self.pauseButton.clicked.connect(self.pauseTask)
        self.delAction.triggered.connect(lambda: self.cancelTask(False))
        self.completelyDelAction.triggered.connect(lambda: self.cancelTask(True))
        if sys.platform == "win32":
            self.folderButton.clicked.connect(lambda: os.startfile(path))
        else:  # Linux 下打开文件夹
            self.folderButton.clicked.connect(lambda: os.system(f"xdg-open {path}"))

        if self.status == "working":
            # 开始下载
            self.task.start()
        elif self.status == "paused":
            self.pauseButton.setIcon(FIF.PLAY)

    def __onTaskError(self, exception: str):
        self.TitleLabel.setText(f"请重新启动任务!")
        self.speedLable.setText(f"Error: {exception}")

    def __onTaskInited(self):
        self.fileName = self.task.fileName

        # TODO 因为Windows会返回已经处理过的只有左上角一点点的图像，所以需要超分辨率触发条件
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

        # 写入未完成任务记录文件，以供下次打开时继续下载
        if not self.autoCreated:
            with open("{}/Ghost Downloader 记录文件".format(cfg.appPath), "a", encoding="utf-8") as f:
                _ = {"url": self.url, "fileName": self.fileName, "filePath": str(self.filePath),
                     "blockNum": self.maxBlockNum, "status": self.status}
                f.write(str(_) + "\n")

    def pauseTask(self):
        if self.status == "working":  # 暂停
            self.pauseButton.setDisabled(True)
            self.pauseButton.setIcon(FIF.PLAY)
            try:
                for i in self.task.workers:
                    i.task.cancel()
                self.task.task.cancel()

                # 改变记录状态
                with open("{}/Ghost Downloader 记录文件".format(cfg.appPath), "r", encoding="utf-8") as f:
                    _ = f.read()

                _ = _.replace(str({"url": self.url, "fileName": self.fileName, "filePath": str(self.filePath),
                                   "blockNum": self.maxBlockNum, "status": self.status}) + "\n",
                              str({"url": self.url, "fileName": self.fileName, "filePath": str(self.filePath),
                                   "blockNum": self.maxBlockNum, "status": "paused"}) + "\n")

                with open("{}/Ghost Downloader 记录文件".format(cfg.appPath), "w", encoding="utf-8") as f:
                    f.write(_)

            finally:
                self.speedLable.setText("任务已经暂停")
                self.status = "paused"
                self.pauseButton.setEnabled(True)

        elif self.status == "paused":  # 继续
            self.pauseButton.setDisabled(True)
            self.pauseButton.setIcon(FIF.PAUSE)

            try:
                self.task = DownloadTask(self.url, self.maxBlockNum, self.filePath, self.fileName)
            except: # TODO 没有 fileName 的情况
                self.task = DownloadTask(self.url, self.maxBlockNum, self.filePath)

            self.task.taskInited.connect(self.__onTaskInited)
            self.task.workerInfoChange.connect(self.__changeInfo)
            self.task.taskFinished.connect(self.taskFinished)
            self.task.gotWrong.connect(self.__onTaskError)

            self.task.start()


            try:
                # 改变记录状态
                with open("{}/Ghost Downloader 记录文件".format(cfg.appPath), "r", encoding="utf-8") as f:
                    _ = f.read()

                _ = _.replace(str({"url": self.url, "fileName": self.fileName, "filePath": str(self.filePath),
                                   "blockNum": self.maxBlockNum, "status": self.status}) + "\n",
                              str({"url": self.url, "fileName": self.fileName, "filePath": str(self.filePath),
                                   "blockNum": self.maxBlockNum, "status": "working"}) + "\n")

                with open("{}/Ghost Downloader 记录文件".format(cfg.appPath), "w", encoding="utf-8") as f:
                    f.write(_)

            finally:
                self.speedLable.setText("任务正在开始")
                self.status = "working"
                self.pauseButton.setEnabled(True)


    @retry(3, 0.1)
    def cancelTask(self, completely: bool = False):
        self.pauseButton.setDisabled(True)
        self.cancelButton.setDisabled(True)

        try:
            if self.status == "working":
                self.pauseTask()

            if completely:
                # 删除文件
                try:
                    Path(f"{self.filePath}/{self.fileName}").unlink()
                    Path(f"{self.filePath}/{self.fileName}.ghd").unlink()
                    logger.info(f"self:{self.fileName}, delete file successfully!")

                except FileNotFoundError:
                    pass

                except Exception as e:
                    raise e

            # 删除记录文件
            with open("{}/Ghost Downloader 记录文件".format(cfg.appPath), "r", encoding="utf-8") as f:
                _ = f.read()

            _ = _.replace(str({"url": self.url, "fileName": self.fileName, "filePath": str(self.filePath),
                               "blockNum": self.maxBlockNum, "status": self.status}) + "\n", "")

            with open("{}/Ghost Downloader 记录文件".format(cfg.appPath), "w", encoding="utf-8") as f:
                f.write(_)

        except Exception as e:
            logger.warning(f"Task:{self.fileName}, 删除时遇到错误: {e}")

        finally:
            self.status = "canceled"
            # Remove Widget
            self.parent().parent().parent().expandLayout.removeWidget(self)
            self.hide()

    def __changeInfo(self, content: list):
        # 理论来说 worker 直增不减 所以ProgressBar不用考虑线程减少的问题
        # process = int(content)
        _ = len(content) - self.progressBar.blockNum
        if _:
            self.progressBar.addProgressBar(content, _)

        process = 0


        for e, i in enumerate(content):
            #process += i["process"] - i["start"]
            self.progressBar.HBoxLayout.setStretch(e, int((i["end"] - i["start"]) / 1048576))  # 除以1MB
            self.progressBar.progressBarList[e].setValue( ( (i["process"] - i["start"]) / (i["end"] - i["start"]) ) * 100)
        
        process = self.task.process
        duringLastSecondProcess = process - self.lastProcess

        self.speedLable.setText(f"{getReadableSize(duringLastSecondProcess)}/s")
        self.processLabel.setText(f"{getReadableSize(process)}/{getReadableSize(self.task.fileSize)}")
        # self.ProgressBar.setValue((process / self.task.fileSize) * 100)

        self.lastProcess = process

    def taskFinished(self):
        self.pauseButton.setDisabled(True)
        self.cancelButton.setDisabled(True)
        self.clicked.connect(lambda: os.system(f"{self.filePath}/{self.fileName}"))
        self.speedLable.setText("任务已经完成")

        try:    # 程序启动时不要发
            self.window().tray.showMessage(self.window().windowTitle(), f"任务 {self.fileName} 已完成！", self.window().windowIcon())
        except:
            pass

        if not self.status == "finished":  # 不是自动创建的已完成任务
            # 改变记录状态
            with open("{}/Ghost Downloader 记录文件".format(cfg.appPath), "r", encoding="utf-8") as f:
                _ = f.read()

            _ = _.replace(str({"url": self.url, "fileName": self.fileName, "filePath": str(self.filePath),
                               "blockNum": self.maxBlockNum, "status": self.status}) + "\n",
                          str({"url": self.url, "fileName": self.fileName, "filePath": str(self.filePath),
                               "blockNum": self.maxBlockNum, "status": "finished"}) + "\n")

            with open("{}/Ghost Downloader 记录文件".format(cfg.appPath), "w", encoding="utf-8") as f:
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
