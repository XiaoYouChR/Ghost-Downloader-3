from time import time

class SpeedInfo:
    def __init__(self, speed = 0, time = 1):
        if time != 0:
            self.speed = speed
            self.time = time
        else:
            raise ValueError("Time cannot be zero")

class SpeedRecoder:
    def __init__(self,process = 0):
        self.process = process
        self.start_time = time()

    def reset(self, process):
        self.process = process
        self.start_time = time()

    def flash(self, process) -> SpeedInfo:
        
        d_time = time() - self.start_time
        #if d_time != 0:
        speed = (process - self.process) / (d_time)
        #else:
        #    logger.warning("Time cannot be zero")
        #    speed = 0
        #    d_time = 0.01#天天出花里胡哨的bug烦死我了
        return SpeedInfo(speed, d_time)
    