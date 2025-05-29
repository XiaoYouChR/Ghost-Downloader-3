import asyncio
import struct
import sys
import time
from abc import ABC, abstractmethod
from asyncio import Task
from pathlib import Path
from typing import List

import httpx
from PySide6.QtCore import QThread, QObject
from loguru import logger

from app.common.config import cfg
from app.common.dto import TaskProgressInfo, TaskFileInfo  # Import DTOs
from app.common.methods import getProxy, getReadableSize, getLinkInfo, createSparseFile
from app.download.download_task_base import DownloadTaskBase


class DownloadWorker:
    """Worker responsible for downloading a specific range of a file"""

    def __init__(self, startPos, currentProgress, endPos, client: httpx.AsyncClient): # Renamed parameters
        self.startPos = startPos
        self.currentProgress = currentProgress # Renamed from progress
        self.endPos = endPos
        self.client = client

    @property
    def remainingBytes(self) -> int:
        """Calculate remaining bytes to download"""
        return self.endPos - self.currentProgress

    @property
    def isCompleted(self) -> bool:
        """Check if worker has completed its task"""
        return self.currentProgress >= self.endPos


class WorkerStrategy(ABC):
    """Base strategy for handling download workers"""

    def __init__(self, file, client: httpx.AsyncClient, url: str):
        self.file = file
        self.client = client
        self.url = url

    @abstractmethod
    async def handleWorker(self, worker: DownloadWorker) -> None:
        """Handle the download process for a worker"""
        pass


class ParallelDownloadStrategy(WorkerStrategy):
    """Strategy for parallel downloading with range requests"""

    async def handleWorker(self, worker: DownloadWorker) -> None:
        """Handle parallel download for a specific worker"""
        if worker.isCompleted:
            worker.currentProgress = worker.endPos # Use currentProgress

        finished = False
        while not finished:
            try:
                workingRangeHeaders = self.client.headers.copy()
                workingRangeHeaders["range"] = f"bytes={worker.currentProgress}-{worker.endPos - 1}" # Use currentProgress

                async with self.client.stream(url=self.url, headers=workingRangeHeaders, 
                                             timeout=30, method="GET") as res:
                    res.raise_for_status()
                    if res.status_code != 206:
                        raise Exception(f"Server rejected range request, status code: {res.status_code}")

                    async for chunk in res.aiter_bytes(chunk_size=65536):
                        if worker.isCompleted:
                            break

                        if chunk:
                            self.file.seek(worker.currentProgress) # Use currentProgress
                            self.file.write(chunk)
                            worker.currentProgress += 65536 # Use currentProgress
                            cfg.globalSpeed += 65536

                            if cfg.speedLimitation.value and cfg.globalSpeed >= cfg.speedLimitation.value:
                                time.sleep(1)

                worker.currentProgress = worker.endPos # Use currentProgress
                finished = True

            except Exception as e:
                logger.info(f"Thread {worker.startPos}-{worker.endPos} is reconnecting, Error: {repr(e)}")
                await asyncio.sleep(5)

        worker.currentProgress = worker.endPos # Use currentProgress


class SingleDownloadStrategy(WorkerStrategy):
    """Strategy for non-parallel downloading"""

    def __init__(self, file, client: httpx.AsyncClient, url: str, onComplete: callable = None):
        super().__init__(file, client, url)
        self.onComplete = onComplete

    async def handleWorker(self, worker: DownloadWorker) -> None:
        """Handle non-parallel download for a worker"""
        if worker.isCompleted:
            worker.currentProgress = worker.endPos # Use currentProgress

        finished = False
        while not finished:
            try:
                workingHeaders = self.client.headers.copy()
                async with self.client.stream(url=self.url, headers=workingHeaders, 
                                             timeout=30, method="GET") as res:
                    res.raise_for_status()

                    async for chunk in res.aiter_bytes():
                        if chunk:
                            self.file.seek(worker.currentProgress) # Use currentProgress
                            self.file.write(chunk)
                            chunkSize = len(chunk)
                            worker.currentProgress += chunkSize # Use currentProgress
                            cfg.globalSpeed += chunkSize

                            if cfg.speedLimitation.value and cfg.globalSpeed >= cfg.speedLimitation.value:
                                time.sleep(1)

                if self.onComplete:
                    self.onComplete()

                finished = True

            except Exception as e:
                logger.info(f"Thread {worker.startPos}-{worker.endPos} is reconnecting, Error: {repr(e)}")
                await asyncio.sleep(5)

        worker.currentProgress = worker.endPos # Use currentProgress


class DefaultDownloadTask(QThread, DownloadTaskBase):
    """Task Manager for downloading files with support for parallel and non-parallel downloads

    This class handles the download process, supporting both parallel downloads with resume
    capability and single-threaded downloads without resume capability.

    Download modes:
    - DETECT: Auto-detect file size and determine download mode (fileSize = -1)
    - SINGLE: Non-parallel download, no resume capability (fileSize = 0)
    - PARALLEL: Parallel download with resume capability (fileSize > 0)

    The download mode is determined based on the file size:
    - If fileSize > 0, the download is performed in parallel with multiple workers
    - If fileSize = 0, the download is performed with a single worker without resume capability
    - If fileSize = -1, the file size is auto-detected and the mode is determined accordingly
    """

    # Download modes
    MODE_DETECT = -1
    MODE_SINGLE = 0
    MODE_PARALLEL = 1

    def __init__(
            self, taskId: str, url: str, headers: dict, filePath: str, fileName: str = None, 
            preBlockNum: int = 8, autoSpeedUp: bool = False, fileSize: int = -1, parent: QObject = None
    ):
        QThread.__init__(self, parent)

        self._taskId = taskId # Renamed from _task_id
        self._currentProgress = 0 
        self.url = url
        self._originalUrl = url 
        self.headers = headers
        self.fileName = fileName 
        self.filePath = filePath 
        self.preBlockNum = preBlockNum 
        self.autoSpeedUp = autoSpeedUp 
        self.fileSize = fileSize 
        self.downloadMode = self.MODE_DETECT
        self._isPaused = False 
        self._isCancelled = False 
        self._statusText = "pending" 
        self._currentSpeedBps = 0 
        self._contentType = "" 

        self.file = None 
        self.ghdFile = None 

        self.workers: List[DownloadWorker] = []
        self.asyncTasks: List[Task] = [] 
        self.supervisorTask = None
        self.downloadStrategy = None
        self.eventLoop = None 

        self.historySpeed = [0] * 10 

        proxy = getProxy()
        self.client = httpx.AsyncClient(
            headers=headers, 
            verify=cfg.SSLVerify.value, # Corrected: Use actual ConfigItem name
            proxy=proxy, 
            limits=httpx.Limits(max_connections=256), 
            trust_env=False, 
            follow_redirects=True
        )
        self._isSingleModeCompleted = False 


    def _initializeTaskSync(self): 
        """Synchronous part of initialization, run before QThread starts."""
        try:
            self._getFileInfoInternal() 
            self._determineDownloadModeInternal() 
            self._setupFilePathInternal() 
            self._sanitizeFileNameInternal() 
            self._createFileIfNeededInternal() 

            self.infoUpdated.emit(self.getFileInfo()) 
            self.statusChanged.emit("initialized")
            self._statusText = "initialized"
            
            if self.downloadMode == self.MODE_SINGLE:
                self.preBlockNum = 1

        except Exception as e:
            logger.error(f"Error during task initialization for {self.taskId}: {repr(e)}") 
            self.errorOccurred.emit(repr(e))
            self._statusText = f"error: {repr(e)}"
            self.statusChanged.emit("error")


    def _reassignWorkerInternal(self): 
        """Find the worker with the most remaining work and split its workload"""
        workerWithMaxRemaining = None
        maxRemainingBytes = 0

        for worker in self.workers:
            remainingBytes = worker.remainingBytes
            if remainingBytes > maxRemainingBytes:
                maxRemainingBytes = remainingBytes
                workerWithMaxRemaining = worker

        minReassignSize = cfg.maxReassignSize.value * 1048576 
        if workerWithMaxRemaining and maxRemainingBytes > minReassignSize:
            currentProgress = workerWithMaxRemaining.currentProgress 
            originalEndPos = workerWithMaxRemaining.endPos

            baseShare = maxRemainingBytes // 2
            remainder = maxRemainingBytes % 2
            newEndPos = currentProgress + baseShare + remainder

            workerWithMaxRemaining.endPos = newEndPos

            newStartPos = newEndPos
            newWorker = DownloadWorker(newStartPos, newStartPos, originalEndPos, self.client)

            newTask = self.eventLoop.create_task(self.downloadStrategy.handleWorker(newWorker)) 

            insertIndex = self.workers.index(workerWithMaxRemaining) + 1
            self.workers.insert(insertIndex, newWorker)
            self.asyncTasks.append(newTask) 

            logger.info(
                f"Task {self.fileName}: Split workload successfully. " +
                f"Remaining: {getReadableSize(maxRemainingBytes)}, " +
                f"Original worker now ends at: {newEndPos}, " +
                f"New worker starts at: {newStartPos}"
            )
        else:
            logger.info(
                f"Task {self.fileName}: Cannot split workload. " +
                f"Remaining bytes ({getReadableSize(maxRemainingBytes)}) " +
                f"less than minimum split size ({getReadableSize(minReassignSize)})"
            )

    def _calculateWorkRangesInternal(self): # Renamed
        """Calculate work ranges for parallel download workers"""
        blockSize = self.fileSize // self.preBlockNum
        rangePoints = list(range(0, self.fileSize, blockSize))

        if self.fileSize % self.preBlockNum == 0: 
            if not rangePoints or rangePoints[-1] != self.fileSize :
                 rangePoints.append(self.fileSize)
        elif not rangePoints or rangePoints[-1] < self.fileSize : 
            rangePoints.append(self.fileSize)


        workRanges = []
        for i in range(len(rangePoints) - 1):
            startPos, endPos = rangePoints[i], rangePoints[i + 1]
            workRanges.append([startPos, endPos])

        if workRanges: 
            workRanges[-1][-1] = self.fileSize

        return workRanges

    # __initTask removed as its logic is now in _initializeTaskSync or called directly

    def _getFileInfoInternal(self): # Renamed
        """Get file information if needed"""
        if self.fileSize == self.MODE_DETECT or not self.fileName:
            # self._originalUrl is already set in __init__

            # Assume getLinkInfo might return content_type if requested
            # For now, getLinkInfo is not modified to return content_type, so this part is illustrative.
            # A more robust solution would be to get headers from initial response in getLinkInfo.
            resolvedUrl, resolvedFileName, resolvedFileSize = getLinkInfo(self.url, self.headers, self.fileName)
            # resolvedContentType = "" # Placeholder, would come from getLinkInfo or another call
            
            fileInfoChanged = False
            if resolvedUrl and self.url != resolvedUrl:
                self.url = resolvedUrl
                fileInfoChanged = True
            if resolvedFileName and self.fileName != resolvedFileName:
                self.fileName = resolvedFileName
                fileInfoChanged = True
            if resolvedFileSize != -1 and self.fileSize != resolvedFileSize: 
                self.fileSize = resolvedFileSize
                fileInfoChanged = True
            # if resolvedContentType and self._contentType != resolvedContentType:
            #     self._contentType = resolvedContentType
            #     fileInfoChanged = True

            if fileInfoChanged : 
                 self.infoUpdated.emit(self.getFileInfo())


    def _determineDownloadModeInternal(self): # Renamed
        """Determine download mode based on file size"""
        if self.fileSize > 0:
            self.downloadMode = self.MODE_PARALLEL
        else:
            self.downloadMode = self.MODE_SINGLE

    def _setupFilePathInternal(self): # Renamed
        """Setup and ensure file path exists"""
        if not self.filePath or not Path(self.filePath).is_dir():
            self.filePath = Path.cwd() 
        else:
            self.filePath = Path(self.filePath)

        if not self.filePath.exists():
            self.filePath.mkdir(parents=True, exist_ok=True)

    def _sanitizeFileNameInternal(self): # Renamed
        """Sanitize and truncate filename if needed"""
        if not self.fileName: 
            self.fileName = "downloaded_file" 
            logger.warning(f"Task {self.taskId} has no filename, defaulting to 'downloaded_file'")

        if sys.platform == "win32":
            self.fileName = ''.join([c for c in self.fileName if c not in r'\/:*?"<>|'])

        if len(self.fileName.encode('utf-8')) > 255: 
            self.fileName = self.fileName[:255//3] 

    def _createFileIfNeededInternal(self): # Renamed
        """Create the file if it doesn't exist"""
        if not self.fileName: # Should have been set by _sanitizeFileNameInternal if was None
            logger.error(f"Task {self.taskId}: Cannot create file, filename is not set.")
            raise ValueError("Filename is not set")

        targetFilePath = Path(self.filePath) / self.fileName 
        if targetFilePath.exists():
            return

        targetFilePath.touch()
        try:
            createSparseFile(targetFilePath)
        except Exception as e:
            logger.warning(f"Failed to create sparse file: {repr(e)}")

    def _loadWorkersInternal(self): # Renamed
        """Load or create workers for the download task"""
        if self.downloadMode == self.MODE_SINGLE:
            self.workers.append(DownloadWorker(0, 0, 1, self.client)) 
            return

        historyFilePath = Path(self.filePath) / f"{self.fileName}.ghd" 
        if historyFilePath.exists():
            self._loadWorkersFromHistoryInternal(historyFilePath) # Renamed
        else:
            self._createNewWorkersInternal() # Renamed

    def _loadWorkersFromHistoryInternal(self, historyFilePath: Path): # Renamed
        """Load workers from a history file"""
        try:
            with open(historyFilePath, "rb") as historyFile:
                while True:
                    data = historyFile.read(24)
                    if not data:
                        break
                    startPos, currentProgress, endPos = struct.unpack("<QQQ", data) # Use currentProgress
                    self.workers.append(DownloadWorker(startPos, currentProgress, endPos, self.client)) # Use currentProgress
        except Exception as e:
            logger.error(f"Failed to load workers from history: {e}")
            self._createNewWorkersInternal() # Renamed

    def _createNewWorkersInternal(self): # Renamed
        """Create new workers for a fresh download"""
        workRanges = self._calculateWorkRangesInternal() # Renamed

        for i in range(self.preBlockNum):
            if i < len(workRanges): 
                startPos, endPos = workRanges[i][0], workRanges[i][1]
                self.workers.append(DownloadWorker(startPos, startPos, endPos, self.client))
            else: # pragma: no cover
                logger.warning(f"Task {self.taskId}: Not enough work ranges for preBlockNum {self.preBlockNum}")
                break


    async def _createDownloadAsyncTasksInternal(self): # Renamed
        """Create download tasks for all workers using the appropriate strategy"""
        logger.debug(f"Task {self.fileName}: Creating download tasks for {len(self.workers)} workers")

        if self.downloadMode == self.MODE_PARALLEL:
            self.downloadStrategy = ParallelDownloadStrategy(self.file, self.client, self.url)
            for worker in self.workers:
                task = asyncio.create_task(self.downloadStrategy.handleWorker(worker))
                self.asyncTasks.append(task) 
            self.ghdFile = open(Path(self.filePath) / f"{self.fileName}.ghd", "wb") 
        else: # MODE_SINGLE
            def markSingleModeCompleted(): # Renamed from markCompleted
                self._isSingleModeCompleted = True 

            self.downloadStrategy = SingleDownloadStrategy(self.file, self.client, self.url, markSingleModeCompleted)
            if self.workers: 
                 logger.debug(f"Task {self.fileName}: Starting single thread download")
                 task = asyncio.create_task(self.downloadStrategy.handleWorker(self.workers[0]))
                 self.asyncTasks.append(task) 
            else: # pragma: no cover
                logger.error(f"Task {self.taskId}: No workers available for single download mode.")
                self._statusText = "error"
                self.statusChanged.emit("error")
                self.errorOccurred.emit("No workers for single download")


    async def _supervisorInternal(self): # Renamed
        """Monitor download progress, update history file, and manage speed optimization"""
        lastProgress = 0
        self._currentProgress = 0 
        for worker in self.workers:
            self._currentProgress += worker.currentProgress - worker.startPos
        lastProgress = self._currentProgress


        if self.downloadMode == self.MODE_PARALLEL:
            await self._runParallelSupervisorInternal(lastProgress) # Renamed
        else: # MODE_SINGLE
            await self._runSingleSupervisorInternal(lastProgress) # Renamed

    async def _runParallelSupervisorInternal(self, lastProgress): # Renamed
        """Supervisor for parallel downloads with history tracking and speed optimization"""
        speedUpVars = None
        if self.autoSpeedUp:
            speedUpVars = {
                'maxSpeedPerConnect': 1,
                'additionalTaskNum': len(self.asyncTasks), 
                'formerAvgSpeed': 0,
                'duringTime': 0,
                'targetSpeed': 0
            }

        while self._currentProgress != self.fileSize:
            if self._isPaused or self._isCancelled:
                break
            self._updateProgressAndHistoryInternal() # Renamed

            currentSpeed = self._currentProgress - lastProgress
            lastProgress = self._currentProgress
            avgSpeed = self._updateSpeedHistoryInternal(currentSpeed) # Renamed

            if self.autoSpeedUp and speedUpVars: 
                self._handleAutoSpeedUpInternal(avgSpeed, speedUpVars) # Renamed

            await asyncio.sleep(1)

    async def _runSingleSupervisorInternal(self, lastProgress): # Renamed
        """Supervisor for non-parallel downloads"""
        while not self._isSingleModeCompleted: 
            if self._isPaused or self._isCancelled:
                break
            
            currentTotalProgress = 0
            if self.workers : 
                currentTotalProgress = self.workers[0].currentProgress - self.workers[0].startPos
            
            if currentTotalProgress != self._currentProgress : 
                 self._currentProgress = currentTotalProgress
                 self.progressUpdated.emit(self.getProgress())


            currentSpeed = self._currentProgress - lastProgress
            lastProgress = self._currentProgress
            self._updateSpeedHistoryInternal(currentSpeed) # Renamed

            await asyncio.sleep(1)

    def _updateProgressAndHistoryInternal(self): # Renamed
        """Update progress from all workers and write to history file. Also emits progressUpdated."""
        if self.ghdFile: 
            self.ghdFile.seek(0)
        
        currentTotalProgress = 0 
        for worker in self.workers:
            currentTotalProgress += worker.currentProgress - worker.startPos 

            if self.ghdFile: 
                data = struct.pack("<QQQ", worker.startPos, worker.currentProgress, worker.endPos) 
                self.ghdFile.write(data)
        
        self._currentProgress = currentTotalProgress 

        if self.ghdFile: 
            self.ghdFile.flush()
            self.ghdFile.truncate()

        self.progressUpdated.emit(self.getProgress())


    def _updateSpeedHistoryInternal(self, currentSpeed): # Renamed
        """Update speed history and calculate average speed. Also emits progressUpdated for speed."""
        self.historySpeed.pop(0)
        self.historySpeed.append(currentSpeed)
        avgSpeed = sum(self.historySpeed) / 10
        self._currentSpeedBps = avgSpeed * 8 
        self.progressUpdated.emit(self.getProgress()) 
        return avgSpeed

    def _handleAutoSpeedUpInternal(self, avgSpeed, speedUpVars): # Renamed
        """Handle auto speed-up logic to optimize download speed"""
        if speedUpVars['duringTime'] < 10:
            speedUpVars['duringTime'] += 1
            return

        speedUpVars['duringTime'] = 0
        speedPerConnect = avgSpeed / len(self.asyncTasks) if self.asyncTasks else 1 

        self._updateMaxSpeedPerConnectInternal(speedPerConnect, speedUpVars) # Renamed

        if avgSpeed < speedUpVars['targetSpeed']:
            return 

        self._prepareForMoreWorkersInternal(avgSpeed, speedUpVars) # Renamed

        if len(self.asyncTasks) < 253: 
            self._addMoreWorkersInternal(4) # Renamed

    def _updateMaxSpeedPerConnectInternal(self, speedPerConnect, speedUpVars): # Renamed
        """Update maximum speed per connection if current is higher"""
        if speedPerConnect <= speedUpVars['maxSpeedPerConnect']:
            return

        speedUpVars['maxSpeedPerConnect'] = speedPerConnect
        speedUpVars['targetSpeed'] = (0.85 * speedUpVars['maxSpeedPerConnect'] * speedUpVars['additionalTaskNum']) + speedUpVars['formerAvgSpeed']

    def _prepareForMoreWorkersInternal(self, avgSpeed, speedUpVars): # Renamed
        """Prepare variables for adding more workers"""
        speedUpVars['formerAvgSpeed'] = avgSpeed
        speedUpVars['additionalTaskNum'] = 4 
        speedUpVars['targetSpeed'] = (0.85 * speedUpVars['maxSpeedPerConnect'] * speedUpVars['additionalTaskNum']) + speedUpVars['formerAvgSpeed']

    def _addMoreWorkersInternal(self, count): # Renamed
        """Add more workers to improve download speed"""
        for _ in range(count):
            self._reassignWorkerInternal() # Renamed

    async def _mainDownloadLoopInternal(self): # Renamed
        """Main download execution flow"""
        try:
            targetFilePath = Path(self.filePath) / self.fileName 
            self.file = open(targetFilePath, "rb+")

            await self._createDownloadAsyncTasksInternal() # Renamed

            if not self.asyncTasks and self.downloadMode == self.MODE_SINGLE and not self.workers: # pragma: no cover
                logger.error(f"Task {self.taskId}: No async tasks or workers created for single download. Aborting.")
                self.errorOccurred.emit("Initialization failed: No workers.")
                self._statusText = "error"
                self.statusChanged.emit("error")
                return


            self.supervisorTask = asyncio.create_task(self._supervisorInternal()) # Renamed

            try:
                await self.supervisorTask
            except asyncio.CancelledError: # pragma: no cover
                 if self.client and not self.client.is_closed: 
                    await self.client.aclose()


            await self._cleanupResourcesInternal() # Renamed

            if not self._isCancelled and not self._isPaused : 
                 await self._handleTaskCompletionInternal() # Renamed

        except Exception as e:
            logger.error(f"Exception in download main loop for {self.taskId}: {repr(e)}") 
            self.errorOccurred.emit(repr(e))
            self._statusText = f"error: {repr(e)}"
            self.statusChanged.emit("error")

    async def _cleanupResourcesInternal(self): # Renamed
        """Clean up resources after download completes or is cancelled"""
        if self.client and not self.client.is_closed:
            await self.client.aclose()

        if self.file and not self.file.closed: 
            self.file.close()

        if self.ghdFile and not self.ghdFile.closed: 
            self.ghdFile.close()

    async def _handleTaskCompletionInternal(self): # Renamed
        """Handle task completion and cleanup"""
        taskCompletedSuccessfully = False
        if self.downloadMode == self.MODE_SINGLE and self._isSingleModeCompleted: 
            taskCompletedSuccessfully = True
        elif self.downloadMode == self.MODE_PARALLEL and self._currentProgress == self.fileSize:
            taskCompletedSuccessfully = True
            try:
                historyFile = Path(self.filePath) / f"{self.fileName}.ghd" 
                if historyFile.exists():
                    historyFile.unlink()
            except Exception as e: # pragma: no cover
                logger.error(f"Failed to delete history file for {self.taskId}: {e}") 

        if taskCompletedSuccessfully:
            logger.info(f"Task {self.taskId} ({self.fileName}) finished!") 
            self._statusText = "completed"
            self.statusChanged.emit("completed")
            self.finished.emit()


    def _internalStop(self, finalStatusText: str, emitStatus: str): # Renamed
        """Internal stop mechanism, also used by pause and cancel."""
        self._isPaused = True 
        if emitStatus == "cancelled":
            self._isCancelled = True

        self._cancelAllAsyncTasksInternal() # Renamed

        try:
            if self.supervisorTask and not self.supervisorTask.done():
                self.supervisorTask.cancel()
        except Exception as e: # pragma: no cover
            logger.warning(f"Error cancelling supervisor task for {self.taskId}: {e}") 
        finally:
            self._closeFilesInternal() # Renamed
            
            self._statusText = finalStatusText
            self.statusChanged.emit(emitStatus)
            if emitStatus in ["cancelled", "error"]:
                 if not self.isFinished(): 
                    self.finished.emit() 
            logger.info(f"Task {self.taskId} ({self.fileName}) stopped with status: {emitStatus}") 


    def _cancelAllAsyncTasksInternal(self): # Renamed
        """Cancel all worker tasks"""
        for task in self.asyncTasks: # Use asyncTasks
            if task and not task.done():
                task.cancel()

    def _closeFilesInternal(self): # Renamed
        """Close all open files"""
        if hasattr(self, 'file') and self.file and not self.file.closed:
            self.file.close()

        if hasattr(self, 'ghdFile') and self.ghdFile and not self.ghdFile.closed:
            self.ghdFile.close()

    # __waitForTasksToComplete and __cancelRemainingTasks removed as they were not used with asyncio approach

    def run(self):
        """Main thread entry point for the download task."""
        if self._isCancelled:
            logger.info(f"Task {self.taskId} was cancelled before run.") 
            self._statusText = "cancelled"
            self.statusChanged.emit("cancelled")
            self.finished.emit() 
            return
        
        # _initializeTaskSync is called in start() before QThread.start()

        self._loadWorkersInternal() # Renamed

        self.eventLoop = asyncio.new_event_loop() # Use self.eventLoop
        asyncio.set_event_loop(self.eventLoop)
        
        self._statusText = "downloading"
        self.statusChanged.emit("downloading")

        try:
            self.eventLoop.run_until_complete(self._mainDownloadLoopInternal()) # Renamed
        except asyncio.CancelledError: # pragma: no cover
            logger.info(f"Download task {self.taskId} ({self.fileName}) main loop cancelled.") 
            if not self._isCancelled : 
                self._statusText = "cancelled"
                self.statusChanged.emit("cancelled")
        except Exception as e: # pragma: no cover
            logger.error(f"Error in download task {self.taskId} ({self.fileName}) run: {repr(e)}") 
            self.errorOccurred.emit(repr(e))
            self._statusText = f"error: {repr(e)}"
            self.statusChanged.emit("error")
        finally:
            self._cleanupEventLoopInternal() # Renamed
            
            currentStatusKnownTerminal = self._statusText in ["completed", "error", "cancelled"]
            if not currentStatusKnownTerminal: # pragma: no cover
                if self._isCancelled: 
                    self._statusText = "cancelled"
                    self.statusChanged.emit("cancelled")
                elif self._isPaused: 
                     self._statusText = "paused" 
                     self.statusChanged.emit("paused")
                else: 
                     self._statusText = "finished_abnormally"
                     self.statusChanged.emit("finished_abnormally")


            if not self.isFinished(): 
                 self.finished.emit() 

    def _cleanupEventLoopInternal(self): # Renamed
        """Clean up the event loop resources"""
        try:
            if self.eventLoop: # Check if eventLoop exists
                if self.eventLoop.is_running(): # pragma: no cover
                    self.eventLoop.call_soon_threadsafe(self.eventLoop.stop)
                
                if not self.eventLoop.is_closed(): # pragma: no cover
                    # Ensure any async generators are shutdown
                    shutdown_future = asyncio.run_coroutine_threadsafe(self.eventLoop.shutdown_asyncgens(), self.eventLoop)
                    shutdown_future.result(timeout=5) 
                
                if not self.eventLoop.is_closed(): # Check again before closing
                    self.eventLoop.close()
        except Exception as e: # pragma: no cover
            logger.error(f"Error cleaning up event loop for {self.taskId}: {e}") 
        finally:
            self.eventLoop = None 

    # --- Implementation of DownloadTaskBase abstract methods ---
    def start(self):
        if self.isRunning():
            logger.warning(f"Task {self.taskId} is already running.") 
            return
        self._isPaused = False
        self._isCancelled = False
        self._statusText = "starting"
        self.statusChanged.emit("starting")
        
        self._initializeTaskSync() 
        if "error" in self._statusText: # If init failed
            logger.error(f"Task {self.taskId} failed initialization, cannot start.") 
            # self.finished.emit() # Ensure QThread termination if start fails critically
            return

        super().start() 

    def pause(self):
        if not self.isRunning() or self._isPaused: # pragma: no cover
            logger.info(f"Task {self.taskId} is not running or already paused.") 
            if self._isPaused and not self.isRunning(): 
                self.statusChanged.emit("paused") 
            return
        logger.info(f"Pausing task {self.taskId} ({self.fileName})") 
        self._internalStop("paused", "paused") # Renamed

    def resume(self):
        if self.isRunning() and not self._isPaused: # pragma: no cover
            logger.warning(f"Task {self.taskId} is already running and not paused.") 
            return
        if self._isCancelled: # pragma: no cover
            logger.warning(f"Task {self.taskId} was cancelled, cannot resume.") 
            return

        logger.info(f"Resuming task {self.taskId} ({self.fileName})") 
        self._isPaused = False
        self._isSingleModeCompleted = False 
        
        self._currentProgress = 0 
        self.workers = []
        self.asyncTasks = [] 
        self.supervisorTask = None 
        
        self.start() 


    def cancel(self):
        logger.info(f"Cancelling task {self.taskId} ({self.fileName})") 
        self._internalStop("cancelled", "cancelled") # Renamed
        
        try:
            ghdFile = Path(self.filePath) / f"{self.fileName}.ghd" 
            if ghdFile.exists():
                ghdFile.unlink()
            
            # downloadFile = Path(self.filePath) / self.fileName 
            # if downloadFile.exists() and self.fileSize > 0 and self._currentProgress < self.fileSize : 
            #      logger.info(f"Partial download file {downloadFile} kept on cancellation for {self.taskId}.")
            #      pass
        except Exception as e: # pragma: no cover
            logger.error(f"Error during file cleanup for cancelled task {self.taskId}: {e}") 

    def getProgress(self) -> TaskProgressInfo:
        return TaskProgressInfo(
            downloadedBytes=self._currentProgress,
            totalBytes=self.fileSize if self.fileSize > 0 else 0, 
            speedBps=int(self._currentSpeedBps), 
            statusText=self._statusText,
            workerInfo=[{ "startPos": w.startPos, "currentProgress": w.currentProgress, "endPos": w.endPos} for w in self.workers] if self.downloadMode == self.MODE_PARALLEL else []
        )

    def getFileInfo(self) -> TaskFileInfo:
        return TaskFileInfo(
            fileName=self.fileName or "",
            filePath=str(self.filePath) if self.filePath else "",
            url=self.url,
            originalUrl=getattr(self, '_originalUrl', self.url), 
            totalBytes=self.fileSize if self.fileSize > 0 else 0,
            ableToParallelDownload=self.downloadMode == self.MODE_PARALLEL,
            contentType=getattr(self, '_contentType', "") 
        )
        
    def saveState(self) -> dict:
        return {
            "taskId": self.taskId, # Added taskId for better identification
            "currentProgress": self._currentProgress, # Renamed from current_progress
            "fileSize": self.fileSize,
            "fileName": self.fileName,
            "url": self.url,
            "originalUrl": self._originalUrl, # Added
            "filePath": str(self.filePath),
            "headers": self.headers,
            "preBlockNum": self.preBlockNum,
            "autoSpeedUp": self.autoSpeedUp,
            "downloadMode": self.downloadMode,
            "statusText": self._statusText, # Added current status text
            "contentType": self._contentType, # Added
            "workersSnapshot": [{"startPos": w.startPos, "currentProgress": w.currentProgress, "endPos": w.endPos} for w in self.workers] if self.workers else [] # Renamed keys
        }

    def loadState(self, state: dict):
        # self.taskId is set in __init__ and should not change
        self._currentProgress = state.get("currentProgress", self._currentProgress) # Renamed
        self.fileSize = state.get("fileSize", self.fileSize) 
        self.fileName = state.get("fileName", self.fileName) 
        self.url = state.get("url", self.url)
        self._originalUrl = state.get("originalUrl", self._originalUrl) # Added
        self.filePath = Path(state.get("filePath", str(self.filePath)))
        self.headers = state.get("headers", self.headers)
        self.preBlockNum = state.get("preBlockNum", self.preBlockNum)
        self.autoSpeedUp = state.get("autoSpeedUp", self.autoSpeedUp)
        self.downloadMode = state.get("downloadMode", self.downloadMode)
        # _statusText is handled by TaskManager's _applyLoadedStatus, not directly set here
        # self._statusText = state.get("statusText", self._statusText) 
        self._contentType = state.get("contentType", self._contentType) # Added
        
        # Worker state is primarily managed by .ghd file for active resumption.
        # workersSnapshot is more for informational purposes or if .ghd is missing.
        # For simplicity, current resumption logic heavily relies on .ghd via __loadWorkers.
        # If restoring workers from snapshot is desired, __loadWorkers would need modification.
        
        logger.info(f"State loaded for task {self.taskId}, progress: {self._currentProgress}") # Use self.taskId
        self.progressUpdated.emit(self.getProgress()) 
        self.infoUpdated.emit(self.getFileInfo())
