import ctypes
import importlib
import inspect
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from email.utils import decode_rfc2231
from functools import wraps
from pathlib import Path
from time import sleep, localtime, time_ns
from urllib.parse import unquote, parse_qs, urlparse

import httpx
from PySide6.QtCore import QUrl, QOperatingSystemVersion, QResource
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication
from loguru import logger
from qfluentwidgets import MessageBox

from app.common.config import cfg, Headers
from app.common.plugin_base import PluginBase
from app.common.signal_bus import signalBus

plugins = []

def isGreaterEqualWin10():
    """ determine if the Windows version ≥ Win10 """
    cv = QOperatingSystemVersion.current()
    return sys.platform == "win32" and cv.majorVersion() >= 10

def isLessThanWin10():
    """  determine if the Windows version < Win10"""
    cv = QOperatingSystemVersion.current()
    return sys.platform == "win32" and cv.majorVersion() < 10

def isGreaterEqualWin11():
    """ determine if the windows version ≥ Win11 """
    return isGreaterEqualWin10() and sys.getwindowsversion().build >= 22000

def isAbleToShowToast():
    return sys.platform == 'win32' and sys.getwindowsversion().build >= 16299  # 高于 Win10 1709

def loadPlugins(mainWindow, directory="{}/plugins".format(cfg.appPath)):
    try:
        for filename in os.listdir(directory):
            if filename.endswith(".py") or filename.endswith(".pyd") or filename.endswith(".so"):

                module_name = filename.split(".")[0]
                file_path = os.path.join(directory, filename)

                # 动态导入模块
                spec = importlib.util.spec_from_file_location(module_name, file_path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                # 遍历模块中的所有成员
                for name, obj in inspect.getmembers(module):
                    # 检查是否是类，并且继承自 PluginBase
                    if inspect.isclass(obj) and issubclass(obj, PluginBase) and obj is not PluginBase:
                        try:
                            # 实例化插件并调用 load 方法
                            plugin_instance = obj(mainWindow)
                            plugin_instance.load()
                            logger.info(f"Loaded plugin: {plugin_instance.name}")
                            plugins.append(plugin_instance)
                        except Exception as e:
                            logger.error(f"Error loading plugin {name}: {e}")
    except Exception as e:
        logger.error(f"Error loading plugins: {e}")


def getSystemProxy():
    if sys.platform == "win32":
        try:
            import winreg

            # 打开 Windows 注册表项
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                 r'Software\Microsoft\Windows\CurrentVersion\Internet Settings')

            # 获取代理开关状态
            proxy_enable, _ = winreg.QueryValueEx(key, 'ProxyEnable')

            if proxy_enable:
                # 获取代理地址和端口号
                proxy_server, _ = winreg.QueryValueEx(key, 'ProxyServer')
                return "http://" + proxy_server
            else:
                return None

        except Exception as e:
            logger.error(f"Cannot get Windows proxy server：{e}")
            return None

    elif sys.platform == "linux":  # 读取 Linux 系统代理
        try:
            return os.environ.get("http_proxy")
        except Exception as e:
            logger.error(f"Cannot get Linux proxy server：{e}")
            return None

    elif sys.platform == "darwin":
        import SystemConfiguration

        _ = SystemConfiguration.SCDynamicStoreCopyProxies(None)

        if _.get('SOCKSEnable', 0):
            return f"socks5://{_.get('SOCKSProxy')}:{_.get('SOCKSPort')}"
        elif _.get('HTTPEnable', 0):
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


def retry(retries: int = 3, delay: float = 0.1, handleFunction: callable = None):
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
                        logger.error(f'Error: {repr(e)}! "{func.__name__}()" 执行失败，已重试{retries}次.')
                        try:
                            handleFunction(e)
                        finally:
                            break
                    else:
                        logger.warning(
                            f'Error: {repr(e)}! "{func.__name__}()"执行失败，将在{delay}秒后第[{i+1}/{retries}]次重试...'
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


def getLocalTimeFromGithubApiTime(gmtTimeStr:str):
    # 解析 GMT 时间
    gmtTime = datetime.fromisoformat(gmtTimeStr.replace("Z", "+00:00"))

    # 获取本地时间的时区偏移量（秒）
    localTimeOffsetSec = localtime().tm_gmtoff

    # 创建带有本地时区偏移量的时区信息
    localTz = timezone(timedelta(seconds=localTimeOffsetSec))

    # 转换为系统本地时间
    localTime = gmtTime.astimezone(localTz)

    # 去掉时区信息
    localTimeNaive = localTime.replace(tzinfo=None)

    return localTimeNaive

def attemptRegisterAppID(appId: str = "GD3", appName: str = "Ghost Downloader", iconPath: Path = Path("{}/logo.ico".format(cfg.appPath))):
    import winreg
    keyPath = f"SOFTWARE\\Classes\\AppUserModelId\\{appId}"
    
    try:
        reg_key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, keyPath)
        winreg.CloseKey(reg_key)
        return
    except FileNotFoundError:
        with open(iconPath, "wb") as f:
            f.write(QResource(":/image/logo.ico").data())
    
        winreg.ConnectRegistry(None, winreg.HKEY_CURRENT_USER)
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, keyPath) as masterKey:
            winreg.SetValueEx(masterKey, "DisplayName", 0, winreg.REG_SZ, appName)
            if iconPath is not None:
                winreg.SetValueEx(masterKey, "IconUri", 0, winreg.REG_SZ, str(iconPath.resolve()))
    except Exception as e:
        logger.error(f"Could not register the application: {e}")

def getLinkInfo(url: str, headers: dict, fileName: str = "", verify: bool = cfg.SSLVerify.value, proxy: str = "", followRedirects: bool = True) -> tuple:
    if not proxy:
        proxy = getProxy()
    headers = headers.copy()
    headers["Range"] = "bytes=0-"#尝试发送范围请求
    # 使用 stream 请求获取响应, 反爬
    with httpx.stream("GET", url, headers=headers, verify=verify, proxy=proxy, follow_redirects=followRedirects, trust_env=False) as response:
        response.raise_for_status()  # 如果状态码不是 2xx，抛出异常

        head = response.headers

        url = str(response.url)

        # 获取文件大小, 判断是否可以分块下载
        # 状态码为206才是范围请求，200表示服务器拒绝了范围请求同时将发送整个文件
        if response.status_code == 206 and "content-range" in head:
            #https://developer.mozilla.org/zh-CN/docs/Web/HTTP/Reference/Headers/Content-Range
            _left, _char, right = head["content-range"].rpartition("/")

            if right != "*":
                fileSize = int(right)
                logger.info(f"content-range: {head['content-range']}, fileSize: {fileSize}, content-length: {head['content-length']}")

            elif "content-length" in head:
                fileSize = int(head["content-length"])
                
            else:
                fileSize = 0
                logger.info("文件似乎支持续传，但无法获取文件大小")
        else:
            fileSize = 0
            logger.info("文件不支持续传")

        # 获取文件名
        if not fileName:
            try:
                # 尝试处理 Content-Disposition 中的 fileName* (RFC 5987 格式)
                headerValue = head["content-disposition"]
                if 'fileName*' in headerValue:
                    match = re.search(r'filename\*\s*=\s*([^;]+)', headerValue, re.IGNORECASE)
                    if match:
                        fileName = match.group(1)
                        fileName = decode_rfc2231(fileName)[2]  # fileName* 后的部分是编码信息

                # 如果 fileName* 没有成功获取，尝试处理普通的 fileName
                if not fileName and 'filename' in headerValue:
                    match = re.search(r'filename\s*=\s*["\']?([^"\';]+)["\']?', headerValue, re.IGNORECASE)
                    if match:
                        fileName = match.group(1)

                # 移除文件名头尾可能存在的引号并解码
                if fileName:
                    fileName = unquote(fileName)
                    fileName = fileName.strip('"\'')
                else:
                    raise KeyError

                logger.debug(f"方法1获取文件名成功, 文件名:{fileName}")
            except (KeyError, IndexError) as e:
                try:
                    logger.info(f"方法1获取文件名失败, KeyError or IndexError:{e}")
                    # 解析 URL
                    # 解析查询字符串
                    # 获取 response-content-disposition 参数
                    # 解码并分割 disposition
                    # 提取文件名
                    fileName = \
                        unquote(parse_qs(urlparse(url).query).get('response-content-disposition', [''])[0]).split(
                            "filename=")[-1]

                    # 移除文件名头尾可能存在的引号并解码
                    if fileName:
                        fileName = unquote(fileName)
                        fileName = fileName.strip('"\'')
                    else:
                        raise KeyError

                    logger.debug(f"方法2获取文件名成功, 文件名:{fileName}")

                except (KeyError, IndexError) as e:

                    logger.info(f"方法2获取文件名失败, KeyError or IndexError:{e}")
                    fileName = unquote(urlparse(url).path.split('/')[-1])

                    if fileName:  # 如果没有后缀名，则使用 content-type 作为后缀名
                        _ = fileName.split('.')
                        if len(_) == 1:
                            fileName += '.' + head["content-type"].split('/')[-1].split(';')[0]

                        logger.debug(f"方法3获取文件名成功, 文件名:{fileName}")
                    else:
                        logger.debug("方法3获取文件名失败, 文件名为空")
                        # 什么都 Get 不到的情况
                        logger.info(f"获取文件名失败, 错误:{e}")
                        content_type = head["content-type"].split('/')[-1].split(';')[0]
                        fileName = f"downloaded_file{int(time_ns())}.{content_type}"
                        logger.debug(f"方法4获取文件名成功, 文件名:{fileName}")

    return url, fileName, fileSize


def bringWindowToTop(window):
    window.show()
    if window.isMinimized():
        window.showNormal()
    # 激活窗口，使其显示在最前面
    window.activateWindow()
    window.raise_()


def addDownloadTask(url: str, fileName: str = None, filePath: str = None,
                    headers: dict = None, status:str = "working", preBlockNum: int= None, notCreateHistoryFile: bool = False, fileSize: int = -1):
    """ Global function to add download task """
    if not filePath:
        filePath = cfg.downloadFolder.value

    if not preBlockNum:
        preBlockNum = cfg.preBlockNum.value

    if not headers:
        headers = Headers

    signalBus.addTaskSignal.emit(url, fileName, filePath, headers, status, preBlockNum, notCreateHistoryFile, str(fileSize))

def showMessageBox(self, title: str, content: str, showYesButton=False, yesSlot=None):
    """ show message box """
    w = MessageBox(title, content, self)
    if not showYesButton:
        w.cancelButton.setText('关闭')
        w.yesButton.hide()
        w.buttonLayout.insertStretch(0, 1)

    if w.exec() and yesSlot is not None:
        yesSlot()


def isSparseSupported(filePath: Path) -> bool:
    """
    检查给定路径所在的文件系统是否支持稀疏文件。

    Args:
        filePath: 要检查的文件路径。

    Returns:
        如果支持稀疏文件则返回 True，否则返回 False。
    """
    try:
        # 如果文件/目录不存在，则检查其父目录的文件系统
        checkPath = filePath
        if not checkPath.exists():
            checkPath = filePath.parent
            # 确保父目录存在
            checkPath.mkdir(parents=True, exist_ok=True)

        if sys.platform == "win32":
            # NTFS, ReFS 支持稀疏文件。exFAT 不支持。
            supportedFileSystems = ('NTFS', 'ReFS')

            # 使用 pathlib.Path.anchor 获取驱动器根路径 (例如 'C:\\')
            rootPath = checkPath.anchor
            if not rootPath:
                logger.warning(f"无法确定路径 '{checkPath}' 的驱动器根目录。")
                return False

            volumeNameBuffer = ctypes.create_unicode_buffer(1024)
            fileSystemBuffer = ctypes.create_unicode_buffer(1024)

            # 调用 Windows API 获取卷信息
            success = ctypes.windll.kernel32.GetVolumeInformationW(
                ctypes.c_wchar_p(rootPath),          # 根路径
                volumeNameBuffer,                    # 卷名缓冲区
                ctypes.sizeof(volumeNameBuffer),     # 缓冲区大小
                None,                                # 序列号
                None,                                # 最大组件长度
                None,                                # 文件系统标志
                fileSystemBuffer,                    # 文件系统名称缓冲区
                ctypes.sizeof(fileSystemBuffer)      # 缓冲区大小
            )

            if not success:
                # 获取更详细的错误信息
                errorCode = ctypes.GetLastError()
                logger.warning(f"GetVolumeInformationW 失败，错误码: {errorCode}")
                return False

            return fileSystemBuffer.value in supportedFileSystems

        elif sys.platform == "linux":
            # 主流的 Linux 文件系统，如 ext3, ext4, xfs, btrfs, f2fs, zfs 都支持稀疏文件
            supportedFileSystems = ('ext3', 'ext4', 'xfs', 'btrfs', 'f2fs', 'zfs')

            statvfsResult = os.statvfs(checkPath)
            # f_basetype 在某些系统上可能不存在，作为备用
            fileSystemType = getattr(statvfsResult, 'f_basetype', '').decode('utf-8').rstrip('\x00')
            return fileSystemType in supportedFileSystems

        elif sys.platform == "darwin":  # macOS
            # APFS 和 HFS+ 支持稀疏文件
            supportedFileSystems = ('apfs', 'hfs')

            # 使用 'stat' 命令是获取文件系统类型的最可靠方法
            # 'stat -f %T /path' 直接输出文件系统类型字符串
            result = subprocess.run(
                ["stat", "-f", "%T", str(checkPath)],
                capture_output=True,
                text=True,
                check=True
            )
            fileSystemType = result.stdout.strip()
            return fileSystemType in supportedFileSystems

        # 对于其他未知操作系统，默认不支持
        return False
    except Exception as e:
        logger.warning(f"文件系统检测失败: {repr(e)}")
        return False

def createSparseFile(filePath: Path) -> bool:
    """
    创建一个支持稀疏写入的空文件。

    在 Windows 上，它会创建一个空文件并设置稀疏标志。
    在 Linux/macOS 上，它仅创建一个空文件，因为文件系统会自动处理稀疏性。

    Args:
        filePath: 要创建的稀疏文件的路径。

    Returns:
        如果创建成功则返回 True，否则返回 False。
    """
    if not isSparseSupported(filePath):
        logger.warning(f"文件系统不支持在 '{filePath}' 创建稀疏文件。")
        return False

    try:
        if sys.platform == "win32":
            # 1. 创建一个空文件
            filePath.touch()
            # 2. 使用 fsutil 将其标记为稀疏文件
            #    这使得系统知道可以为该文件分配稀疏空间
            result = subprocess.run(
                ["fsutil", "sparse", "setflag", str(filePath)],
                capture_output=True,
                text=True,
                check=True, # 如果命令返回非零退出码，则引发 CalledProcessError
                creationflags=subprocess.CREATE_NO_WINDOW # 不显示控制台窗口
            )
            # check=True 会处理错误，但为清晰起见保留检查
            if result.returncode != 0:
                raise RuntimeError(f"fsutil 失败: {result.stderr}")

        elif sys.platform in ("linux", "darwin"):
            # 在 Linux 和 macOS (APFS/HFS+) 上，文件系统本身支持稀疏文件。
            # 无需特殊标志或API调用来“创建”一个稀疏文件。
            # 只需创建一个普通空文件，后续通过 fseek/lseek 跳过大块区域并写入数据时，
            # 文件系统会自动创建“空洞”，从而形成稀疏文件。
            filePath.touch()

        else:
            # 对于其他系统，我们可能不知道如何操作，所以失败
            logger.error(f"不支持在操作系统 '{sys.platform}' 上创建稀疏文件。")
            return False

        return True
    except (OSError, subprocess.CalledProcessError, RuntimeError) as e:
        logger.error(f"在 '{filePath}' 创建稀疏文件失败: {repr(e)}")
        # 如果失败，尝试清理创建的文件
        if filePath.exists():
            try:
                filePath.unlink()
            except OSError as cleanup_error:
                logger.error(f"清理失败的文件 '{filePath}' 时出错: {cleanup_error}")
        return False
    