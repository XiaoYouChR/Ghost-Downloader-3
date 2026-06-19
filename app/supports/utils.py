import re
import shutil
import sys
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path
from time import sleep
from typing import TYPE_CHECKING, Callable
from urllib.request import getproxies

from PySide6.QtCore import QUrl, Qt, QProcess
from PySide6.QtGui import QDesktopServices
from loguru import logger
from wreq import Client, Emulation, HeaderMap, Proxy
from wreq.emulation import Platform, Profile
from wreq.redirect import Policy
from qfluentwidgets import MessageBox, ToolButton, FluentIcon

from app.supports.config import cfg
from app.supports.paths import APP_DATA_DIR

if TYPE_CHECKING:
    from app.bases.models import Task
    from os import PathLike


def _makeWreqExceptionsPicklable() -> None:
    import wreq.exceptions
    for cls in vars(wreq.exceptions).values():
        if isinstance(cls, type) and issubclass(cls, BaseException) and cls.__module__ == "exceptions":
            cls.__module__ = "wreq.exceptions"


_makeWreqExceptionsPicklable()


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


# 收移动端变体供 auto 匹配 iOS Safari / Android Firefox; 菜单家族另见 _MENU_FAMILY_ORDER
_FAMILY_BY_PREFIX = {
    "Chrome": "chrome", "Edge": "edge", "Firefox": "firefox", "Safari": "safari", "OkHttp": "okhttp",
    "FirefoxAndroid": "firefox-android", "SafariIos": "safari-ios",
    "SafariIPad": "safari-ipad", "SafariIpad": "safari-ipad",  # wreq 两种拼写并存
}
_MENU_FAMILY_ORDER = ("chrome", "edge", "firefox", "safari", "okhttp")
# 固定平台的家族(其余浏览器跟随来源 UA / 本机)
_PLATFORM_BY_FAMILY = {
    "okhttp": Platform.Android,
    "firefox-android": Platform.Android,
    "safari-ios": Platform.IOS,
    "safari-ipad": Platform.IOS,
}
_PROFILE_NAME_PATTERN = re.compile(r"^([A-Za-z]+?)(\d[\d_]*)$")
# Edge/Opera 的 UA 也含 "Chrome/", 顺序上须先判 Edge
_UA_FAMILY_PATTERNS = (
    ("edge", re.compile(r"Edg(?:e|A|iOS)?/(\d+)")),
    ("okhttp", re.compile(r"okhttp/(\d+)", re.IGNORECASE)),
    ("firefox", re.compile(r"Firefox/(\d+)")),
    ("chrome", re.compile(r"Chrome/(\d+)")),
    ("safari", re.compile(r"Version/(\d+).+Safari/")),
)


def _profileVersion(name: str) -> tuple[str, tuple[int, ...]] | None:
    match = _PROFILE_NAME_PATTERN.match(name)
    if not match:
        return None
    return match.group(1), tuple(int(part) for part in match.group(2).split("_"))


_PROFILE_BY_NAME: dict[str, Profile] = {
    name: getattr(Emulation, name)
    for name in dir(Emulation)
    if _PROFILE_NAME_PATTERN.match(name) and isinstance(getattr(Emulation, name), Profile)
}


def _profilesByFamily() -> dict[str, list[tuple[str, tuple[int, ...], Profile]]]:
    families: dict[str, list[tuple[str, tuple[int, ...], Profile]]] = {family: [] for family in set(_FAMILY_BY_PREFIX.values())}
    for name, profile in _PROFILE_BY_NAME.items():
        parsed = _profileVersion(name)
        family = _FAMILY_BY_PREFIX.get(parsed[0]) if parsed else None
        if family is None:
            continue
        families[family].append((name, parsed[1], profile))
    for items in families.values():
        items.sort(key=lambda item: item[1], reverse=True)
    return families


_PROFILES_BY_FAMILY = _profilesByFamily()
# 只暴露真有 profile 的菜单家族, 既保证 toEmulation/menu 不会索引到空家族, 也跟随 wreq 实际能力
EMULATION_FAMILIES = tuple(family for family in _MENU_FAMILY_ORDER if _PROFILES_BY_FAMILY.get(family))


def _latestProfile(family: str) -> Profile:
    return _PROFILES_BY_FAMILY[family][0][2]


def _latestMajor(family: str) -> int:
    return _PROFILES_BY_FAMILY[family][0][1][0]


# Chrome 自 UA reduction 起 UA 固定 .0.0.0, 套模板即等于 wreq 真实 Chrome UA, 版本随 wreq 走
DEFAULT_USER_AGENT = (
    f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    f"(KHTML, like Gecko) Chrome/{_latestMajor('chrome')}.0.0.0 Safari/537.36"
)


def familyProfileNames(family: str) -> list[str]:
    return [name for name, _version, _profile in _PROFILES_BY_FAMILY.get(family, [])]


def _hostPlatform() -> Platform:
    return {"win32": Platform.Windows, "darwin": Platform.MacOS}.get(sys.platform, Platform.Linux)


def _uaPlatform(userAgent: str) -> Platform:
    if "Android" in userAgent:
        return Platform.Android
    if any(token in userAgent for token in ("iPhone", "iPad", "iPod")):
        return Platform.IOS
    if "Windows" in userAgent:
        return Platform.Windows
    if "Mac OS X" in userAgent or "Macintosh" in userAgent:
        return Platform.MacOS
    if "Linux" in userAgent:
        return Platform.Linux
    return _hostPlatform()


def _profilePlatform(name: str) -> Platform:
    parsed = _profileVersion(name)
    family = _FAMILY_BY_PREFIX.get(parsed[0]) if parsed else None
    return _PLATFORM_BY_FAMILY.get(family, _hostPlatform())


def _matchFamily(family: str, platform: Platform) -> str:
    # 移动端有专属 profile 时换过去, 免得拿桌面 TLS 配 iOS/Android(指纹自相矛盾)
    if family == "safari" and platform == Platform.IOS and _PROFILES_BY_FAMILY.get("safari-ios"):
        return "safari-ios"
    if family == "firefox" and platform == Platform.Android and _PROFILES_BY_FAMILY.get("firefox-android"):
        return "firefox-android"
    return family


def _nearestProfile(family: str, major: int) -> Profile | None:
    profiles = _PROFILES_BY_FAMILY.get(family)
    if not profiles:
        return None
    for _name, version, profile in profiles:
        if version[0] <= major:
            return profile
    return profiles[-1][2]


def _matchEmulation(userAgent: str | None) -> Emulation | None:
    if not userAgent:
        return None
    for family, pattern in _UA_FAMILY_PATTERNS:
        match = pattern.search(userAgent)
        if not match:
            continue
        platform = _PLATFORM_BY_FAMILY.get(family) or _uaPlatform(userAgent)
        profile = _nearestProfile(_matchFamily(family, platform), int(match.group(1)))
        if profile is None:
            return None
        return Emulation(profile=profile, platform=platform)
    return None


def _defaultEmulation() -> Emulation:
    return Emulation(profile=_latestProfile("chrome"), platform=_hostPlatform())


def toEmulation(profile: str, sourceUserAgent: str | None = None) -> Emulation | None:
    profile = profile or cfg.clientProfile.value  # "" = 跟随全局
    if profile == "raw":
        return None
    if profile == "auto":
        return _matchEmulation(sourceUserAgent) or _defaultEmulation()
    if profile in EMULATION_FAMILIES:
        return Emulation(profile=_latestProfile(profile), platform=_PLATFORM_BY_FAMILY.get(profile, _hostPlatform()))
    pinned = _PROFILE_BY_NAME.get(profile)
    if pinned is None:
        logger.warning("未知的模拟身份 {}, 退回默认", profile)
        return _defaultEmulation()
    return Emulation(profile=pinned, platform=_profilePlatform(profile))


def userAgent(headers: dict | None) -> str | None:
    if not headers:
        return None
    for name, value in headers.items():
        if name.lower() == "user-agent":
            return value
    return None


def stripEmulationHeaders(headers: dict[str, str]) -> dict[str, str]:
    return {
        name: value
        for name, value in headers.items()
        if name.lower() != "user-agent" and not name.lower().startswith("sec-ch-ua")
    }


def toRequestHeaders(headers: dict | None, emulation: Emulation | None) -> dict:
    headers = headers or {}
    if emulation is not None:
        return stripEmulationHeaders(headers)
    if userAgent(headers) is None:
        return {**headers, "user-agent": DEFAULT_USER_AGENT}
    return dict(headers)


def toProxies(proxies: dict | None) -> list[Proxy]:
    if not proxies:
        return []
    url = next((value for value in proxies.values() if value), "")
    return [Proxy.all(url)] if url else []


_USE_GLOBAL_PROFILE = object()


def buildClient(
    proxies: dict | None = None,
    *,
    emulation: Emulation | None = _USE_GLOBAL_PROFILE,
    headers: dict | None = None,
    timeout: int | None = None,
) -> Client:
    resolved = toEmulation("") if emulation is _USE_GLOBAL_PROFILE else emulation
    config = {
        "proxies": toProxies(proxies),
        "tls_verify": cfg.SSLVerify.value,
        "redirect": Policy.limited(10),
    }
    if resolved is not None:
        config["emulation"] = resolved
    if headers:
        config["headers"] = toRequestHeaders(headers, resolved)
    if timeout is not None:
        config["timeout"] = timedelta(seconds=timeout)
    return Client(**config)


def _toStr(value: str | bytes) -> str:
    return value.decode("latin-1") if isinstance(value, (bytes, bytearray)) else value


def headerDict(headers: HeaderMap) -> dict[str, str]:
    # HeaderMap 键/值皆 bytes
    result = {}
    for key in headers.keys():
        name = _toStr(key)
        result[name.lower()] = _toStr(headers.get(name))
    return result





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
