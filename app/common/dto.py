from time import time

class SpeedInfo:
    __slot__ = ('speed', 'time')
    def __init__(self, speed = 0, elapsedTime = 1):
        if elapsedTime != 0:
            self.speed = speed
            self.time = elapsedTime
        else:
            raise ValueError("Time cannot be zero")

class SpeedRecorder:
    __slot__ = ('progress', 'startTime')
    def __init__(self, progress = 0):
        self.progress = progress
        self.startTime = time()

    def reset(self, progress):
        self.progress = progress
        self.startTime = time()

    def update(self, progress) -> SpeedInfo:
        elapsedTime = time() - self.startTime
        speed = (progress - self.progress) / elapsedTime
        return SpeedInfo(speed, elapsedTime)
    