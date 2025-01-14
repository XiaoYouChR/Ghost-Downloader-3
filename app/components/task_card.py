import hashlib
import pickle
from pathlib import Path

from PySide6.QtCore import QThread, Signal, QFileInfo
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFileIconProvider
from loguru import logger
from qfluentwidgets import CardWidget, IndeterminateProgressBar, ProgressBar
from qfluentwidgets import FluentIcon as FIF

from .Ui_TaskCard import Ui_TaskCard
from .del_dialog import DelDialog
from .task_progress_bar import TaskProgressBar
from ..common.config import cfg
from ..common.download_task import DownloadTask
from ..common.methods import getProxy, getReadableSize, openFile

# 获取系统代理
proxy = getProxy()

class TaskCard(CardWidget, Ui_TaskCard):
    taskStatusChanged = Signal()

    def __init__(self, url, path, maxBlockNum: int, headers: dict, name: str = None, status: str = "working",
                 parent=None, autoCreated=False):
        super().__init__(parent=parent)

        self.setupUi(self)

        # 初始化参数
        self.url = url
        self.headers = headers
        self.filePath = path
        self.maxBlockNum = maxBlockNum
        self.status = status  # working paused finished
        self.autoCreated = autoCreated  # 事实上用来记录历史文件是否已经创建
        self.ableToParallelDownload = False # 是否可以并行下载

        # Show Information
        self.__showInfo("若任务初始化过久，请检查网络连接后重试.")
        self.TitleLabel.setText("正在初始化任务...")

        self.LogoPixmapLabel.setPixmap(QPixmap(":/image/logo.png"))
        self.LogoPixmapLabel.setFixedSize(70, 70)

        self.progressBar = ProgressBar(self)
        self.progressBar.setObjectName(u"progressBar")
        self.verticalLayout.addWidget(self.progressBar)

        if name:
            self.fileName = name

        if not self.status == "finished":  # 不是已完成的任务才要进行的操作
            self.pauseButton.setDisabled(True)

            if name:
                self.task = DownloadTask(url, headers, maxBlockNum, path, name)

                self.__onTaskInited(self.ableToParallelDownload)

                if self.status == "paused":
                    self.__showInfo("任务已经暂停")

            else:
                self.task = DownloadTask(url, headers, maxBlockNum, path)

            self.__connectSignalToSlot()

        elif self.status == "finished":
            # TODO 超分辨率触发条件
            _ = QFileIconProvider().icon(QFileInfo(f"{self.filePath}/{self.fileName}")).pixmap(128, 128)  # 自动获取图标

            if _:
                pixmap = _
            else:
                pixmap = QPixmap(":/image/logo.png")

            self.TitleLabel.setText(self.fileName)
            self.LogoPixmapLabel.setPixmap(pixmap)
            self.LogoPixmapLabel.setFixedSize(70, 70)

            self.__onTaskFinished()

        # 连接信号到槽
        self.pauseButton.clicked.connect(self.pauseTask)
        self.cancelButton.clicked.connect(self.cancelTask)
        self.folderButton.clicked.connect(lambda: openFile(path))

        if self.status == "working":
            # 开始下载
            self.task.start()
        elif self.status == "paused":
            self.pauseButton.setIcon(FIF.PLAY)

    def updateTaskRecord(self, newStatus: str):
        recordPath = "{}/Ghost Downloader 记录文件".format(cfg.appPath)

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
        for record in records:
            if (record["url"] == self.url and
                    record["fileName"] == self.fileName and
                    record["filePath"] == str(self.filePath) and
                    record["blockNum"] == self.maxBlockNum and
                    record["headers"] == self.headers):
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
                "blockNum": self.maxBlockNum,
                "status": self.status,
                "headers": self.headers
            })

        # 写回记录文件
        with open(recordPath, "wb") as f:
            for record in updatedRecords:
                pickle.dump(record, f)


    def __onTaskError(self, exception: str):
        self.__showInfo(f"Error: {exception}")

    def __onTaskInited(self, ableToParallelDownload: bool):
        self.fileName = self.task.fileName
        self.ableToParallelDownload = ableToParallelDownload

        # TODO 因为Windows会返回已经处理过的只有左上角一点点的图像，所以需要超分辨率触发条件
        # _ = QFileIconProvider().icon(QFileInfo(f"{self.filePath}/{self.fileName}")).pixmap(48, 48).scaled(70, 70, aspectMode=Qt.AspectRatioMode.KeepAspectRatio,
        #                            mode=Qt.TransformationMode.SmoothTransformation)  # 自动获取图标
        _ = QFileIconProvider().icon(QFileInfo(f"{self.filePath}/{self.fileName}")).pixmap(128, 128)  # 自动获取图标

        if _:
            pixmap = _
        else:
            pixmap = QPixmap(":/image/logo.png")

        # 显示信息
        self.TitleLabel.setText(self.fileName)
        self.LogoPixmapLabel.setPixmap(pixmap)
        self.LogoPixmapLabel.setFixedSize(70, 70)

        if self.ableToParallelDownload:
            self.progressBar.deleteLater()
            self.progressBar = TaskProgressBar(self.maxBlockNum, self)
            self.progressBar.setObjectName(u"progressBar")

            self.verticalLayout.addWidget(self.progressBar)

            # 写入未完成任务记录文件，以供下次打开时继续下载
            if self.fileName and not self.autoCreated:
                self.updateTaskRecord(self.status)
                self.autoCreated = True

            self.pauseButton.setEnabled(True)
        else:
            self.progressBar.deleteLater()
            self.progressBar = IndeterminateProgressBar(self)
            self.progressBar.setObjectName(u"progressBar")
            self.verticalLayout.addWidget(self.progressBar)

    def pauseTask(self):
        if self.status == "working":  # 暂停
            self.pauseButton.setDisabled(True)
            self.pauseButton.setIcon(FIF.PLAY)

            try:
                self.task.stop()

                # self.task.terminate()
                self.task.wait()
                self.task.deleteLater()

                # 改变记录状态
                self.updateTaskRecord("paused")

            except Exception as e:
                logger.warning(f"Task:{self.fileName}, 暂停时遇到错误: {repr(e)}")

            finally:
                self.__showInfo("任务已经暂停")
                self.status = "paused"
                self.pauseButton.setEnabled(True)

        elif self.status == "paused":  # 继续
            self.pauseButton.setDisabled(True)
            self.pauseButton.setIcon(FIF.PAUSE)

            try:
                self.task = DownloadTask(self.url, self.headers, self.maxBlockNum, self.filePath, self.fileName)
            except:  # TODO 没有 fileName 的情况
                self.task = DownloadTask(self.url, self.headers, self.maxBlockNum, self.filePath)

            self.__connectSignalToSlot()

            self.task.start()

            try:
                # 改变记录状态
                self.updateTaskRecord("working")

            finally:
                self.__showInfo("任务正在开始")
                self.status = "working"
                # 得让 self.__tempThread 运行完才能运行暂停！ self.pauseButton.setEnabled(True)

        self.taskStatusChanged.emit()

    def cancelTask(self, surely=False, completely=False):

        if not surely:
            dialog = DelDialog(self.window())
            if dialog.exec():
                completely = dialog.checkBox.isChecked()
                surely = True
            dialog.deleteLater()

        if surely:
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

            except Exception as e:
                logger.warning(f"Task:{self.fileName}, 删除时遇到错误: {e}")

            finally:
                try:
                    # 删除记录文件
                    self.updateTaskRecord("deleted")

                finally:
                    # Remove Widget
                    self.parent().parent().parent().expandLayout.removeWidget(self)
                    self.parent().parent().parent().cards.remove(self)
                    self.taskStatusChanged.emit()
                    self.deleteLater()

    def __showInfo(self, content: str):
        # 隐藏 statusHorizontalLayout
        self.speedLabel.hide()
        self.leftTimeLabel.hide()
        self.progressLabel.hide()

        # 显示 infoLayout
        self.infoLabel.show()
        self.infoLabel.setText(content)

    def __hideInfo(self):
        self.infoLabel.hide()

        self.speedLabel.show()
        self.leftTimeLabel.show()
        self.progressLabel.show()

    def __updateProgress(self, content: list):
        # 如果还在显示消息状态，则调用 __hideInfo
        if self.infoLabel.isVisible():
            self.__hideInfo()

        if self.ableToParallelDownload:
            # 理论来说 worker 直增不减 所以ProgressBar不用考虑线程减少的问题
            _ = len(content) - self.progressBar.blockNum
            if _:
                self.progressBar.addProgressBar(content, _)

            for e, i in enumerate(content):
                self.progressBar.progressBarList[e].setValue(((i["progress"] - i["start"]) / (i["end"] - i["start"])) * 100)

            self.progressLabel.setText(f"{getReadableSize(self.task.progress)}/{getReadableSize(self.task.fileSize)}")

        else: # 不能并行下载
            self.progressLabel.setText(f"{getReadableSize(self.task.progress)}")

    def __UpdateSpeed(self, avgSpeed: int):

        self.speedLabel.setText(f"{getReadableSize(avgSpeed)}/s")

        if self.ableToParallelDownload:
            # 计算剩余时间，并转换为 MM:SS
            try:
                leftTime = (self.task.fileSize - self.task.progress) / avgSpeed
                self.leftTimeLabel.setText(f"{int(leftTime // 60):02d}:{int(leftTime % 60):02d}")
            except ZeroDivisionError:
                self.leftTimeLabel.setText("Infinity")
        else:
            self.leftTimeLabel.setText("Unknown")

    def __onTaskFinished(self):
        self.pauseButton.setDisabled(True)
        self.cancelButton.setDisabled(True)

        self.clicked.connect(lambda: openFile(f"{self.filePath}/{self.fileName}"))

        self.__showInfo("任务已经完成")

        self.progressBar.deleteLater()

        self.progressBar = ProgressBar(self)
        self.progressBar.setObjectName(u"progressBar")
        self.verticalLayout.addWidget(self.progressBar)

        self.progressBar.setValue(100)

        try:  # 程序启动时不要发
            self.window().tray.showMessage(self.window().windowTitle(), f"任务 {self.fileName} 已完成！", self.window().windowIcon())
        except:
            pass

        if not self.status == "finished":  # 不是自动创建的已完成任务
            # 改变记录状态
            self.updateTaskRecord("finished")

            # 再获取一次图标
            _ = QFileIconProvider().icon(QFileInfo(f"{self.filePath}/{self.fileName}")).pixmap(128, 128)  # 自动获取图标
            if _:
                pass
            else:
                _ = QPixmap(":/image/logo.png")
            self.LogoPixmapLabel.setPixmap(_)
            self.LogoPixmapLabel.setFixedSize(70, 70)

        self.status = "finished"

        # 将暂停按钮改成校验按钮
        self.pauseButton.setIcon(FIF.UPDATE)
        self.pauseButton.clicked.disconnect()
        self.pauseButton.clicked.connect(self.runCalcMD5Task)
        self.pauseButton.setDisabled(False)
        self.cancelButton.setDisabled(False)

        self.taskStatusChanged.emit()

    def __connectSignalToSlot(self):
        self.task.taskInited.connect(self.__onTaskInited)
        self.task.workerInfoChanged.connect(self.__updateProgress)
        self.task.speedChanged.connect(self.__UpdateSpeed)

        self.task.taskFinished.connect(self.__onTaskFinished)

        self.task.gotWrong.connect(self.__onTaskError)

    def runCalcMD5Task(self):
        self.__showInfo("正在校验 MD5, 请稍后...")
        self.pauseButton.setDisabled(True)
        self.progressBar.setMaximum(Path(f"{self.filePath}/{self.fileName}").stat().st_size)  # 设置进度条最大值

        self.calcTask = CalcMD5Thread(f"{self.filePath}/{self.fileName}")
        self.calcTask.calcProgress.connect(lambda x: self.progressBar.setValue(int(x)))
        self.calcTask.returnMD5.connect(self.whenMD5CalcFinished)
        self.calcTask.start()

    def whenMD5CalcFinished(self, result: str):
        self.calcTask.deleteLater()
        self.__showInfo(f"校验完成，文件的MD5值是: {result}")
        # 把校验按钮变成复制按钮
        from PySide6.QtWidgets import QApplication
        self.pauseButton.setIcon(FIF.COPY)
        self.pauseButton.clicked.disconnect()
        self.pauseButton.clicked.connect(lambda: QApplication.clipboard().setText(result))
        self.pauseButton.setDisabled(False)

class CalcMD5Thread(QThread):
    calcProgress = Signal(str)  # 因为C++ int最大值仅支持到2^31 PyQt又没有Qint类 故只能使用str代替
    returnMD5 = Signal(str)

    def __init__(self, fileResolvedPath: str, parent=None):
        super().__init__(parent=parent)
        self.fileResolvedPath = fileResolvedPath

    def run(self):
        hashAlgorithm = getattr(hashlib, "md5")()
        progress = 0

        with open(self.fileResolvedPath, "rb") as file:
            chunk_size = 1048576  # 1MiB chunks
            while True:
                chunk = file.read(chunk_size)
                if not chunk:
                    break
                hashAlgorithm.update(chunk)
                progress += 1048576
                self.calcProgress.emit(str(progress))

        result = hashAlgorithm.hexdigest()

        self.returnMD5.emit(result)
