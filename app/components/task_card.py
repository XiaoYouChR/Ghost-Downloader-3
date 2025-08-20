import hashlib
import pickle
from pathlib import Path

from PySide6.QtCore import QThread, Signal, QFileInfo, QMimeData, Qt, QUrl
from PySide6.QtGui import QPixmap, QDrag
from PySide6.QtWidgets import QFileIconProvider, QApplication
from loguru import logger
from qfluentwidgets import CardWidget, IndeterminateProgressBar, ProgressBar, MenuAnimationType, RoundMenu, Action
from qfluentwidgets import FluentIcon as FIF

from .Ui_TaskCard import Ui_TaskCard
from .custom_components import TaskProgressBar
from .custom_dialogs import DelDialog, CustomInputDialog
from ..common.config import cfg
from ..common.download_task import DownloadTask
from ..common.methods import getReadableSize, openFile, openFolder
from ..view.pop_up_window import FinishedPopUpWindow


class MimeData(QMimeData):
    def __init__(self, filepath, filename, url):
        super().__init__()
        self.filepath = filepath
        self.filename = filename
        self.url = url

    def toFile(self):
        self.clear()
        self.setData("text/uri-list", QUrl.fromLocalFile(f'{self.filepath}/{self.filename}').toEncoded())
        return self

    def toUrl(self):
        self.clear()
        self.setData('application/x-gd3-copy', b'True')
        self.setText(self.url)
        return self

class TaskCard(CardWidget, Ui_TaskCard):
    taskStatusChanged = Signal()

    def __init__(self, url: str, fileName: str, filePath: str, preBlockNum: int, headers: dict, status: str,
                 notCreatedHistoryFile: bool, fileSize: int = -1, parent=None):
        super().__init__(parent=parent)

        self.setupUi(self)

        # 初始化参数
        self.url = url
        self.headers = headers
        self.fileName = fileName
        self.filePath = filePath
        self.preBlockNum = preBlockNum
        self.status = status  # working waiting paused finished
        self.notCreateHistoryFile = notCreatedHistoryFile  # 事实上用来记录历史文件是否已经创建
        self.fileSize = fileSize
        self.ableToParallelDownload = False  # 是否可以并行下载

        self.mimedata = MimeData(self.filePath, self.fileName, self.url)  # 预生成mime数据

        self.task: DownloadTask = None

        self.__clickPos = None

        # Show Information
        self.__showInfo(self.tr("若任务初始化过久，请检查网络连接后重试."))
        self.titleLabel.setText(self.tr("正在初始化任务..."))

        self.LogoPixmapLabel.setPixmap(QPixmap(":/image/logo.png"))
        self.LogoPixmapLabel.setFixedSize(48, 48)

        self.progressBar = ProgressBar(self)
        self.progressBar.setObjectName(u"progressBar")
        self.verticalLayout.addWidget(self.progressBar)

        if not self.status == "finished":  # 不是已完成的任务才要进行的操作
            self.__launchTask()

        elif self.status == "finished":
            # TODO 超分辨率触发条件
            _ = QFileIconProvider().icon(QFileInfo(f"{self.filePath}/{self.fileName}")).pixmap(48, 48).scaled(128, 128, aspectMode=Qt.AspectRatioMode.KeepAspectRatio,
                                   mode=Qt.TransformationMode.SmoothTransformation)  # 自动获取图标

            if _:
                pixmap = _
            else:
                pixmap = QPixmap(":/image/logo.png")

            self.titleLabel.setText(self.fileName)
            self.LogoPixmapLabel.setPixmap(pixmap)
            self.LogoPixmapLabel.setFixedSize(48, 48)

            self.__onTaskFinished()

        # 连接信号到槽
        self.pauseButton.clicked.connect(self.pauseTask)
        self.cancelButton.clicked.connect(self.cancelTask)
        self.folderButton.clicked.connect(lambda: openFolder(self.filePath + '/' + self.fileName))

    def __launchTask(self):
        # self.pauseButton.setDisabled(True)
        self.changeButtonStatus(enabled=False)
        if self.fileName:
            self.__instantiateTask(
                self.url, self.filePath, self.preBlockNum, self.headers, self.fileSize, self.fileName)

            self.__onTaskInited(self.ableToParallelDownload)

            if self.status == "paused":
                self.__showInfo(self.tr("任务已经暂停"))
            elif self.status == "waiting":
                self.__showInfo(self.tr("排队中..."))

        else:
            self.__instantiateTask(self.url, self.filePath, self.preBlockNum, self.headers, self.fileSize)

        self.__connectSignalToSlot()

        if self.status == "working":
            # 开始下载
            self.task.start()
        elif self.status == "paused" or self.status == "waiting":
            # self.pauseButton.setIcon(FIF.PLAY)
            self.changeButtonStatus(icon=FIF.PLAY)

    def __instantiateTask(self, url: str, filePath: str, preBlockNum: int, headers: dict, fileSize: int = -1,
                          fileName: str = None):
        autoSpeedUp = cfg.autoSpeedUp.value
        self.task = DownloadTask(url, headers, preBlockNum, filePath, fileName, autoSpeedUp, fileSize)

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
                    record["blockNum"] == self.preBlockNum and
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
                "blockNum": self.preBlockNum,
                "status": self.status,
                "headers": self.headers,
                "fileSize": self.fileSize
            })

        # 写回记录文件
        with open(recordPath, "wb") as f:
            for record in updatedRecords:
                pickle.dump(record, f)

    def __onTaskError(self, exception: str):
        self.__showInfo(self.tr("错误: ") + exception)
        if not self.fileName:
            self.status = "paused"
            # self.pauseButton.setEnabled(True)
            # self.pauseButton.setIcon(FIF.PLAY)
            self.changeButtonStatus(enabled=True, icon=FIF.PLAY)
            self.titleLabel.setText(self.tr("任务初始化失败"))

    def __calcDistance(self, startPos, endPos):
        return (startPos.x() - endPos.x()) ** 2 + (startPos.y() - endPos.y()) ** 2

    def __onTaskInited(self, ableToParallelDownload: bool):
        self.fileName = self.task.fileName
        self.fileSize = self.task.fileSize
        self.ableToParallelDownload = ableToParallelDownload

        _ = QFileIconProvider().icon(QFileInfo(f"{self.filePath}/{self.fileName}")).pixmap(48, 48).scaled(128, 128, aspectMode=Qt.AspectRatioMode.KeepAspectRatio,
                                   mode=Qt.TransformationMode.SmoothTransformation)  # 自动获取图标
        # _ = QFileIconProvider().icon(QFileInfo(f"{self.filePath}/{self.fileName}")).pixmap(128, 128)  # 自动获取图标

        if _:
            pixmap = _
        else:
            pixmap = QPixmap(":/image/logo.png")

        # 显示信息
        self.titleLabel.setText(self.fileName)
        self.LogoPixmapLabel.setPixmap(pixmap)
        self.LogoPixmapLabel.setFixedSize(48, 48)

        if self.status == "waiting":
            self.__showInfo(self.tr("排队中..."))

        if self.ableToParallelDownload:
            self.progressBar.deleteLater()
            self.progressBar = TaskProgressBar(self.preBlockNum, self)
            self.progressBar.setObjectName(u"progressBar")

            self.verticalLayout.addWidget(self.progressBar)

            # 写入未完成任务记录文件，以供下次打开时继续下载
            if self.fileName and not self.notCreateHistoryFile:
                self.updateTaskRecord(self.status)
                self.notCreateHistoryFile = True

            # self.pauseButton.setEnabled(True)
            self.changeButtonStatus(enabled=True)
        else:
            self.progressBar.deleteLater()
            self.progressBar = IndeterminateProgressBar(self)
            self.progressBar.setObjectName(u"progressBar")
            self.verticalLayout.addWidget(self.progressBar)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.__clickPos = event.pos()
        elif event.button() == Qt.RightButton:
            if self.status == 'finished':
                clipboard = QApplication.clipboard()
                menu = RoundMenu(parent=self)
                menu.setAttribute(Qt.WA_DeleteOnClose)

                openFileAction = Action(FIF.FOLDER, self.tr('打开文件夹'), parent=menu)
                openFileAction.triggered.connect(lambda: openFile(self.filePath))
                copyFileAction = Action(FIF.COPY, self.tr('复制文件'), parent=menu)
                copyFileAction.triggered.connect(lambda: clipboard.setMimeData(self.mimedata.toFile()))
                copyLinkAction = Action(FIF.LINK, self.tr('复制链接'), parent=menu)
                copyLinkAction.triggered.connect(lambda: clipboard.setMimeData(self.mimedata.toUrl()))
                restartAction = Action(FIF.RETURN, self.tr('重新下载'), parent=menu)
                restartAction.triggered.connect(self.restartTask)

                menu.addActions([openFileAction, copyFileAction, copyLinkAction, restartAction])

                menu.adjustSize()
                menu.exec(event.globalPos(), aniType=MenuAnimationType.DROP_DOWN)

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.__clickPos and self.status == "finished":
            if self.__calcDistance(self.__clickPos, event.pos()) >= 4:
                drag = QDrag(self)
                mimeData = QMimeData()
                mimeData.setText(self.url)
                mimeData.setData("text/uri-list", QUrl.fromLocalFile(f'{self.filePath}/{self.fileName}').toEncoded())
                drag.setMimeData(mimeData)
                pixmap = self.LogoPixmapLabel.pixmap().copy()
                # Resize
                size = (48,) * 2
                pixmap = pixmap.scaled(*size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                drag.setPixmap(pixmap)
                drag.exec(Qt.CopyAction | Qt.MoveAction)
        event.accept()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.isPressed and self.status == "finished":
                openFile(f"{self.filePath}/{self.fileName}")
        super().mouseReleaseEvent(e)

    def changeButtonStatus(self, enabled: bool | None = None, icon=None, slot=None):
        if enabled is not None:
            self.pauseButton.setEnabled(enabled)
        if icon:
            self.pauseButton.setIcon(icon)
        if slot:
            self.pauseButton.clicked.disconnect()
            self.pauseButton.clicked.connect(slot)

    def restartTask(self):
        if self.status == "finished":
            self.status = "working"
            if self.task:
                self.task.stop()
                # self.task.terminate()
                self.task.wait()
                self.task.deleteLater()
            self.changeButtonStatus(
                enabled=False, icon=FIF.PAUSE, slot=self.pauseTask)
            self.__launchTask()  # launchTask方法会重新初始化并启动任务

    def pauseTask(self):
        if self.status == "working":  # 暂停
            self.changeButtonStatus(enabled=False, icon=FIF.PLAY)

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
                self.__showInfo(self.tr("任务已经暂停"))
                self.status = "paused"
                self.changeButtonStatus(enabled=True)

        elif self.status == "paused" or self.status == "waiting":  # 继续
            self.changeButtonStatus(enabled=False, icon=FIF.PAUSE)

            try:
                self.__instantiateTask(self.url, self.filePath, self.preBlockNum, self.headers, self.fileSize,
                                       self.fileName)
            except:  # TODO 没有 fileName 的情况
                self.__instantiateTask(self.url, self.filePath, self.preBlockNum, self.headers, self.fileSize)

            self.__connectSignalToSlot()

            self.task.start()

            try:
                # 改变记录状态
                self.updateTaskRecord("working")

            finally:
                self.__showInfo(self.tr("任务正在开始"))
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
            self.changeButtonStatus(enabled=False)
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
                    parent = self.parent().parent().parent()
                    parent.expandLayout.takeAt(parent.expandLayout.indexOf(self))
                    parent.cards.remove(self)
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
                try:
                    progress_range = i["end"] - i["start"]
                    if progress_range == 0:
                        progress_value = 100 if i["progress"] >= i["start"] else 0
                    else:
                        progress_value = ((i["progress"] - i["start"]) / progress_range) * 100
                    
                    progress_value = max(0, min(100, progress_value))
                    self.progressBar.progressBarList[e].setValue(int(progress_value))
                except (KeyError, TypeError, ValueError):
                    self.progressBar.progressBarList[e].setValue(0)

            self.progressLabel.setText(f"{getReadableSize(self.task.progress)}/{getReadableSize(self.task.fileSize)}")

        else:  # 不能并行下载
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
        # self.pauseButton.setDisabled(True)
        self.changeButtonStatus(enabled=False)
        self.cancelButton.setDisabled(True)

        fileinfo = QFileInfo(f"{self.filePath}/{self.fileName}").lastModified().toString("yyyy-MM-dd hh:mm:ss")

        self.__showInfo(self.tr("完成时间: ") + fileinfo if fileinfo else self.tr("文件已被删除"))

        self.progressBar.deleteLater()

        self.progressBar = ProgressBar(self)
        self.progressBar.setObjectName(u"progressBar")
        self.verticalLayout.addWidget(self.progressBar)

        self.progressBar.setValue(100)

        try:  # 程序启动时不要发
            if self.window().tray:
                FinishedPopUpWindow.showPopUpWindow(f"{self.filePath}/{self.fileName}", self.window())
        except:
            pass

        if self.status != "finished":  # 不是自动创建的已完成任务
            # 改变记录状态
            self.updateTaskRecord("finished")

            # 再获取一次图标
            fileinfo = QFileIconProvider().icon(QFileInfo(f"{self.filePath}/{self.fileName}")).pixmap(48, 48).scaled(128, 128, aspectMode=Qt.AspectRatioMode.KeepAspectRatio,
                                   mode=Qt.TransformationMode.SmoothTransformation)  # 自动获取图标

            if fileinfo:
                pass
            else:
                fileinfo = QPixmap(":/image/logo.png")

            self.LogoPixmapLabel.setPixmap(fileinfo)
            self.LogoPixmapLabel.setFixedSize(48, 48)

        self.status = "finished"

        # 将暂停按钮改成校验按钮
        # self.pauseButton.setIcon(FIF.UPDATE)
        # self.pauseButton.clicked.disconnect()
        # self.pauseButton.clicked.connect(self.showHashAlgorithmDialog)
        # self.pauseButton.setDisabled(False)
        self.changeButtonStatus(enabled=True, icon=FIF.UPDATE, slot=self.showHashAlgorithmDialog)
        self.cancelButton.setDisabled(False)

        self.taskStatusChanged.emit()

    def __connectSignalToSlot(self):
        self.task.taskInited.connect(self.__onTaskInited)
        self.task.workerInfoChanged.connect(self.__updateProgress)
        self.task.speedChanged.connect(self.__updateSpeed)

        self.task.taskFinished.connect(self.__onTaskFinished)

        self.task.gotWrong.connect(self.__onTaskError)

    def runCalcHashTask(self, algorithm):
        self.__showInfo(self.tr("正在校验 ") + algorithm + self.tr(", 请稍后..."))
        self.changeButtonStatus(enabled=False)
        self.progressBar.setMaximum(Path(f"{self.filePath}/{self.fileName}").stat().st_size/1048576)  # 设置进度条最大值

        self.calcTask = CalcHashThread(f"{self.filePath}/{self.fileName}", algorithm)
        self.calcTask.calcProgress.connect(lambda x: self.progressBar.setValue(int(x)/1048576))
        self.calcTask.returnHash.connect(self.whenHashCalcFinished)
        self.calcTask.start()

    def whenHashCalcFinished(self, result: str):
        self.calcTask.deleteLater()
        self.progressBar.setMaximum(100)
        self.progressBar.setValue(100)
        self.__showInfo(self.tr("校验完成，文件的 ") + self.calcTask.algorithm + self.tr(" 是: ") + result)
        # 把校验按钮变成复制按钮
        self.changeButtonStatus(enabled=True, icon=FIF.COPY, slot=lambda: QApplication.clipboard().setText(result))

    def showHashAlgorithmDialog(self):

        algorithms = ["MD5", "SHA1", "SHA224", "SHA256", "SHA384", "SHA512", "BLAKE2B", "BLAKE2S", "SHA3_224",
                      "SHA3_256", "SHA3_384", "SHA3_512", "SHAKE_128", "SHAKE_256"]

        dialog = CustomInputDialog(self.tr("选择校验算法"), self.tr("请选择一个校验算法:"), algorithms, self.window())
        selected_algorithm, ok = dialog.get_item()

        if ok and selected_algorithm:
            self.runCalcHashTask(selected_algorithm)

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
