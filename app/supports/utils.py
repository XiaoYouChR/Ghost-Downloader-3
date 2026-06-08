import asyncio as _asyncio
import re
import shutil
import subprocess
import sys
import threading
from datetime import datetime
from functools import wraps
from http.cookiejar import CookieJar
from pathlib import Path
from time import sleep
from typing import TYPE_CHECKING, Callable
from urllib.request import getproxies

from PySide6.QtCore import QUrl, Qt, QProcess
from PySide6.QtGui import QDesktopServices
from loguru import logger
from niquests.cookies import RequestsCookieJar, cookiejar_from_dict
from qfluentwidgets import MessageBox, ToolButton, FluentIcon

from app.supports.config import cfg
from app.supports.paths import APP_DATA_DIR

if TYPE_CHECKING:
    from app.bases.models import Task
    from os import PathLike


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


def _sanitize(value: str) -> str:
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


def toSafeFilename(name: str, fallback: str = "file", maxLength: int = 200) -> str:
    normalizedFallback = ""
    candidate = _sanitize(name)

    if not candidate:
        normalizedFallback = _sanitize(fallback) or "file"
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
                normalizedFallback = _sanitize(fallback) or "file"
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
    openFolder(f"{APP_DATA_DIR}/GhostDownloader.log")


def getProxies():
    if cfg.proxyServer.value == "Off":
        return None

    if cfg.proxyServer.value == "Auto":
        return getproxies() or None

    proxyServer = str(cfg.proxyServer.value).strip()
    if not proxyServer:
        return None

    return {protocol: proxyServer for protocol in _PROXY_PROTOCOLS}


def splitCookies(headers: dict[str, str] | None) -> tuple[dict[str, str], "RequestsCookieJar | CookieJar | None"]:
    requestHeaders = dict(headers or {})
    cookieHeader = str(requestHeaders.pop("cookie", "") or "").strip()
    if not cookieHeader:
        return requestHeaders, None

    cookieItems: dict[str, str] = {}
    for part in cookieHeader.replace("\r", ";").replace("\n", ";").split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue

        name, value = part.split("=", 1)
        name = name.strip()
        value = str(value or "").strip()
        if not name or not value:
            continue
        if any(ord(c) < 32 or ord(c) == 127 for c in value):
            continue

        encodedValue = value if all(ord(c) <= 255 for c in value) else value.encode("utf-8").decode("latin-1")
        cookieItems[name] = encodedValue

    if not cookieItems:
        return requestHeaders, None

    return requestHeaders, cookiejar_from_dict(cookieItems)





def toReadableSize(size: int):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} TB"





def toReadableTime(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        return f"{seconds // 60}m{seconds % 60}s"
    else:
        remainingSeconds = seconds % 3600
        return f"{int(seconds // 3600)}h{int(remainingSeconds // 60)}m{remainingSeconds % 60}s"





def toPosixPath(path) -> str:
    return str(Path(path)).replace("\\", "/")


def toExecutable(name: str) -> str:
    return f"{name}.exe" if sys.platform == "win32" else name


def create_subprocess_exec(program, *args, stdin=None, stdout=None, stderr=None,
                           cwd=None, env=None, **kwargs):
    """Like asyncio.create_subprocess_exec but hides console window on Windows.

    On Windows, winloop's subprocess_exec rejects startupinfo/creationflags, so we
    use subprocess.Popen with a reader thread to provide async-compatible I/O.
    """
    if sys.platform == "win32":
        return _create_subprocess_win32(
            program, *args,
            stdin=stdin, stdout=stdout, stderr=stderr,
            cwd=cwd, env=env,
        )
    return _asyncio.create_subprocess_exec(
        program, *args,
        stdin=stdin, stdout=stdout, stderr=stderr,
        cwd=cwd, env=env, **kwargs,
    )


async def _create_subprocess_win32(program, *args, stdin=None, stdout=None, stderr=None,
                                   cwd=None, env=None):
    popen_args = [program, *args]

    _stdin = subprocess.DEVNULL if stdin == _asyncio.subprocess.DEVNULL else stdin
    _stdout = subprocess.PIPE if stdout == _asyncio.subprocess.PIPE else stdout
    _stderr = subprocess.PIPE if stderr == _asyncio.subprocess.PIPE else stderr
    if stderr == _asyncio.subprocess.STDOUT:
        _stderr = subprocess.STDOUT

    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = subprocess.SW_HIDE

    proc = subprocess.Popen(
        popen_args,
        stdin=_stdin,
        stdout=_stdout,
        stderr=_stderr,
        cwd=str(cwd) if cwd is not None else None,
        env=env,
        startupinfo=si,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )

    return _AsyncPopenWrapper(proc)


class _AsyncPopenWrapper:
    """Wraps subprocess.Popen with async-compatible stdout / stderr / wait."""

    def __init__(self, proc):
        self._proc = proc
        self.returncode = None
        self.stdout = _AsyncPipeReader(proc.stdout) if proc.stdout is not None else None
        self.stderr = _AsyncPipeReader(proc.stderr) if proc.stderr is not None else None

    async def wait(self):
        await _asyncio.to_thread(self._proc.wait)
        self.returncode = self._proc.returncode
        return self.returncode

    async def communicate(self, input=None):
        return await _asyncio.to_thread(self._proc.communicate, input)

    def kill(self):
        self._proc.kill()

    def terminate(self):
        self._proc.terminate()


class _AsyncPipeReader:
    """Provides async readline() and read() over a blocking pipe."""

    def __init__(self, pipe):
        self._queue = _asyncio.Queue()
        self._loop = _asyncio.get_running_loop()
        self._thread = threading.Thread(target=self._read_loop, args=(pipe,), daemon=True)
        self._thread.start()

    def _read_loop(self, pipe):
        try:
            for line in pipe:
                self._loop.call_soon_threadsafe(self._queue.put_nowait, line)
        finally:
            self._loop.call_soon_threadsafe(self._queue.put_nowait, None)

    async def readline(self):
        line = await self._queue.get()
        return line if line is not None else b""

    async def read(self):
        chunks = []
        while True:
            chunk = await self._queue.get()
            if chunk is None:
                break
            chunks.append(chunk)
        return b"".join(chunks)


def findExecutable(installFolder: Path, name: str, *subdirs: str) -> str:
    exe = toExecutable(name)
    candidates = [installFolder / sub / exe for sub in subdirs]
    candidates.append(installFolder / exe)
    for candidate in candidates:
        if candidate.is_file():
            return toPosixPath(candidate)
    found = shutil.which(name)
    return toPosixPath(found) if found else ""


def removePath(path: Path):
    try:
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path, ignore_errors=True)
        elif path.is_file() or path.is_symlink():
            path.unlink(missing_ok=True)
    except FileNotFoundError:
        return
    except PermissionError:
        logger.warning("skip removing busy {}", path)
    except Exception as e:
        logger.opt(exception=e).error("failed to remove {}", path)


def toBytes(value: str, unit: str) -> int:
    _SCALE = {"B": 1, "KB": 1024, "MB": 1024 ** 2, "GB": 1024 ** 3,
              "Bps": 1, "KBps": 1024, "MBps": 1024 ** 2, "GBps": 1024 ** 3}
    return int(float(value) * _SCALE[unit])


def deduplicateFilename(
    task: "Task",
) -> bool:
    target = Path(task.outputFolder.strip())
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


def openFile(fileResolve: "str | bytes | PathLike[str]"):
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


def bringWindowToTop(window) -> None:
    window.show()
    window.setWindowState(
        (window.windowState() & ~Qt.WindowState.WindowMinimized) | Qt.WindowState.WindowActive
    )
    window.raise_()
    window.activateWindow()

    if sys.platform == "win32":
        try:
            _bringWindowToTopOnWindows(int(window.winId()))
        except Exception as e:
            logger.opt(exception=e).warning("Failed to bring window to top on Windows")


def _bringWindowToTopOnWindows(hwnd: int) -> None:
    import win32api
    import win32con
    import win32gui
    import win32process

    if win32gui.IsIconic(hwnd):
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)

    foregroundHwnd = win32gui.GetForegroundWindow()
    foregroundThreadId = (
        win32process.GetWindowThreadProcessId(foregroundHwnd)[0]
        if foregroundHwnd
        else 0
    )
    currentThreadId = win32api.GetCurrentThreadId()
    attached = False

    try:
        if foregroundThreadId and foregroundThreadId != currentThreadId:
            win32process.AttachThreadInput(currentThreadId, foregroundThreadId, True)
            attached = True

        win32gui.BringWindowToTop(hwnd)
        win32gui.SetForegroundWindow(hwnd)
        flags = win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW
        win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0, flags)
        win32gui.SetWindowPos(hwnd, win32con.HWND_NOTOPMOST, 0, 0, 0, 0, flags)
    finally:
        if attached:
            win32process.AttachThreadInput(currentThreadId, foregroundThreadId, False)


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
