import hashlib
import os
import re
from pathlib import Path
from time import sleep

from PySide6.QtCore import QThread, Signal, QFileInfo
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFileIconProvider
from qfluentwidgets import CardWidget

from .Ui_TaskCard import Ui_TaskCard
from ..common.download_task import DownloadTask
from ..common.tool_hub import getWindowsProxy, getReadableSize

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
proxy = getWindowsProxy()


class TaskCard(CardWidget, Ui_TaskCard):

    def __init__(self, url, path, maxBlockNum: int, pixmap: QPixmap = None, name: str = None, parent=None,
                 autoCreated=False):
        super().__init__(parent=parent)

        self.setupUi(self)

        # 初始化参数

        self.url = url
        self.filePath = path
        self.maxBlockNum = maxBlockNum

        if name:
            self.task = DownloadTask(url, maxBlockNum, path, name)
            self.fileName = name
        else:
            self.task = DownloadTask(url, maxBlockNum, path)
            self.fileName = self.task.fileName

        if not pixmap:
            pixmap = QFileIconProvider().icon(QFileInfo(f"{self.filePath}/{self.fileName}")).pixmap(128, 128)  # 自动获取图标

        self.paused = False

        self.lastProcess = 0

        # 显示信息
        self.TitleLabel.setText(self.fileName)
        self.LogoPixmapLabel.setPixmap(pixmap)
        self.LogoPixmapLabel.setFixedSize(91, 91)
        self.processLabel.setText(f"0B/{getReadableSize(self.task.fileSize)}")

        # 连接信号到槽
        self.pauseButton.clicked.connect(self.pauseTask)
        self.cancelButton.clicked.connect(self.cancelTask)
        self.folderButton.clicked.connect(lambda: os.startfile(self.task.filePath))
        self.task.processChange.connect(self.__changeInfo)
        self.task.taskFinished.connect(self.taskFinished)

        # 写入未完成任务记录文件，以供下次打开时继续下载
        if not autoCreated:
            with open("./history", "a", encoding="utf-8") as f:
                _ = {"url": self.url, "fileName": self.fileName, "filePath": str(self.filePath),
                     "blockNum": self.maxBlockNum}
                f.write(str(_) + "\n")

        # 开始下载
        self.task.start()

    def pauseTask(self):
        if not self.paused:  # 暂停
            self.pauseButton.setDisabled(True)
            self.pauseButton.setIcon(self.playIcon)
            for i in self.task.workers:
                try:
                    i.file.close()
                except Exception as e:
                    print(f"似乎无法关闭线程{i.id}对文件的占用, 错误信息: {e}")
                i.terminate()
            self.task.terminate()
            self.speedLable.setText("任务已经暂停")
            self.paused = True
            self.pauseButton.setEnabled(True)

        else:  # 继续
            self.pauseButton.setDisabled(True)
            self.pauseButton.setIcon(self.pauseIcon)
            self.task = DownloadTask(self.url, self.maxBlockNum, self.filePath, self.fileName)
            self.task.start()
            self.task.processChange.connect(self.__changeInfo)
            self.speedLable.setText("任务正在开始")
            self.paused = False
            self.pauseButton.setEnabled(True)

    def cancelTask(self):
        self.pauseButton.setDisabled(True)
        self.cancelButton.setDisabled(True)

        for i in self.task.workers:
            try:
                i.file.close()
            except Exception as e:
                print(f"似乎无法关闭线程{i.id}对文件的占用, 错误信息: {e}")
            i.terminate()
        self.task.terminate()

        # 删除文件
        tryCount = 0
        isDeleted = False
        while not isDeleted and tryCount < 3:
            try:
                Path(f"{self.filePath}/{self.fileName}").unlink()
                Path(f"{self.filePath}/{self.fileName}.ghd").unlink()
                print("删除成功！")

                # 删除记录文件
                with open("./history", "r", encoding="utf-8") as f:
                    _ = f.read()

                _ = _.replace(str({"url": self.url, "fileName": self.fileName, "filePath": str(self.filePath),
                                   "blockNum": self.maxBlockNum}) + "\n", "")

                with open("./history", "w", encoding="utf-8") as f:
                    f.write(_)

                isDeleted = True
                tryCount = 5

            except FileNotFoundError:
                isDeleted = True
                tryCount = 5
            except Exception as e:
                print(f"似乎无法删除文件, 错误信息: {e}")
                tryCount += 1

            sleep(0.1)

        self.deleteLater()

    def __changeInfo(self, content: str):

        process = int(content)

        duringLastSecondProcess = process - self.lastProcess

        self.speedLable.setText(f"{getReadableSize(duringLastSecondProcess)}/s")
        self.processLabel.setText(f"{getReadableSize(process)}/{getReadableSize(self.task.fileSize)}")
        self.ProgressBar.setValue((process / self.task.fileSize) * 100)

        self.lastProcess = process

    def taskFinished(self):
        self.pauseButton.setDisabled(True)
        self.cancelButton.setDisabled(True)
        self.speedLable.setText("下载完成！正在校验MD5...")

        # 尝试删除历史文件
        tryCount = 0
        isDeleted = False

        while not isDeleted and tryCount <= 3:
            try:
                # 删除记录文件
                with open("./history", "r", encoding="utf-8") as f:
                    _ = f.read()

                _ = _.replace(str({"url": self.url, "fileName": self.fileName, "filePath": str(self.filePath),
                                   "blockNum": self.maxBlockNum}) + "\n", "")

                with open("./history", "w", encoding="utf-8") as f:
                    f.write(_)

                isDeleted = True
                tryCount = 5
            except FileNotFoundError:
                isDeleted = True
                tryCount = 5
            except Exception as e:
                print(f"似乎无法删除文件, 错误信息: {e}")
                tryCount += 1

            sleep(0.1)

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
