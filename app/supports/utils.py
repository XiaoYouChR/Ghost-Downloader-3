from time import sleep
import os
import sys
from datetime import datetime
from functools import wraps
from typing import Callable

from PySide6.QtCore import QUrl, QOperatingSystemVersion
from PySide6.QtGui import QDesktopServices, QColor
from loguru import logger
from qfluentwidgets import MessageBox, setThemeColor
from qframelesswindow.utils import getSystemAccentColor

from app.supports.config import cfg, Headers
from app.supports.signal_bus import signalBus

def setAppColor(color: QColor | None = None):
    if color is None or not isinstance(color, QColor):
        if sys.platform == "win32" or "darwin":
            setThemeColor(getSystemAccentColor(), save=False)
        if sys.platform == "linux":
            if "KDE_SESSION_UID" in os.environ:  # KDE Plasma
                import configparser

                config = configparser.ConfigParser()

                config.read(f"/home/{os.getlogin()}/.config/kdeglobals")

                # 获取 DecorationFocus 的值
                if "Colors:Window" in config:
                    color = list(
                        map(
                            int,
                            config.get("Colors:Window", "DecorationFocus").split(","),
                        )
                    )
                    setThemeColor(QColor(*color))

    else:
        setThemeColor(color, save=False)

def isGreaterEqualWin10():
    """determine if the Windows version ≥ Win10"""
    cv = QOperatingSystemVersion.current()
    return sys.platform == "win32" and cv.majorVersion() >= 10

def isLessThanWin10():
    """determine if the Windows version < Win10"""
    cv = QOperatingSystemVersion.current()
    return sys.platform == "win32" and cv.majorVersion() < 10

def isGreaterEqualWin11():
    """determine if the windows version ≥ Win11"""
    return isGreaterEqualWin10() and sys.getwindowsversion().build >= 22000  # type: ignore

def isAbleToShowToast():
    return (
        sys.platform == "win32" and sys.getwindowsversion().build >= 16299
    )  # 高于 Win10 1709

def getSystemProxy():
    if sys.platform == "win32":
        try:
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
            )

            proxyEnable, _ = winreg.QueryValueEx(key, "ProxyEnable")

            if proxyEnable:
                proxyServer, _ = winreg.QueryValueEx(key, "ProxyServer")

                if "http=" in proxyServer:
                    proxyServer = proxyServer.split(';')[0].split('=')[1]

                if not proxyServer.startswith("http://") and not proxyServer.startswith("https://"):
                     return "http://" + proxyServer
                return proxyServer
            else:
                return None

        except FileNotFoundError:
            return None
        except Exception as e:
            logger.error(f"无法获取 Windows 代理服务器: {e}")
            return None

    elif sys.platform == "linux":  # 读取 Linux 系统代理
        try:
            proxyUrl = os.environ.get("https_proxy") or os.environ.get("http_proxy")
            return proxyUrl
        except Exception as e:
            logger.error(f"无法获取 Linux 代理服务器: {e}")
            return None

    elif sys.platform == "darwin":
        import SystemConfiguration
        _ = SystemConfiguration.SCDynamicStoreCopyProxies(None) # type: ignore

        if _.get("SOCKSEnable", 0):
            return f"socks5://{_.get('SOCKSProxy')}:{_.get('SOCKSPort')}"
        elif _.get("HTTPEnable", 0):
            return f"http://{_.get('HTTPProxy')}:{_.get('HTTPPort')}"
        else:
            return None
    return None


def getProxy():
    if cfg.proxyServer.value == "Off":
        return None
    elif cfg.proxyServer.value == "Auto":
        return getSystemProxy()
    else:
        return cfg.proxyServer.value


def getReadableSize(size):
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    unit_index = 0
    K = 1024.0
    while size >= K:
        size = size / K
        unit_index += 1
    return "%.2f %s" % (size, units[unit_index])


def retry(retries: int = 3, delay: float = 0.1, handleFunction: Callable = lambda e: None):
    """
    是装饰器。函数执行失败时，重试

    :param retries: 最大重试的次数
    :param delay: 每次重试的间隔时间，单位 秒
    :param handleFunction: 处理函数，用来处理异常
    :return:
    """
    # 校验重试的参数，参数值不正确时使用默认参数
    if retries < 1 or delay <= 0:
        retries = 3
        delay = 1

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for i in range(retries + 1):  # 第一次正常执行不算重试次数，所以 retries+1
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    # 检查重试次数
                    if i == retries:
                        logger.error(
                            f'Error: {repr(e)}! "{func.__name__}()" 执行失败，已重试{retries}次.'
                        )
                        try:
                            handleFunction(e)
                        finally:
                            break
                    else:
                        logger.warning(
                            f'Error: {repr(e)}! "{func.__name__}()"执行失败，将在{delay}秒后第[{i + 1}/{retries}]次重试...'
                        )
                        sleep(delay)

        return wrapper

    return decorator


def openFile(fileResolve):
    """
    打开文件

    :param fileResolve: 文件路径
    """
    QDesktopServices.openUrl(QUrl.fromLocalFile(fileResolve))


def getLocalTimeFromGithubApiTime(gmtTimeStr: str) -> datetime:
    """
    将 GitHub API 返回的 GMT 时间字符串（ISO8601 格式）转换为本地时间（无时区信息）。

    Args:
        gmtTimeStr: 形如 "2024-06-01T12:34:56Z" 的时间字符串

    Returns:
        本地时间（datetime，无 tzinfo）
    """
    # 解析为带时区的 datetime
    gmtTime = datetime.fromisoformat(gmtTimeStr.replace("Z", "+00:00"))
    # 转换为本地时区
    localTime = gmtTime.astimezone()
    # 返回去除 tzinfo 的本地时间
    return localTime.replace(tzinfo=None)


def bringWindowToTop(window):
    window.show()
    if window.isMinimized():
        window.showNormal()
    # 激活窗口，使其显示在最前面
    window.activateWindow()
    window.raise_()


def addDownloadTask(
    url: str,
    fileName: str | None = None,
    filePath: str | None = None,
    headers: dict | None = None,
    status: str = "working",
    preBlockNum: int | None = None,
    notCreateHistoryFile: bool = False,
    fileSize: int = -1,
):
    """Global function to add download task"""
    if not filePath:
        filePath = cfg.downloadFolder.value

    if not preBlockNum:
        preBlockNum = cfg.preBlockNum.value

    if not headers:
        headers = Headers

    signalBus.addTaskSignal.emit(
        url,
        fileName,
        filePath,
        headers,
        status,
        preBlockNum,
        notCreateHistoryFile,
        str(fileSize),
    )


def showMessageBox(self, title: str, content: str, showYesButton=False, yesSlot=None):
    """show message box"""
    w = MessageBox(title, content, self)
    if not showYesButton:
        w.cancelButton.setText("关闭")
        w.yesButton.hide()
        w.buttonLayout.insertStretch(0, 1)

    if w.exec() and yesSlot is not None:
        yesSlot()

async def checkUpdate(self):
    """check update"""
    ...
