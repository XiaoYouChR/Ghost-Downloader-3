import asyncio
import struct
import sys
import time
from dataclasses import dataclass,field
from abc import ABC, abstractmethod
from asyncio import Task
from pathlib import Path
from threading import Thread
from typing import List

import httpx
from PySide6.QtCore import QThread, Signal
from loguru import logger

from app.common.config import cfg
from app.common.methods import getProxy, getReadableSize, getLinkInfo, createSparseFile
from app.common.dto import SpeedInfo, SpeedRecoder

class DownloadWorker:
    """Worker responsible for downloading a specific range of a file"""

    def __init__(self, start, progress, end, client: httpx.AsyncClient):
        self.startPos = start
        self.progress = progress
        self.endPos = end
        self.client = client

    @property
    def remainingBytes(self) -> int:
        """Calculate remaining bytes to download"""
        return self.endPos - self.progress

    @property
    def isCompleted(self) -> bool:
        """Check if worker has completed its task"""
        return self.progress >= self.endPos
    
    @property
    def task(self):
        if hasattr(self, '_task'):
            return self._task
        else:
            logger.error("Task not set yet")

    @task.setter
    def task(self, task: asyncio.Task):
        if not self.running:
            self._task = task
        else:
            self._task.cancel()
            self._task = task
            logger.warning("Task is running, cancell old task before setting new one")

    @property
    def running(self) -> bool:
        if hasattr(self, '_task'):
            return not self._task.done()
        else:
            return False
    
    def cancel(self):
        if hasattr(self, '_task'):
            self._task.cancel()

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
            worker.progress = worker.endPos
            logger.warning(f"Worker {worker.startPos}-{worker.endPos} is already completed, skipping download.")
            return

        finished = False
        while not finished:
            try:
                workingRangeHeaders = self.client.headers.copy()
                workingRangeHeaders["range"] = f"bytes={worker.progress}-{worker.endPos - 1}"

                async with self.client.stream(url=self.url, headers=workingRangeHeaders, 
                                             timeout=30, method="GET") as res:
                    res.raise_for_status()
                    if res.status_code != 206:
                        raise Exception(f"Server rejected range request, status code: {res.status_code}")

                    async for chunk in res.aiter_bytes(chunk_size=65536):
                        if worker.isCompleted:
                            break

                        if chunk:
                            self.file.seek(worker.progress)
                            self.file.write(chunk)
                            worker.progress += 65536
                            cfg.globalSpeed += 65536

                            if cfg.speedLimitation.value and cfg.globalSpeed >= cfg.speedLimitation.value:
                                time.sleep(1)

                worker.progress = worker.endPos
                finished = True

            except Exception as e:
                logger.info(f"Thread {worker.startPos}-{worker.endPos} is reconnecting, Error: {repr(e)}")
                await asyncio.sleep(5)

        worker.progress = worker.endPos


class SingleDownloadStrategy(WorkerStrategy):
    """Strategy for non-parallel downloading"""

    def __init__(self, file, client: httpx.AsyncClient, url: str, onComplete: callable = None):
        super().__init__(file, client, url)
        self.onComplete = onComplete

    async def handleWorker(self, worker: DownloadWorker) -> None:
        """Handle non-parallel download for a worker"""
        if worker.isCompleted:
            worker.progress = worker.endPos
            logger.warning(f"Worker {worker.startPos}-{worker.endPos} is already completed, skipping download.")
            return

        finished = False
        while not finished:
            try:
                workingHeaders = self.client.headers.copy()
                async with self.client.stream(url=self.url, headers=workingHeaders, 
                                             timeout=30, method="GET") as res:
                    res.raise_for_status()

                    async for chunk in res.aiter_bytes():
                        if chunk:
                            self.file.seek(worker.progress)
                            self.file.write(chunk)
                            chunkSize = len(chunk)
                            worker.progress += chunkSize
                            cfg.globalSpeed += chunkSize

                            if cfg.speedLimitation.value and cfg.globalSpeed >= cfg.speedLimitation.value:
                                time.sleep(1)

                if self.onComplete:
                    self.onComplete()

                finished = True

            except Exception as e:
                logger.info(f"Thread {worker.startPos}-{worker.endPos} is reconnecting, Error: {repr(e)}")
                await asyncio.sleep(5)

        worker.progress = worker.endPos


class DownloadTask(QThread):
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

    taskInited = Signal(bool)  # Emitted when task is initialized, with parallel download capability flag
    workerInfoChanged = Signal(list)  # Emitted when worker progress changes, for segmented progress bars
    speedChanged = Signal(int)  # Emitted when download speed changes
    taskFinished = Signal()  # Emitted when task is finished
    gotWrong = Signal(str)  # Emitted when an error occurs

    # Download modes
    MODE_DETECT = -1
    MODE_SINGLE = 0
    MODE_PARALLEL = 1

    def __init__(
            self, url, headers, preTaskNum: int = 8,
            filePath: str = None, fileName: str = None, autoSpeedUp: bool = False, fileSize: int = -1, parent=None
    ):
        super().__init__(parent)

        # Basic task properties
        self.progress = 0
        self.url = url
        self.headers = headers
        self.fileName = fileName
        self.filePath = filePath
        self.preBlockNum = preTaskNum
        self.autoSpeedUp = autoSpeedUp
        self.fileSize = fileSize
        self.downloadMode = self.MODE_DETECT  # Initial mode is detect
        self.isCompleted = False  # Flag to track completion status

        # File handling
        self.file = None
        self.ghdFile = None

        # Worker and task management
        self.workers: List[DownloadWorker] = []
        self.tasks: List[Task] = []
        self.doneTask: int = 0  # Count of completed tasks
        self.supervisorTask = None
        self.downloadStrategy = None

        # Speed tracking
        self.historySpeed = [0] * 10  # Rolling window of 10 seconds for speed calculation

        # HTTP client setup
        proxy = getProxy()
        self.client = httpx.AsyncClient(
            headers=headers, 
            verify=cfg.SSLVerify.value,
            proxy=proxy, 
            limits=httpx.Limits(max_connections=256), 
            trust_env=False, 
            follow_redirects=True
        )

        # Initialize task in a separate thread
        self.initThread = Thread(target=self.__initTask, daemon=True)
        self.initThread.start()


    def __reassignWorker(self):
        """Find the worker with the most remaining work and split its workload"""
        # Find worker with maximum remaining bytes
        workerWithMaxRemaining = None
        maxRemainingBytes = 0

        for worker in self.workers:
            if worker.running:
                remainingBytes = worker.remainingBytes
                if remainingBytes > maxRemainingBytes:
                    maxRemainingBytes = remainingBytes
                    workerWithMaxRemaining = worker
            elif not worker.isCompleted:
                #总是优先运行未运行的worker
                worker.task = self.loop.create_task(self.handleWorker(worker))
                return
            

        # Check if we should split the workload
        minReassignSize = cfg.maxReassignSize.value * 1048576  # Convert to bytes
        if workerWithMaxRemaining and maxRemainingBytes > minReassignSize:
            # Split the workload evenly
            currentProgress = workerWithMaxRemaining.progress
            originalEndPos = workerWithMaxRemaining.endPos

            # Calculate split point
            baseShare = maxRemainingBytes // 2
            remainder = maxRemainingBytes % 2
            newEndPos = currentProgress + baseShare + remainder

            # Update existing worker's endpoint
            workerWithMaxRemaining.endPos = newEndPos

            # Create new worker for the second half
            newStartPos = newEndPos
            newWorker = DownloadWorker(newStartPos, newStartPos, originalEndPos, self.client)

            # Create task for the new worker
            newTask = self.loop.create_task(self.handleWorker(newWorker))
            newWorker.task = newTask

            # Add new worker and task to their respective lists
            insertIndex = self.workers.index(workerWithMaxRemaining) + 1
            self.workers.insert(insertIndex, newWorker)
            self.tasks.append(newTask)

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

    def __calculateWorkRanges(self):
        """Calculate work ranges for parallel download workers"""
        # Calculate size of each block
        blockSize = self.fileSize // self.preBlockNum
        rangePoints = list(range(0, self.fileSize, blockSize))

        # Ensure we have the correct number of blocks
        if self.fileSize % self.preBlockNum == 0:
            rangePoints.append(self.fileSize)

        # Create list of start/end positions for each worker
        workRanges = []
        for i in range(len(rangePoints) - 1):
            startPos, endPos = rangePoints[i], rangePoints[i + 1]
            workRanges.append([startPos, endPos])

        # Ensure the last range ends at the file size
        if workRanges:
            workRanges[-1][-1] = self.fileSize

        return workRanges

    def __initTask(self):
        """Initialize the download task by getting file information and preparing the file"""
        try:
            self.__getFileInfo()
            self.__determineDownloadMode()
            self.__setupFilePath()
            self.__sanitizeFileName()
            self.__createFileIfNeeded()

            # Signal task initialization completion
            # True if parallel download is possible
            self.taskInited.emit(self.downloadMode == self.MODE_PARALLEL)

            # For non-parallel downloads, use only one worker
            if self.downloadMode == self.MODE_SINGLE:
                self.preBlockNum = 1

        except Exception as e:
            self.gotWrong.emit(repr(e))

    def __getFileInfo(self):
        """Get file information if needed"""
        if self.fileSize == self.MODE_DETECT or not self.fileName:
            self.url, self.fileName, self.fileSize = getLinkInfo(self.url, self.headers, self.fileName)

    def __determineDownloadMode(self):
        """Determine download mode based on file size"""
        if self.fileSize > 0:
            self.downloadMode = self.MODE_PARALLEL
        else:
            self.downloadMode = self.MODE_SINGLE

    def __setupFilePath(self):
        """Setup and ensure file path exists"""
        if not self.filePath or not Path(self.filePath).is_dir():
            self.filePath = Path.cwd()
            return

        self.filePath = Path(self.filePath)
        if not self.filePath.exists():
            self.filePath.mkdir()

    def __sanitizeFileName(self):
        """Sanitize and truncate filename if needed"""
        # Sanitize filename for Windows
        if sys.platform == "win32":
            self.fileName = ''.join([c for c in self.fileName if c not in r'\/:*?"<>|'])

        # Truncate filename if too long
        if len(self.fileName) > 255:
            self.fileName = self.fileName[:255]

    def __createFileIfNeeded(self):
        """Create the file if it doesn't exist"""
        filePath = Path(f"{self.filePath}/{self.fileName}")
        if filePath.exists():
            return

        filePath.touch()
        try:
            createSparseFile(filePath)
        except Exception as e:
            logger.warning(f"Failed to create sparse file: {repr(e)}")

    def __loadWorkers(self):
        """Load or create workers for the download task"""
        if self.downloadMode == self.MODE_SINGLE:
            # For non-parallel downloads, create a single worker
            self.workers.append(DownloadWorker(0, 0, 1, self.client))
            return

        # For parallel downloads, check if we have a history file (.ghd) to resume download
        historyFilePath = Path(f"{self.filePath}/{self.fileName}.ghd")
        if historyFilePath.exists():
            self.__loadWorkersFromHistory(historyFilePath)
        else:
            self.__createNewWorkers()

    def __loadWorkersFromHistory(self, historyFilePath: Path):
        """Load workers from a history file"""
        try:
            with open(historyFilePath, "rb") as historyFile:
                while True:
                    # Each worker has 3 uint64 values (start, progress, end) = 24 bytes
                    data = historyFile.read(24)
                    if not data:
                        break

                    start, progress, end = struct.unpack("<QQQ", data)
                    self.workers.append(DownloadWorker(start, progress, end, self.client))

        except Exception as e:
            logger.error(f"Failed to load workers from history: {e}")
            # Fall back to creating new workers
            self.__createNewWorkers()

    def __createNewWorkers(self):
        """Create new workers for a fresh download"""
        workRanges = self.__calculateWorkRanges()

        for i in range(self.preBlockNum):
            startPos, endPos = workRanges[i][0], workRanges[i][1]
            self.workers.append(DownloadWorker(startPos, startPos, endPos, self.client))

    async def __createDownloadTasks(self):
        """Create download tasks for all workers using the appropriate strategy"""
        logger.debug(f"Task {self.fileName}: Creating download tasks for {len(self.workers)} workers")

        # Create the appropriate download strategy based on download mode
        if self.downloadMode == self.MODE_PARALLEL:
            self.downloadStrategy = ParallelDownloadStrategy(self.file, self.client, self.url)

            # Create tasks for all workers
            created = 0
            for worker in self.workers:
                if not worker.isCompleted:
                    task = asyncio.create_task(self.handleWorker(worker))
                    worker.task = task
                    self.tasks.append(task)
                    created += 1
                    if created >= self.preBlockNum:
                        break

            # Open history file for parallel downloads
            self.ghdFile = open(f"{self.filePath}/{self.fileName}.ghd", "wb")
        else:
            # For non-parallel downloads, mark completion when done
            def markCompleted():
                self.isCompleted = True  # Mark task as completed

            self.downloadStrategy = SingleDownloadStrategy(self.file, self.client, self.url, markCompleted)

            # Create a single task for the worker
            logger.debug(f"Task {self.fileName}: Starting single thread download")
            task = asyncio.create_task(self.handleWorker(self.workers[0]))
            self.workers[0].task = task
            self.tasks.append(task)

    async def __supervisor(self):
        """Monitor download progress, update history file, and manage speed optimization"""
        lastProgress = 0

        # Initialize total progress
        for worker in self.workers:
            self.progress += worker.progress - worker.startPos
            lastProgress = self.progress

        if self.downloadMode == self.MODE_PARALLEL:
            await self.__runParallelSupervisor(lastProgress)
        else:
            await self.__runSingleSupervisor(lastProgress)

    async def __runParallelSupervisor(self, lastProgress):
        """Supervisor for parallel downloads with history tracking and speed optimization"""
        # Initialize auto speed-up variables if enabled
        if self.autoSpeedUp:
            recoder = SpeedRecoder(self.progress)
            threshold = 0.1 # 判断阈值
            accuracy = 1  # 判断精度
            logger.info(f'自动提速阈值：{threshold}, 精度：{accuracy}')
            info = SpeedInfo()
            formerInfo = SpeedInfo()
            formerTaskNum = taskNum = 0
            maxSpeedPerConnect = 1

        # Monitor until download is complete
        while self.progress != self.fileSize:
            # Update progress and history file
            workerInfo = self.__updateProgressAndHistory() #用不到的workerInfo

            # Calculate and emit current speed
            currentSpeed = self.progress - lastProgress
            lastProgress = self.progress
            avgSpeed = self.__updateSpeedHistory(currentSpeed) #用不到avgSpeed

            # Handle auto speed-up if enabled
            if self.autoSpeedUp:
                if taskNum != self.taskNum:  #如果线程数发生变化：
                    formerTaskNum = taskNum
                    taskNum = self.taskNum
                    formerInfo = info
                    recoder.reset(self.progress)
                    logger.info(f'taskNum changed:{self.taskNum}')
                
                elif recoder.flash(self.progress).time > 60:  #每60秒强制重置
                    recoder.reset(self.progress)

                else:                                         #主逻辑
                    info = recoder.flash(self.progress) 
                    if self.taskNum > 0:
                        speedPerConnect = info.speed / self.taskNum
                        if speedPerConnect > maxSpeedPerConnect:
                            maxSpeedPerConnect = speedPerConnect
                    
                    speedDeltaPerNewThread = (info.speed - formerInfo.speed) / (taskNum - formerTaskNum)                    
                    efficiency = speedDeltaPerNewThread / maxSpeedPerConnect
                    offset = accuracy / info.time
                    logger.debug(f'speed:{getReadableSize(info.speed)}/s {getReadableSize(info.speed - formerInfo.speed)}/s / {taskNum - formerTaskNum} / maxSpeedPerThread {getReadableSize(maxSpeedPerConnect)}/s = efficiency:{efficiency:.2f}, offset:{offset:.2f}, time:{info.time:.2f}s')
                    if efficiency >= threshold + offset:
                        logger.debug(f'自动提速增加新线程  {efficiency}')

                        if self.taskNum < 256:
                            self.__reassignWorker()
                    if self.taskNum == 0 and self.progress < self.fileSize:
                        logger.info('没有线程了，立即重新分配工作线程')
                        self.__reassignWorker()
            # Wait before next update
            await asyncio.sleep(1)

    async def handleWorker(self, worker: DownloadWorker):
        await self.downloadStrategy.handleWorker(worker)
        if not self.autoSpeedUp:# 如果开启了自动提速，则重新分配工作线程由自动提速控制
            print("autoSpeedUp is off, reassigning worker")
            self.__reassignWorker()
        self.doneTask += 1
    
    async def __runSingleSupervisor(self, lastProgress):
        """Supervisor for non-parallel downloads"""
        # Monitor until download is complete (marked by isCompleted flag)
        while not self.isCompleted:
            # Update total progress
            self.progress = 0
            for worker in self.workers:
                self.progress += worker.progress - worker.startPos

            # Emit empty worker info (no segments for non-parallel downloads)
            self.workerInfoChanged.emit([])

            # Calculate and emit current speed
            currentSpeed = self.progress - lastProgress
            lastProgress = self.progress
            avgSpeed = self.__updateSpeedHistory(currentSpeed)

            # Wait before next update
            await asyncio.sleep(1)

    def __updateProgressAndHistory(self):
        """Update progress from all workers and write to history file"""
        workerInfo = []
        self.ghdFile.seek(0)
        self.progress = 0

        # Process each worker
        for worker in self.workers:
            # Create info dict for UI
            info = {
                "start": worker.startPos,
                "progress": worker.progress,
                "end": worker.endPos
            }
            workerInfo.append(info)

            # Update total progress
            self.progress += worker.progress - worker.startPos

            # Save worker state to history file
            data = struct.pack("<QQQ", worker.startPos, worker.progress, worker.endPos)
            self.ghdFile.write(data)

        # Ensure history file is updated
        self.ghdFile.flush()
        self.ghdFile.truncate()

        # Emit updated worker info for UI
        self.workerInfoChanged.emit(workerInfo)

        return workerInfo

    def __updateSpeedHistory(self, currentSpeed):
        """Update speed history and calculate average speed"""
        self.historySpeed.pop(0)
        self.historySpeed.append(currentSpeed)
        avgSpeed = sum(self.historySpeed) / 10
        self.speedChanged.emit(avgSpeed)
        return avgSpeed

    async def __main(self):
        """Main download execution flow"""
        try:
            # Open the download file
            self.file = open(f"{self.filePath}/{self.fileName}", "rb+")

            # Create download tasks using the appropriate strategy
            await self.__createDownloadTasks()

            # Start the supervisor to monitor progress
            self.supervisorTask = asyncio.create_task(self.__supervisor())

            # Wait for the supervisor to complete
            try:
                await self.supervisorTask
            except asyncio.CancelledError:
                await self.client.aclose()

            # Clean up resources
            await self.__cleanupResources()

            # Handle task completion
            await self.__handleTaskCompletion()

        except Exception as e:
            self.gotWrong.emit(repr(e))

    async def __cleanupResources(self):
        """Clean up resources after download completes or is cancelled"""
        # Close HTTP client
        await self.client.aclose()

        # Close the download file
        if self.file:
            self.file.close()

        # Close history file if it exists
        if self.ghdFile:
            self.ghdFile.close()

    async def __handleTaskCompletion(self):
        """Handle task completion and cleanup"""
        # For non-parallel downloads that completed successfully
        if self.downloadMode == self.MODE_SINGLE and self.isCompleted:
            logger.info(f"Task {self.fileName} finished!")
            self.taskFinished.emit()
            return

        # For parallel downloads that completed successfully
        if self.downloadMode == self.MODE_PARALLEL and self.progress == self.fileSize:
            # Delete history file when download is complete
            try:
                historyFile = Path(f"{self.filePath}/{self.fileName}.ghd")
                if historyFile.exists():
                    historyFile.unlink()
            except Exception as e:
                logger.error(f"Failed to delete history file: {e}")

            logger.info(f"Task {self.fileName} finished!")
            self.taskFinished.emit()

    def stop(self):
        """Stop all download tasks and clean up resources"""
        # Cancel all worker tasks
        self.__cancelAllTasks()

        # Cancel supervisor task
        try:
            if self.supervisorTask:
                self.supervisorTask.cancel()
        finally:
            # Close files
            self.__closeFiles()

            # Ensure all tasks are properly cancelled
            self.__waitForTasksToComplete()

    def __cancelAllTasks(self):
        """Cancel all worker tasks"""
        for task in self.tasks:
            if task and not task.done():
                task.cancel()

    def __closeFiles(self):
        """Close all open files"""
        if hasattr(self, 'file') and self.file:
            self.file.close()

        if self.ghdFile:
            self.ghdFile.close()

    def __waitForTasksToComplete(self):
        """Wait for all tasks to complete after cancellation"""
        timeout = 0
        maxTimeout = 100  # 5 seconds max wait

        while not all(task.done() for task in self.tasks) and timeout < maxTimeout:
            # Try to cancel any remaining tasks
            self.__cancelRemainingTasks()

            # Wait a bit before checking again
            time.sleep(0.05)
            timeout += 1

    def __cancelRemainingTasks(self):
        """Attempt to cancel any tasks that are not yet done"""
        for task in self.tasks:
            if task.done():
                continue

            try:
                task.cancel()
            except RuntimeError:
                # RuntimeError can occur if the task is in an invalid state
                pass
            except Exception as e:
                logger.error(f"Error cancelling task: {e}")

    def run(self):
        """Main thread entry point for the download task"""
        # Wait for initialization to complete
        self.initThread.join()

        # Load or create workers
        self.__loadWorkers()

        # Create and configure event loop
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        # Run the main download process
        try:
            self.loop.run_until_complete(self.__main())
        except asyncio.CancelledError as e:
            logger.debug(f"Download task cancelled: {e}")
        except Exception as e:
            logger.error(f"Error in download task: {e}")
        finally:
            # Clean up the event loop
            self.__cleanupEventLoop()

    def __cleanupEventLoop(self):
        """Clean up the event loop resources"""
        try:
            # Close any remaining async generators
            self.loop.run_until_complete(self.loop.shutdown_asyncgens())
            # Close the event loop
            self.loop.close()
        except Exception as e:
            logger.error(f"Error cleaning up event loop: {e}")
    
    @property
    def taskNum(self) -> int:
        """Get the number of active tasks"""
        return len(self.tasks) - self.doneTask

