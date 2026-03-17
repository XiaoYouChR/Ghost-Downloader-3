import os
import sys
from datetime import datetime
from functools import wraps
from pathlib import Path
from time import sleep
from typing import Callable

from PySide6.QtCore import QUrl, QOperatingSystemVersion, Qt, QProcess
from PySide6.QtGui import QDesktopServices
from loguru import logger
from qfluentwidgets import MessageBox

from app.bases.models import Task
from app.supports.config import cfg

def openFolder(path):
    path = Path(path)
    if path.exists():
        folder = str(path.parent)
        target = str(path)
        match sys.platform:
            case 'win32':
                QProcess.startDetached("explorer.exe", ["/select,", target])
            case 'linux':
                QProcess.startDetached("xdg-open", [folder])
            case 'darwin':
                QProcess.startDetached("open", ["-R", target])
    elif path.parent.exists():
        QDesktopServices.openUrl(QUrl.fromLocalFile(path.parent))
    else:
        raise FileNotFoundError(path)


def isGreaterEqualWin10():
    """determine if the Windows version ≥ Win10"""
    cv = QOperatingSystemVersion.current()
    return sys.platform == "win32" and cv.majorVersion() >= 10


def isLessThanWin10():
    """determine if the Windows version < Win10"""
    cv = QOperatingSystemVersion.current()
    return sys.platform == "win32" and cv.majorVersion() < 10


def isGreaterEqualWin11():
    """determine if the Windows version ≥ Win11"""
    return isGreaterEqualWin10() and sys.getwindowsversion().build >= 22000  # type: ignore


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

                # TODO 当 http 代理和 https 代理不同时，当前实现只能获取 http 代理，后续可以改进为分别获取 http 和 https 代理
                if "http=" in proxyServer:
                    proxyServer = proxyServer.split(";")[0].split("=")[1]

                if not proxyServer.startswith("http://") and not proxyServer.startswith(
                    "https://"
                ):
                    proxyServer = "http://" + proxyServer

                # 尝试从 Windows 凭证管理器获取用户名和密码
                username = None
                password = None
                try:
                    proxyUser, _ = winreg.QueryValueEx(key, "ProxyUser")
                    if proxyUser:
                        username = proxyUser
                    proxyPass, _ = winreg.QueryValueEx(key, "ProxyPass")
                    if proxyPass:
                        password = proxyPass
                except (FileNotFoundError, OSError):
                    # 注册表中未找到用户名或密码
                    pass

                # 如果有用户名和密码，插入到代理 URL 中
                if username or password:
                    protocol = proxyServer[: proxyServer.find("://")]
                    hostPort = proxyServer[proxyServer.find("://") + 3 :]
                    credentials = f"{username or ''}:{password or ''}"
                    proxyServer = f"{protocol}://{credentials}@{hostPort}"

                return proxyServer
            else:
                return None

        except FileNotFoundError:
            return None
        except Exception as e:
            logger.opt(exception=e).error("无法获取 Windows 代理服务器")
            return None

    elif sys.platform == "linux":  # 读取 Linux 系统代理
        try:
            proxyUrl = os.environ.get("https_proxy") or os.environ.get("http_proxy")
            return proxyUrl
        except Exception as e:
            logger.opt(exception=e).error("无法获取 Linux 代理服务器")
            return None

    elif sys.platform == "darwin":
        import SystemConfiguration

        _ = SystemConfiguration.SCDynamicStoreCopyProxies(None)  # type: ignore

        if _.get("SOCKSEnable", 0):
            return f"socks5://{_.get('SOCKSProxy')}:{_.get('SOCKSPort')}"
        elif _.get("HTTPEnable", 0):
            return f"http://{_.get('HTTPProxy')}:{_.get('HTTPPort')}"
        else:
            return None

    return None


def getProxies():
    if cfg.proxyServer.value == "Off":
        return None
    elif cfg.proxyServer.value == "Auto":
        return {"http": getSystemProxy(), "https": getSystemProxy()}
    else:
        return {"http": cfg.proxyServer.value, "https": cfg.proxyServer.value}


def getReadableSize(size: int):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} TB"

def getReadableTime(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        return f"{seconds // 60}m{seconds % 60}s"
    else:
        remainingSeconds = seconds % 3600
        return f"{int(seconds // 3600)}h{int(remainingSeconds // 60)}m{remainingSeconds % 60}s"


def ensureUniqueTaskTarget(
    task: Task,
) -> bool:
    target = Path(task.resolvePath.strip())
    if not target.name:
        return False

    if not target.exists() and not Path(f"{target}.ghd").exists():
        return False

    suffixes = "".join(target.suffixes)   # .tar.gz
    stem = target.name[:-len(suffixes)] if suffixes else target.name    # stem 不会去除所有的后缀

    index = 1
    while True:
        renamed = target.with_name(f"{stem}({index}){suffixes}")
        if not renamed.exists() and not Path(f"{renamed}.ghd").exists():
            task.setTitle(renamed.name)
            return True
        index += 1


def retry(
    retries: int = 3, delay: float = 0.1, handleFunction: Callable = lambda e: None
):
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
                        logger.opt(exception=e).error(
                            '"{}()" 执行失败，已重试 {} 次',
                            func.__name__,
                            retries,
                        )
                        try:
                            handleFunction(e)
                        finally:
                            break
                    else:
                        logger.warning(
                            '"{}()" 执行失败，将在 {} 秒后第 [{}/{}] 次重试: {}',
                            func.__name__,
                            delay,
                            i + 1,
                            retries,
                            e,
                        )
                        sleep(delay)
            return None

        return wrapper

    return decorator


def openFile(fileResolve: "str | bytes | os.PathLike[str]"):
    """
    打开文件

    :param fileResolve: 文件路径
    """
    QDesktopServices.openUrl(QUrl.fromLocalFile(fileResolve))


def getLocalTimeFromGithubApiTime(gmtTimeStr: str) -> str:
    """
    将 GitHub API 返回的 GMT 时间字符串（ISO8601 格式）转换为本地时间（无时区信息）。

    Args:
        gmtTimeStr: 形如 "2024-06-01T12:34:56Z" 的时间字符串

    Returns:
        本地时间（datetime，无 tzinfo）
    """
    localTime = datetime.fromisoformat(gmtTimeStr.replace("Z", "+00:00")).astimezone()

    return localTime.strftime("%Y-%m-%d %H:%M:%S")


def bringWindowToTop(window):
    window.show()
    if window.isMinimized():
        window.showNormal()
    # 激活窗口，使其显示在最前面
    window.activateWindow()
    window.raise_()


def showMessageBox(self, title: str, content: str, showYesButton=False, yesSlot=None):
    """show message box"""
    w = MessageBox(title, content, self)
    w.contentLabel.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    if not showYesButton:
        w.cancelButton.setText(self.tr("关闭"))
        w.yesButton.hide()
        w.buttonLayout.insertStretch(0, 1)

    if w.exec() and yesSlot is not None:
        yesSlot()
