from app.supports.config import cfg

class TaskRecoder:
    def __init__(self):
        self.fileHandle = open(f"{cfg.get(cfg.appLocalDataLocation)}/GhostDownloader/Memory.log", "r+", encoding="utf-8")
        self.memorizedTasks: list[str] = []
        for line in self.fileHandle.readlines():
            self.memorizedTasks.append(line.strip())

    def flush(self):
        ...

    def __del__(self):
        self.fileHandle.close()
