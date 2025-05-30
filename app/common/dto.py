from dataclasses import dataclass, field
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


# @dataclass
# class AutoSpeedUpVars:
#     maxSpeedPerConnect: int = 1
#     additionalTaskNum: int = 0
#     formerAvgSpeed: float = 0
#     duringTime: int = 0
#     targetSpeed: float = 0

#     recoder: SpeedRecoder = SpeedRecoder()
#     threshold: float = 0.1
#     accuracy: float = 1
#     info = SpeedInfo()
#     formerInfo = SpeedInfo()
#     formerTaskNum: int = 0
#     taskNum: int = 0

#     def flash(self, process, taskNum = 0):
#         if self.taskNum != taskNum:
#             self.formerTaskNum = self.taskNum
#             self.taskNum = taskNum
#             self.formerInfo = self.info
#             self.recoder.reset(process)
#         elif self.recoder.flash(process).time > 60:
#             self.recoder.reset(process)
#         else:
#             self.info = self.recoder.flash(process)
#             if taskNum > 0:
#                 speedPerConnect = self.info.speed / taskNum
#                 if speedPerConnect > self.maxSpeedPerConnect:
#                     self.maxSpeedPerConnect = speedPerConnect
            
#             speedDeltaPerNewThread = (self.info.speed - self.formerInfo.speed) / (taskNum - self.formerTaskNum)
#             efficiency = speedDeltaPerNewThread / self.maxSpeedPerConnect
#             offset = self.accuracy / self.info.time

#             if efficiency > self.threshold + offset:

#                 if taskNum < 256:
                    
            


    
    