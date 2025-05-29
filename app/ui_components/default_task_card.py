import hashlib
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QThread, Signal, QFileInfo, QMimeData, Qt, QUrl, Slot
from PySide6.QtGui import QPixmap, QDrag
from PySide6.QtWidgets import QFileIconProvider, QApplication, QWidget
from loguru import logger
from qfluentwidgets import FluentIcon as FIF
from qfluentwidgets import IndeterminateProgressBar, ProgressBar, MenuAnimationType, RoundMenu, Action

from app.common.dto import TaskUIData  # Import DTOs
# Updated import paths
from .Ui_TaskCard import Ui_TaskCard
from .task_card_base import TaskCardBase
from ..common.config import cfg
# from app.download.default_download_task import DefaultDownloadTask # No longer directly used by TaskCard
from ..common.methods import getReadableSize, openFile
from ..components.custom_components import TaskProgressBar
from ..components.custom_dialogs import DelDialog, \
    CustomInputDialog  # Assuming custom_dialogs is now a sibling or in PYTHONPATH
from ..view.pop_up_window import FinishedPopUpWindow

if TYPE_CHECKING:
    from app.task_manager.task_manager_base import TaskManagerBase


class MimeData(QMimeData): # This class can remain as is or be moved to a common utils if used elsewhere
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

class DefaultTaskCard(TaskCardBase, Ui_TaskCard): # Inherit from TaskCardBase
    # taskStatusChanged = Signal() # This signal's role is now taken by TaskManager signals or TaskCardBase.requestRemove

    # Old constructor parameters are mostly for data that will now come from uiData via TaskManager
    def __init__(self, taskManager: 'TaskManagerBase', parent: QWidget = None):
        super().__init__(taskManager, parent) # Call TaskCardBase constructor
        self.setupUi(self) # Load UI from Ui_TaskCard.py

        # Store some initial data for convenience, though it will be updated by updateDisplay
        self.fileName = "N/A"
        self.filePath = ""
        self.url = "" # Will be set by setTaskId or updateDisplay
        self.fileSize = 0
        self.ableToParallelDownload = False
        self.status = "pending" # Internal status for UI logic, driven by uiData['status_text']
        # self.notCreatedHistoryFile is specific to old system, remove if state persistence is handled by TaskManager
        self.preBlockNum = cfg.preBlockNum.value # Keep for TaskProgressBar, might get from uiData later

        self.mimedata: MimeData = None # Will be initialized when data is available
        self._clickPos = None # Renamed from __clickPos
        self._completed_popup_shown = False # Flag to show "completed" popup only once

        # Initialize UI elements to a default state
        self.titleLabel.setText(self.tr("正在初始化任务..."))
        self.LogoPixmapLabel.setPixmap(QPixmap(":/image/logo.png"))
        self.LogoPixmapLabel.setFixedSize(70, 70)

        # Initial progress bar (can be indeterminate until type is known)
        self.progressBar = IndeterminateProgressBar(self)
        self.progressBar.setObjectName(u"progressBar")
        self.verticalLayout.addWidget(self.progressBar)
        
        # Connect UI element signals to TaskCardBase handlers or specific handlers here
        # The actual pause/resume logic is now in `controlTask` which calls base handlers
        self.pauseButton.clicked.connect(self.controlTask) 
        self.cancelButton.clicked.connect(self.onCancelClicked) # Uses TaskCardBase.onCancelClicked
        self.folderButton.clicked.connect(self.onOpenFolderClicked) # Uses TaskCardBase.onOpenFolderClicked
        
        # Old direct task management is removed.
        # self.task: DefaultDownloadTask = None 
        # self._task_id is now self._currentTaskId in TaskCardBase and set by setTaskId()
        # Retain updateTaskRecord for now, as its removal is a separate step.

    # --- Implementation of TaskCardBase abstract methods ---
    @Slot(TaskUIData) 
    def updateDisplay(self, uiData: TaskUIData) -> None:
        previous_status = self.status 
        
        # Access fields from DTOs
        self.fileName = uiData.fileInfo.fileName if uiData.fileInfo else self.tr('未知文件名')
        self.filePath = uiData.fileInfo.filePath if uiData.fileInfo else ''
        self.url = uiData.fileInfo.url if uiData.fileInfo else ''
        self.fileSize = uiData.fileInfo.totalBytes if uiData.fileInfo else 0
        self.ableToParallelDownload = uiData.fileInfo.ableToParallelDownload if uiData.fileInfo else False
        
        new_status_text = uiData.progressInfo.statusText.lower() if uiData.progressInfo else 'pending'
        
        recognized_statuses = ["downloading", "paused", "completed", "error", "cancelled", "waiting", "initialized", "starting", "resuming", "pending"]
        if new_status_text in recognized_statuses:
            self.status = new_status_text 
        else: 
            pass

        if self.filePath and self.fileName and self.url and not self.mimedata:
             self.mimedata = MimeData(self.filePath, self.fileName, self.url)

        icon_path_str = f"{self.filePath}/{self.fileName}" if self.filePath and self.fileName else ""
        icon_pixmap = QPixmap() 
        if icon_path_str:
            file_info_for_icon = QFileInfo(icon_path_str)
            if file_info_for_icon.exists() or new_status_text not in ["error", "cancelled"]:
                 icon_pixmap_temp = QFileIconProvider().icon(file_info_for_icon).pixmap(128, 128)
                 if not icon_pixmap_temp.isNull():
                      icon_pixmap = icon_pixmap_temp
        
        self.LogoPixmapLabel.setPixmap(icon_pixmap if not icon_pixmap.isNull() else QPixmap(":/image/logo.png"))
        self.titleLabel.setText(self.fileName if self.fileName else self.tr("未知文件名"))

        downloaded_bytes = uiData.progressInfo.downloadedBytes if uiData.progressInfo else 0
        total_bytes = self.fileSize # Already updated from uiData.fileInfo.totalBytes
        
        current_progress_bar_type = type(self.progressBar)
        expected_progress_bar_type = None

        if new_status_text in ["downloading", "paused", "error", "starting", "resuming", "initialized", "waiting"] :
            if self.ableToParallelDownload and total_bytes > 0:
                expected_progress_bar_type = TaskProgressBar
            elif total_bytes > 0: 
                expected_progress_bar_type = ProgressBar
            else: 
                expected_progress_bar_type = IndeterminateProgressBar
        elif new_status_text == "completed":
            expected_progress_bar_type = ProgressBar 
        else: 
            expected_progress_bar_type = ProgressBar 

        if current_progress_bar_type != expected_progress_bar_type:
            if self.progressBar:
                old_pb_index = self.verticalLayout.indexOf(self.progressBar)
                if old_pb_index != -1: 
                    item = self.verticalLayout.takeAt(old_pb_index)
                    if item and item.widget(): item.widget().deleteLater()
                else: self.progressBar.deleteLater()

            if expected_progress_bar_type == TaskProgressBar:
                # Use workerInfo from progressInfo DTO
                num_workers = len(uiData.progressInfo.workerInfo) if uiData.progressInfo else self.preBlockNum 
                self.progressBar = TaskProgressBar(num_workers, self)
            elif expected_progress_bar_type == ProgressBar:
                self.progressBar = ProgressBar(self)
            else: 
                self.progressBar = IndeterminateProgressBar(self)
            
            insert_index = self.verticalLayout.indexOf(self.statusHorizontalLayout)
            if insert_index == -1 : insert_index = self.verticalLayout.count()
            self.verticalLayout.insertWidget(insert_index, self.progressBar)
            self.progressBar.setObjectName(u"progressBar")


        if isinstance(self.progressBar, TaskProgressBar):
            worker_info = uiData.progressInfo.workerInfo if uiData.progressInfo else []
            if len(worker_info) != self.progressBar.blockNum and len(worker_info) > 0 : 
                old_pb_index = self.verticalLayout.indexOf(self.progressBar)
                if old_pb_index != -1:
                     item = self.verticalLayout.takeAt(old_pb_index)
                     if item and item.widget(): item.widget().deleteLater()
                else: self.progressBar.deleteLater()
                self.progressBar = TaskProgressBar(len(worker_info), self)
                self.verticalLayout.insertWidget(old_pb_index if old_pb_index !=-1 else self.verticalLayout.count(), self.progressBar)
                self.progressBar.setObjectName(u"progressBar")

            for e, i in enumerate(worker_info): 
                if e < len(self.progressBar.progressBarList):
                    denominator = (i.get("endPos",0) - i.get("startPos",0)) 
                    self.progressBar.progressBarList[e].setValue(
                        ((i.get("currentProgress",0) - i.get("startPos",0)) / denominator * 100) if denominator > 0 else (100 if i.get("currentProgress",0) >= i.get("endPos",0) else 0)
                    )
        elif isinstance(self.progressBar, ProgressBar):
            if total_bytes > 0:
                self.progressBar.setValue(int(downloaded_bytes / total_bytes * 100))
            elif new_status_text == "completed":
                self.progressBar.setValue(100)
            else:
                self.progressBar.setValue(0)

        self.progressLabel.setText(f"{getReadableSize(downloaded_bytes)}{f'/{getReadableSize(total_bytes)}' if total_bytes > 0 else ''}")
        speed_bps = uiData.progressInfo.speedBps if uiData.progressInfo else 0
        self.speedLabel.setText(f"{getReadableSize(speed_bps / 8)}/s")

        if total_bytes > 0 and speed_bps > 0 and new_status_text == "downloading":
            try:
                leftTime = (total_bytes - downloaded_bytes) / (speed_bps / 8)
                self.leftTimeLabel.setText(f"{int(leftTime // 60):02d}:{int(leftTime % 60):02d}")
            except ZeroDivisionError: # pragma: no cover
                self.leftTimeLabel.setText("Infinity")
        elif total_bytes == 0 and new_status_text == "downloading":
             self.leftTimeLabel.setText(self.tr("未知"))
        else: 
            self.leftTimeLabel.setText("")

        current_display_status = new_status_text # Use the validated status
        
        if current_display_status == "downloading":
            self._hideInfo() # Renamed
            self.changeButtonStatus(enabled=True, icon=FIF.PAUSE)
        elif current_display_status == "paused":
            self._showInfo(self.tr("任务已经暂停")) # Renamed
            self.changeButtonStatus(enabled=True, icon=FIF.PLAY)
        elif current_display_status == "completed":
            completed_time_str = QFileInfo(icon_path_str).lastModified().toString("yyyy-MM-dd hh:mm:ss") if icon_path_str and QFileInfo(icon_path_str).exists() else ""
            self._showInfo(self.tr("完成时间: ") + completed_time_str) # Renamed
            self.changeButtonStatus(enabled=True, icon=FIF.UPDATE, slot=self.showHashAlgorithmDialog) 
            self.cancelButton.setDisabled(False) 
            if previous_status != "completed" and not self._completed_popup_shown : # Check previous_status
                 if hasattr(self, 'window') and self.window() and hasattr(self.window(), 'tray') and self.window().tray: 
                     try:
                         FinishedPopUpWindow.showPopUpWindow(f"{self.filePath}/{self.fileName}", self.window())
                         self._completed_popup_shown = True 
                     except Exception as e:
                         logger.warning(f"Error showing finished popup in updateDisplay for {self.fileName}: {e}")
        elif current_display_status != "completed": 
            self._completed_popup_shown = False


        if current_display_status == "error":
            error_msg_display = uiData.errorMessage if uiData.errorMessage else self.tr("未知错误")
            self._showInfo(self.tr("错误: ") + error_msg_display) # Renamed
            self.changeButtonStatus(enabled=True, icon=FIF.PLAY) 
        elif current_display_status == "cancelled":
            self._showInfo(self.tr("任务已取消")) # Renamed
            self.changeButtonStatus(enabled=False)
            self.cancelButton.setDisabled(True)
        elif current_display_status == "waiting":
            self._showInfo(self.tr("排队中...")) # Renamed
            self.changeButtonStatus(enabled=True, icon=FIF.PLAY) 
        elif current_display_status in ["initialized", "starting", "resuming", "pending"]:
            self._showInfo(self.tr("正在准备任务..."))  # Renamed
            self.changeButtonStatus(enabled=False) 
        elif current_display_status != "completed": # Catch-all for other non-completed statuses
            self._showInfo(uiData.progressInfo.statusText.capitalize() if uiData.progressInfo else "") # Renamed
            self.changeButtonStatus(enabled=False) 
            
        self.folderButton.setEnabled(bool(self.filePath and (current_display_status == "completed" or (self.fileName and Path(self.filePath, self.fileName).exists())) ))
        # self.status is already updated from new_status_text


    # --- Methods that interact with TaskCardBase handlers ---
    def controlTask(self): # This is connected to the pauseButton
        current_ui_status = self.status # Use the internal status updated by updateDisplay
        if current_ui_status in ["downloading", "starting", "resuming"]:
            self.onPauseClicked()
        elif current_ui_status in ["paused", "waiting", "error", "initialized", "pending", "completed"]: # "completed" for retry via "verify" button turning to play
            self.onResumeClicked() # This effectively becomes "start" or "retry"

    # Override TaskCardBase specific error handler if needed for custom UI display
    @Slot(str, str)
    def _handleTaskSpecificError(self, taskId: str, errorMessage: str) -> None:
        if self.getTaskId() and taskId == self.getTaskId():
            logger.error(f"DefaultTaskCard specific error for {taskId}: {errorMessage}")
            self._showInfo(self.tr("错误: ") + errorMessage) # Renamed # Explicitly show error
            self.changeButtonStatus(enabled=True, icon=FIF.PLAY) # Allow retry
    
    def _onCancelClicked(self): 
        dialog = DelDialog(self.window())
        if dialog.exec():
            # completely = dialog.checkBox.isChecked() # This info needs to be passed to TaskManager
            self.onCancelClicked() 
        dialog.deleteLater()
    
    # This method is kept as it's a UI utility for this card
    def changeButtonStatus(self, enabled: bool | None = None, icon=None, slot=None):
        if enabled is not None:
            self.pauseButton.setEnabled(enabled)
        if icon:
            self.pauseButton.setIcon(icon)
        
        current_slot = slot if slot else self.controlTask
        try:
            self.pauseButton.clicked.disconnect() 
        except RuntimeError: 
            pass
        self.pauseButton.clicked.connect(current_slot)


    # Retain mouse events for drag&drop and context menu
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._clickPos = event.pos() # Renamed
        elif event.button() == Qt.RightButton:
            current_ui_status = self.status 
            if current_ui_status == 'completed': 
                clipboard = QApplication.clipboard()
                menu = RoundMenu(parent=self)
                menu.setAttribute(Qt.WA_DeleteOnClose)

                openFileAction = Action(FIF.FOLDER, self.tr('打开文件夹'), parent=menu)
                openFileAction.triggered.connect(self.onOpenFolderClicked) 
                
                if self.filePath and self.fileName and self.url: # Ensure these are set
                    self.mimedata = MimeData(self.filePath, self.fileName, self.url)

                if self.mimedata:
                    copyFileAction = Action(FIF.COPY, self.tr('复制文件'), parent=menu)
                    copyFileAction.triggered.connect(lambda: clipboard.setMimeData(self.mimedata.toFile()))
                    copyLinkAction = Action(FIF.LINK, self.tr('复制链接'), parent=menu)
                    copyLinkAction.triggered.connect(lambda: clipboard.setMimeData(self.mimedata.toUrl()))
                    menu.addActions([copyFileAction, copyLinkAction])

                restartAction = Action(FIF.RETURN, self.tr('重新下载'), parent=menu)
                restartAction.triggered.connect(self.onRetryClicked) 

                menu.addActions([openFileAction, restartAction])
                menu.adjustSize()
                menu.exec(event.globalPos(), aniType=MenuAnimationType.DROP_DOWN)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        current_ui_status = self.status
        if self._clickPos and current_ui_status == "completed": # Renamed 
            if self._calcDistance(self._clickPos, event.pos()) >= 4: # Renamed
                if not (self.filePath and self.fileName and self.url): return 
                self.mimedata = MimeData(self.filePath, self.fileName, self.url) 

                drag = QDrag(self)
                mimeData = QMimeData()
                local_file_path = Path(self.filePath) / self.fileName
                if local_file_path.exists():
                    mimeData.setUrls([QUrl.fromLocalFile(str(local_file_path))])
                else: 
                    mimeData.setText(self.url)
                
                drag.setMimeData(mimeData)
                pixmap = self.LogoPixmapLabel.pixmap().copy()
                size = (48,) * 2
                pixmap = pixmap.scaled(*size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                drag.setPixmap(pixmap)
                drag.exec(Qt.CopyAction | Qt.MoveAction)
        event.accept()

    def mouseReleaseEvent(self, e):
        current_ui_status = self.status
        if e.button() == Qt.LeftButton and self.isPressed and current_ui_status == "completed": 
                if self.filePath and self.fileName and Path(self.filePath, self.fileName).exists():
                     openFile(str(Path(self.filePath) / self.fileName))
        super().mouseReleaseEvent(e)

    # File Hashing logic can remain as it's UI specific for a completed task
    def showHashAlgorithmDialog(self):
        algorithms = ["MD5", "SHA1", "SHA224", "SHA256", "SHA384", "SHA512", "BLAKE2B", "BLAKE2S", "SHA3_224",
                      "SHA3_256", "SHA3_384", "SHA3_512", "SHAKE_128", "SHAKE_256"]
        dialog = CustomInputDialog(self.tr("选择校验算法"), self.tr("请选择一个校验算法:"), algorithms, self.window())
        selected_algorithm, ok = dialog.get_item()
        if ok and selected_algorithm:
            self.runCalcHashTask(selected_algorithm)

    def runCalcHashTask(self, algorithm):
        self._showInfo(self.tr("正在校验 ") + algorithm + self.tr(", 请稍后...")) # Renamed
        self.changeButtonStatus(enabled=False) 
        
        full_file_path_str = str(Path(self.filePath) / self.fileName if self.filePath and self.fileName else "")
        if not full_file_path_str or not Path(full_file_path_str).exists():
            self._showInfo(self.tr("错误: 文件不存在无法校验.")) # Renamed
            self.changeButtonStatus(enabled=True, icon=FIF.UPDATE, slot=self.showHashAlgorithmDialog)
            return

        try:
            file_size_bytes = Path(full_file_path_str).stat().st_size
            if isinstance(self.progressBar, ProgressBar): 
                self.progressBar.setMaximum(int(file_size_bytes / 1048576) if file_size_bytes > 0 else 100) 
                self.progressBar.setValue(0)
        except Exception as e:
            logger.error(f"Error getting file size for hash progress: {e}")
            if isinstance(self.progressBar, ProgressBar):
                self.progressBar.setMaximum(100) 
                self.progressBar.setValue(0)


        self.calcTask = CalcHashThread(full_file_path_str, algorithm, self) # Pass self as parent
        self.calcTask.calcProgress.connect(lambda x: self.progressBar.setValue(int(int(x)/1048576)) if isinstance(self.progressBar, ProgressBar) and self.progressBar.maximum() > 1 else None)
        self.calcTask.returnHash.connect(self.whenHashCalcFinished)
        self.calcTask.start()

    def whenHashCalcFinished(self, result: str):
        self.calcTask.deleteLater()
        if isinstance(self.progressBar, ProgressBar):
            self.progressBar.setMaximum(100)
            self.progressBar.setValue(100)
        self._showInfo(self.tr("校验完成，文件的 ") + self.calcTask.algorithm + self.tr(" 是: ") + result) # Renamed
        self.changeButtonStatus(enabled=True, icon=FIF.COPY, slot=lambda: QApplication.clipboard().setText(result))

    def _showInfo(self, content: str): # Renamed
        self.speedLabel.hide()
        self.leftTimeLabel.hide()
        self.progressLabel.hide()
        self.infoLabel.show()
        self.infoLabel.setText(content)

    def _hideInfo(self): # Renamed
        self.infoLabel.hide()
        self.speedLabel.show()
        self.leftTimeLabel.show()
        self.progressLabel.show()

    def _calcDistance(self, startPos, endPos): # Renamed
        return (startPos.x() - endPos.x()) ** 2 + (startPos.y() - endPos.y()) ** 2

# Utility class, can stay here or be moved to a common utils if used elsewhere
class CalcHashThread(QThread):
    calcProgress = Signal(str)
    returnHash = Signal(str)

    def __init__(self, fileResolvedPath: str, algorithm: str, parent=None):
        super().__init__(parent=parent)
        self.fileResolvedPath = fileResolvedPath
        self.algorithm = algorithm

    def run(self):
        hashAlgorithm = getattr(hashlib, self.algorithm.lower())()
        progress = 0
        try:
            with open(self.fileResolvedPath, "rb") as file:
                chunk_size = 1048576  
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
        except Exception as e:
            logger.error(f"Error during hash calculation for {self.fileResolvedPath}: {e}")
            self.returnHash.emit(self.tr("错误")) 
        # self.changeButtonStatus(enabled=False) # This line was causing an error as changeButtonStatus is a DefaultTaskCard method
        # self.progressBar.setMaximum(Path(f"{self.filePath}/{self.fileName}").stat().st_size/1048576)  # This line was causing an error
