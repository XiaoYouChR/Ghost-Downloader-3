import hashlib
import pickle
from pathlib import Path

from PySide6.QtCore import QThread, Signal, QFileInfo, QMimeData, Qt, QUrl
from PySide6.QtGui import QPixmap, QDrag
from PySide6.QtWidgets import QFileIconProvider
from loguru import logger
from qfluentwidgets import CardWidget, IndeterminateProgressBar, ProgressBar
from qfluentwidgets import FluentIcon as FIF

from .Ui_TaskCard import Ui_TaskCard
from .custom_components import TaskProgressBar
from .custom_dialogs import DelDialog, CustomInputDialog
from ..common.config import cfg
from ..common.download_task import DownloadTask
from ..common.methods import getReadableSize, openFile
from ..view.pop_up_window import PopUpWindow

class TaskCard(CardWidget, Ui_TaskCard):
    taskStatusChanged = Signal()

    def __init__(self, url, path, maxBlockNum: int, headers: dict, name: str = None, status: str = "working",
                 parent=None, autoCreated=False):
        super().__init__(parent=parent)

        self.setupUi(self)

        # 初始化参数
        self.url = url
        self.headers = headers
        self.fileName = name
        self.filePath = path
        self.maxBlockNum = maxBlockNum
        self.status = status  # working waiting paused finished
        self.autoCreated = autoCreated  # 事实上用来记录历史文件是否已经创建
        self.ableToParallelDownload = False # 是否可以并行下载

        self.__clickPos = None

        # Show Information
        self.__showInfo("若任务初始化过久，请检查网络连接后重试.")
        self.titleLabel.setText("正在初始化任务...")

        self.LogoPixmapLabel.setPixmap(QPixmap(":/image/logo.png"))
        self.LogoPixmapLabel.setFixedSize(70, 70)

        self.progressBar = ProgressBar(self)
        self.progressBar.setObjectName(u"progressBar")
        self.verticalLayout.addWidget(self.progressBar)

        if not self.status == "finished":  # 不是已完成的任务才要进行的操作
            self.pauseButton.setDisabled(True)

            if name:
                self.task = DownloadTask(url, headers, maxBlockNum, path, name)

                self.__onTaskInited(self.ableToParallelDownload)

                if self.status == "paused":
                    self.__showInfo("任务已经暂停")
                elif self.status == "waiting":
                    self.__showInfo("排队中...")

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

            self.titleLabel.setText(self.fileName)
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
        elif self.status == "paused" or self.status == "waiting":
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
        if not self.fileName:
            self.status = "paused"
            self.pauseButton.setEnabled(True)
            self.pauseButton.setIcon(FIF.PLAY)
            self.titleLabel.setText("任务初始化失败")

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
        self.titleLabel.setText(self.fileName)
        self.LogoPixmapLabel.setPixmap(pixmap)
        self.LogoPixmapLabel.setFixedSize(70, 70)

        if self.status == "waiting":
            self.__showInfo("排队中...")

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

        elif self.status == "paused" or self.status == "waiting":  # 继续

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
                # 得让 self.__initThread 运行完才能运行暂停！ self.pauseButton.setEnabled(True)

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
                logger.warning(f"Task 删除时遇到错误: {e}")

            finally:
                try:
                    # 删除记录文件
                    self.updateTaskRecord("deleted")

                finally:
                    # Remove Widget
                    self.parent().parent().parent().expandLayout.takeAt(self.parent().parent().parent().expandLayout.indexOf(self))
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

    def __updateSpeed(self, avgSpeed: int):

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
            if self.window().tray:
                PopUpWindow.showPopUpWindow(f"{self.filePath}/{self.fileName}", self.window())
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
        self.pauseButton.clicked.connect(self.showHashAlgorithmDialog)
        self.pauseButton.setDisabled(False)
        self.cancelButton.setDisabled(False)

        self.taskStatusChanged.emit()

    def __connectSignalToSlot(self):
        self.task.taskInited.connect(self.__onTaskInited)
        self.task.workerInfoChanged.connect(self.__updateProgress)
        self.task.speedChanged.connect(self.__updateSpeed)

        self.task.taskFinished.connect(self.__onTaskFinished)

        self.task.gotWrong.connect(self.__onTaskError)

    def showHashAlgorithmDialog(self):

        algorithms = ["MD5", "SHA1","SHA224", "SHA256","SHA384", "SHA512", "BLAKE2B", "BLAKE2S", "SHA3_224", "SHA3_256", "SHA3_384", "SHA3_512", "SHAKE_128", "SHAKE_256"]

        dialog = CustomInputDialog("选择校验算法", "请选择一个校验算法:", algorithms, self.window())
        selected_algorithm, ok = dialog.get_item()

        if ok and selected_algorithm:
            self.runCalcHashTask(selected_algorithm)

    def runCalcHashTask(self, algorithm):
        self.__showInfo(f"正在校验 {algorithm}, 请稍后...")
        self.pauseButton.setDisabled(True)
        self.progressBar.setMaximum(Path(f"{self.filePath}/{self.fileName}").stat().st_size)  # 设置进度条最大值

        self.calcTask = CalcHashThread(f"{self.filePath}/{self.fileName}", algorithm)
        self.calcTask.calcProgress.connect(lambda x: self.progressBar.setValue(int(x)))
        self.calcTask.returnHash.connect(self.whenHashCalcFinished)
        self.calcTask.start()

    def whenHashCalcFinished(self, result: str):
        self.calcTask.deleteLater()
        self.progressBar.setMaximum(100)
        self.progressBar.setValue(100)
        self.__showInfo(f"校验完成，文件的 {self.calcTask.algorithm} 是: {result}")
        # 把校验按钮变成复制按钮
        from PySide6.QtWidgets import QApplication
        self.pauseButton.setIcon(FIF.COPY)
        self.pauseButton.clicked.disconnect()
        self.pauseButton.clicked.connect(lambda: QApplication.clipboard().setText(result))
        self.pauseButton.setDisabled(False)

    def __calcDistance(self, startPos, endPos):
        return (startPos.x() - endPos.x()) ** 2 + (startPos.y() - endPos.y()) ** 2

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.__clickPos = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.__clickPos and self.status == "finished":
            if self.__calcDistance(self.__clickPos, event.pos()) >= 4:
                drag = QDrag(self)
                mimeData = QMimeData()
                mimeData.setUrls([QUrl.fromLocalFile(f'{self.filePath}/{self.fileName}')])
                drag.setMimeData(mimeData)
                drag.setPixmap(self.LogoPixmapLabel.pixmap().copy())
                drag.exec(Qt.CopyAction | Qt.MoveAction)
        event.accept()



class CalcHashThread(QThread):
    calcProgress = Signal(str)  # 因为C++ int最大值仅支持到2^31 PyQt又没有Qint类 故只能使用str代替
    returnHash = Signal(str)

    def __init__(self, fileResolvedPath: str, algorithm: str, parent=None):
        super().__init__(parent=parent)
        self.fileResolvedPath = fileResolvedPath
        self.algorithm = algorithm

    def run(self):
        hashAlgorithm = getattr(hashlib, self.algorithm.lower())()
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

        if self.algorithm in ["SHAKE_128", "SHAKE_256"]:
            result = hashAlgorithm.hexdigest(32)
        else:
            result = hashAlgorithm.hexdigest()

        self.returnHash.emit(result)

