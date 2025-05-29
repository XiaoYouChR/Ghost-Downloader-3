from dataclasses import dataclass, field
from typing import List, Any, Dict

@dataclass
class TaskProgressInfo:
    downloadedBytes: int = 0
    totalBytes: int = 0
    speedBps: int = 0
    statusText: str = "pending"
    workerInfo: List[Dict[str, Any]] = field(default_factory=list) # For parallel downloads

@dataclass
class TaskFileInfo:
    fileName: str = ""
    filePath: str = ""
    url: str = ""
    originalUrl: str = "" # In case of redirects
    totalBytes: int = 0 # Can also be part of file info, esp. if resolved late from headers
    ableToParallelDownload: bool = False
    contentType: str = "" # e.g., 'application/octet-stream'
    # Add any other relevant static file info

@dataclass
class TaskUIData:
    taskId: str
    fileInfo: TaskFileInfo
    progressInfo: TaskProgressInfo
    errorMessage: str = None
    # Add any other fields DefaultTaskCard might need for display that don't fit above

@dataclass
class OverallProgressInfo:
    totalTasks: int = 0
    activeTasks: int = 0
    overallDownloadedBytes: int = 0
    overallTotalBytes: int = 0
    overallSpeedBps: int = 0
