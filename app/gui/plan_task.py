import sys
from subprocess import Popen

from app.supports import utils

# 计划任务的完成后动作（复刻原版）。纯桌面 OS 动作，只在 gui 端调（headless daemon 不涉及关机/重启）。
# 实际关机/重启需在真机验收——这里只把各平台命令拼对。


def executePlanAction(action: str, filePath: str) -> None:
    if action == "openFile":
        if filePath:
            utils.openFile(filePath)
        return

    if action == "restart":
        if sys.platform == "win32":
            Popen(["shutdown", "/r", "/t", "0"])
        elif sys.platform == "darwin":
            Popen(["osascript", "-e", 'tell app "System Events" to restart'])
        else:
            Popen(["shutdown", "-r", "now"])
        return

    # 默认 shutdown
    if sys.platform == "win32":
        Popen(["shutdown", "/s", "/t", "0"])
    elif sys.platform == "darwin":
        Popen(["osascript", "-e", 'tell app "System Events" to shut down'])
    else:
        Popen(["shutdown", "-h", "now"])
