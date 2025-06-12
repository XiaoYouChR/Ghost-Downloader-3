from enum import IntEnum, auto


class TaskStatus(IntEnum):
    Unknown = auto()
    Single = auto()
    Parallel = auto()

class TaskManagerStatus(IntEnum):
    Initializing = auto()
    ParallelRunning = auto()
    SingleRunning = auto()
    Waiting = auto()
    Paused = auto()
    Canceled = auto()
    Finished = auto()

class HttpVersion(IntEnum):
    HTTP_1_2 = 12
    HTTP_2 = 20
    HTTP_3 = 30
