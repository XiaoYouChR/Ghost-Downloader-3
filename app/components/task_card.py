import hashlib
import pickle
from pathlib import Path
from typing import Type

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
from ..common.download_task import DownloadTask, DownloadTaskManager
from ..common.methods import getReadableSize, openFile
from ..common.task_base import TaskManagerBase
from ..view.pop_up_window import FinishedPopUpWindow


class TaskCard(CardWidget, Ui_TaskCard):
    """
    taskManagerCls 为 taskManager 的实例化方法
    接受没有 fileName 或 未知 fileSize 的 taskManager, 待 taskInited 后读取获取到 LinkInfo 重设界面
    """

    taskStatusChanged = Signal()

    def __init__(self, taskManagerCls: Type[TaskManagerBase], url:str, headers: dict, preBlockNum: int, fileName: str, filePath:str, status: str,
                 notCreatedHistoryFile:bool, fileSize: int = -1, parent=None):
        super().__init__(parent=parent)

        self.setupUi(self)

        # 初始化 TaskManager
        self.taskManager = taskManagerCls(url, headers, preBlockNum, filePath, fileName, fileSize, self)
        self.taskManager.taskInited.connect(self.__onTaskInited)
        self.taskManager.taskFinished.connect(self.__onTaskFinished)
        self.taskManager.taskGotWrong.connect(self.__onTaskError)
        self.taskManager.progressInfoChanged.connect(self.__updateProgress)
        self.taskManager.speedChanged.connect(self.__updateSpeed)

        self.status = status  # 状态有: working, waiting, paused, finished. 不希望被迁移到 taskManagerBase
        self.notCreateHistoryFile = notCreatedHistoryFile  # 事实上用来记录历史文件是否已经创建
        self.ableToParallelDownload = False # 记录是否可以并行下载(进度条的显示方式和进度信息的显示方式)
        self.__clickPos = None # 记录鼠标点击位置, 用来在 dragEvent 中计算鼠标移动距离

        self.__showInfo("若任务初始化过久，请检查网络连接后重试.")

        self.cancelButton.clicked.connect(self.cancelTask)
        self.folderButton.clicked.connect(lambda: openFile(filePath))

        if not self.status == "finished":  # 不是已完成的任务才要进行的操作
            self.pauseButton.clicked.connect(self.pauseTask)
            self.pauseButton.setEnabled(False)  # 不允许暂停, 因为 __InitThread 无法停止
            self.__onTaskInited(False)  # 有就显示, 没就等信号 TaskInited

            if self.taskManager.fileName and self.taskManager.fileSize != -1:   # 先显示 fileName
                self.pauseButton.setEnabled(True)   # 这种情况下 __InitThread 要不然不启动, 要不然运行完了

        elif self.status == "finished": # 已完成的任务, 就当个傀儡
            _ = QFileIconProvider().icon(QFileInfo(f"{self.taskManager.filePath}/{self.fileName}")).pixmap(128, 128)  # 自动获取图标, Qt 有 Bug, 会获取到一个只有左上角一点点的图像

            if _:
                pixmap = _
            else:
                pixmap = QPixmap(":/image/logo.png")    # 无法获取

            self.titleLabel.setText(self.fileName)
            self.LogoPixmapLabel.setPixmap(pixmap)
            self.LogoPixmapLabel.setFixedSize(70, 70)

            self.__onTaskFinished() # 显示完成信息, 里面处理了 pauseBtn 信号的连接

        if self.status == "working":  # 开始任务
            self.taskManager.start()
        elif self.status == "paused" or self.status == "waiting":   # 不开始
            self.pauseButton.setIcon(FIF.PLAY)

    def __onTaskError(self, exception: str):
        self.__showInfo(f"Error: {exception}")
        if not self.fileName or self.fileSize == -1:
            self.status = "paused"
            self.pauseButton.setEnabled(True)
            self.pauseButton.setIcon(FIF.PLAY)
            self.titleLabel.setText("任务初始化失败")

    def __onTaskInited(self, ableToParallelDownload: bool):
        self.fileName = self.taskManager.fileName
        self.fileSize = self.taskManager.fileSize
        self.ableToParallelDownload = ableToParallelDownload

        # _ = QFileIconProvider().icon(QFileInfo(f"{self.taskManager.filePath}/{self.fileName}")).pixmap(48, 48).scaled(70, 70, aspectMode=Qt.AspectRatioMode.KeepAspectRatio,
        #                            mode=Qt.TransformationMode.SmoothTransformation)  # 自动获取图标
        _ = QFileIconProvider().icon(QFileInfo(f"{self.taskManager.filePath}/{self.fileName}")).pixmap(128, 128)  # 自动获取图标, Qt 有 Bug, 会获取到一个只有左上角一点点的图像

        if _:
            pixmap = _
        else:
            pixmap = QPixmap(":/image/logo.png")    # 无法获取

        # 显示信息
        self.titleLabel.setText(self.fileName)
        self.LogoPixmapLabel.setPixmap(pixmap)
        self.LogoPixmapLabel.setFixedSize(70, 70)

        if self.status == "paused":
            self.__showInfo("任务已经暂停")
        
        if self.status == "waiting":
            self.__showInfo("排队中...")

        if self.ableToParallelDownload: # 可以并行下载, pauseBtn 可用
            self.progressBar.deleteLater()
            self.progressBar = TaskProgressBar(self.taskManager.preBlockNum, self)
            self.progressBar.setObjectName(u"progressBar")
            self.verticalLayout.addWidget(self.progressBar)

            # 写入未完成任务记录文件，以供下次打开时继续下载
            if self.fileName and not self.notCreateHistoryFile:
                self.taskManager.updateTaskRecord(self.status)
                self.notCreateHistoryFile = True

            self.pauseButton.setEnabled(True)
        else:   # 可以并行下载, pauseBtn 事实上已被禁用
            self.progressBar.deleteLater()
            self.progressBar = IndeterminateProgressBar(self)
            self.progressBar.setObjectName(u"progressBar")
            self.verticalLayout.addWidget(self.progressBar)

    def pauseTask(self):
        """
        当不能并行下载的时候实际上也不可能触发,
        因此不用考虑 updateTaskRecord 意外记录不应该记录的任务的问题
        """
        if self.status == "working":  # 暂停
            self.pauseButton.setDisabled(True)
            self.pauseButton.setIcon(FIF.PLAY)

            try:
                self.taskManager.stop()
                self.taskManager.updateTaskRecord("paused") # 改变记录状态

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
                self.taskManager.start()
                self.taskManager.updateTaskRecord("working")

            finally:    # 得让 self.__initThread 运行完才能运行暂停! 不要恢复 self.pauseBtn 的状态
                self.__showInfo("任务正在开始")
                self.status = "working"

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
                    self.pauseTask()    # 先暂停

                self.taskManager.cancel(completely)

            except Exception as e:
                logger.warning(f"Task 删除时遇到错误: {e}")

            finally:
                try:
                    # 删除记录文件
                    self.taskManager.updateTaskRecord("deleted")

                finally:
                    # Remove TaskCard, 不知道怎么改得更好😵
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

            progress = 0

            for e, i in enumerate(content):
                _ = i["progress"] - i["start"]
                self.progressBar.progressBarList[e].setValue((_ / (i["end"] - i["start"])) * 100)
                progress += _

            self.progressLabel.setText(f"{getReadableSize(_)}/{getReadableSize(self.taskManager.fileSize)}")

        else: # 不能并行下载
            self.progressLabel.setText(f"{getReadableSize(self.taskManager.progress)}")

    def __updateSpeed(self, avgSpeed: int):

        self.speedLabel.setText(f"{getReadableSize(avgSpeed)}/s")

        if self.ableToParallelDownload:
            # 计算剩余时间，并转换为 MM:SS
            try:
                leftTime = (self.taskManager.fileSize - self.taskManager.progress) / avgSpeed
                self.leftTimeLabel.setText(f"{int(leftTime // 60):02d}:{int(leftTime % 60):02d}")
            except ZeroDivisionError:
                self.leftTimeLabel.setText("Infinity")
        else:
            self.leftTimeLabel.setText("Unknown")

    def __onTaskFinished(self):
        self.pauseButton.setDisabled(True)
        self.cancelButton.setDisabled(True)

        self.clicked.connect(lambda: openFile(f"{self.taskManager.filePath}/{self.fileName}"))

        _ = QFileInfo(f"{self.taskManager.filePath}/{self.fileName}").lastModified().toString("yyyy-MM-dd hh:mm:ss")

        self.__showInfo(f"完成时间: {_}" if _ else "文件已被删除")

        self.progressBar.deleteLater()

        self.progressBar = ProgressBar(self)
        self.progressBar.setObjectName(u"progressBar")
        self.verticalLayout.addWidget(self.progressBar)

        self.progressBar.setValue(100)

        try:  # 程序启动时不要发
            if self.window().tray:
                FinishedPopUpWindow.showPopUpWindow(f"{self.taskManager.filePath}/{self.fileName}", self.window())
        except:
            pass

        if not self.status == "finished":  # 不是自动创建的已完成任务
            # 改变记录状态
            self.taskManager.updateTaskRecord("finished")

            # 再获取一次图标
            _ = QFileIconProvider().icon(QFileInfo(f"{self.taskManager.filePath}/{self.fileName}")).pixmap(128, 128)  # 自动获取图标

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

    def showHashAlgorithmDialog(self):

        algorithms = ["MD5", "SHA1","SHA224", "SHA256","SHA384", "SHA512", "BLAKE2B", "BLAKE2S", "SHA3_224", "SHA3_256", "SHA3_384", "SHA3_512", "SHAKE_128", "SHAKE_256"]

        dialog = CustomInputDialog("选择校验算法", "请选择一个校验算法:", algorithms, self.window())
        selected_algorithm, ok = dialog.get_item()

        if ok and selected_algorithm:
            self.runCalcHashTask(selected_algorithm)

    def runCalcHashTask(self, algorithm):
        self.progressBar:ProgressBar
        self.__showInfo(f"正在校验 {algorithm}, 请稍后...")
        self.pauseButton.setDisabled(True)
        self.progressBar.setMaximum(Path(f"{self.taskManager.filePath}/{self.fileName}").stat().st_size)  # 设置进度条最大值

        self.calcTask = CalcHashThread(f"{self.taskManager.filePath}/{self.fileName}", algorithm)
        self.calcTask.calcProgress.connect(lambda x: self.progressBar.setValue(int(x)))
        self.calcTask.returnHash.connect(self.whenHashCalcFinished)
        self.calcTask.start()

    def whenHashCalcFinished(self, result: str):
        self.progressBar:ProgressBar
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
                mimeData.setUrls([QUrl.fromLocalFile(f'{self.taskManager.filePath}/{self.fileName}')])
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

