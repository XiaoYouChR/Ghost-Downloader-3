import re
import sys
from datetime import datetime
from functools import wraps
from pathlib import Path
from time import sleep
from typing import TYPE_CHECKING, Callable

from niquests.utils import getproxies
from PySide6.QtCore import QUrl, Qt, QProcess, QStandardPaths
from PySide6.QtGui import QDesktopServices
from loguru import logger
from qfluentwidgets import MessageBox, ToolButton, FluentIcon

from app.supports.config import cfg

if TYPE_CHECKING:
    from app.bases.models import Task


_PROXY_PROTOCOLS = ("http", "https", "ftp")
_INVALID_FILENAME_CHARS_PATTERN = re.compile(r'[\x00-\x1f\x7f<>:"/\\|?*]+')
_WINDOWS_RESERVED_FILENAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def _normalizeFilenameCandidate(value: str) -> str:
    candidate = str(value or "")
    lastSeparator = max(candidate.rfind("/"), candidate.rfind("\\"))
    if lastSeparator >= 0:
        candidate = candidate[lastSeparator + 1:]

    candidate = _INVALID_FILENAME_CHARS_PATTERN.sub("_", candidate).strip()
    candidate = candidate.rstrip(". ")

    if candidate in {"", ".", ".."}:
        return ""

    root, _, _ = candidate.partition(".")
    if root.upper() in _WINDOWS_RESERVED_FILENAMES:
        candidate = f"_{candidate}"

    return candidate


def sanitizeFilename(name: str, fallback: str = "file", maxLength: int = 200) -> str:
    normalizedFallback = ""
    candidate = _normalizeFilenameCandidate(name)

    if not candidate:
        normalizedFallback = _normalizeFilenameCandidate(fallback) or "file"
        candidate = normalizedFallback

    if maxLength > 0 and len(candidate) > maxLength:
        stem, dot, suffix = candidate.rpartition(".")
        if stem and dot:
            maxStemLength = maxLength - len(dot + suffix)
            if maxStemLength <= 0:
                candidate = candidate[:maxLength]
            else:
                candidate = f"{stem[:maxStemLength]}{dot}{suffix}"
        else:
            candidate = candidate[:maxLength]

        candidate = candidate.rstrip(". ")
        if candidate in {"", ".", ".."}:
            if not normalizedFallback:
                normalizedFallback = _normalizeFilenameCandidate(fallback) or "file"
            candidate = normalizedFallback

    return candidate


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


def openAppLogFolder():
    appLocalDataLocation = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.GenericDataLocation)
    openFolder(f"{appLocalDataLocation}/GhostDownloader/GhostDownloader.log")


def getProxies():
    if cfg.proxyServer.value == "Off":
        return None

    if cfg.proxyServer.value == "Auto":
        return getproxies() or None

    proxyServer = str(cfg.proxyServer.value).strip()
    if not proxyServer:
        return None

    return {protocol: proxyServer for protocol in _PROXY_PROTOCOLS}


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
    task: "Task",
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


def showMessageBox(
    self,
    title: str,
    content: str,
    showYesButton=False,
    yesSlot=None,
    actionIcon: FluentIcon | None = None,
    actionSlot=None,
):
    """show message box"""
    w = MessageBox(title, content, self)
    w.contentLabel.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    if not showYesButton:
        w.cancelButton.setText(self.tr("关闭"))
        w.yesButton.hide()
        w.buttonLayout.insertStretch(0, 1)

    if actionIcon and actionSlot is not None:
        actionButton = ToolButton(actionIcon, w)
        actionButton.clicked.connect(actionSlot)
        w.buttonLayout.insertWidget(3, actionButton)

    if w.exec() and yesSlot is not None:
        yesSlot()
