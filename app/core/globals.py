from PySide6.QtCore import QTimer

globalSpeed = 0  # 用于记录每秒下载速度, 单位 KB/s

def resetGlobalSpeed(self):
    self.globalSpeed = 0

BASE_UTILIZATION_THRESHOLD = 0.1 # 判断阈值
TIME_WEIGHT_FACTOR = 1  # 判断精度

# create SpeedLimiter
speedLimiter = QTimer()  # 限速器
speedLimiter.setInterval(1000)  # 一秒刷新一次
speedLimiter.timeout.connect(resetGlobalSpeed)  # 刷新 globalSpeed为 0
speedLimiter.start()