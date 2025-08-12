from time import time

class SpeedInfo:
    __slot__ = ('speed', 'time')
    def __init__(self, speed = 0, elapsedTime = 1):
        if elapsedTime != 0:
            self.speed = speed
            self.time = elapsedTime
        else:
            raise ValueError("Time cannot be zero")

class ProgressInfo:
    __slot__ = ("progress", "startTime", "formerProgress")
    def __init__(self, progress = 0):
        self.formerProgress = progress
        self.progress = progress
        self.startTime = time()

    def reset(self):
        self.formerProgress = self.progress
        self.startTime = time()

    def getSpeedInfo(self) -> SpeedInfo:
        elapsedTime = time() - self.startTime
        speed = (self.progress - self.formerProgress) / elapsedTime
        return SpeedInfo(speed, elapsedTime)
    