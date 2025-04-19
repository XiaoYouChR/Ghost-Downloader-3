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
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication
from loguru import logger
from qfluentwidgets import MessageBox

from app.common.config import cfg, Headers
from app.common.plugin_base import PluginBase
from app.common.signal_bus import signalBus

plugins = []

def isAbleToShowToast():
    return sys.platform == 'win32' and sys.getwindowsversion().build >= 16299  # 高于 Win10 1709

def loadPlugins(mainWindow, directory="{}/plugins".format(QApplication.applicationDirPath())):
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
    print(cfg.proxyServer.value)
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
            fileSize = int(head["content-length"])
        else:
            fileSize = 0

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
    """检查文件系统是否支持稀疏文件"""
    try:
        if sys.platform == "win32":
            # 获取驱动器根路径（如 C:\）
            root_path = str(filePath.drive + '\\').encode('utf-16le')

            # 定义Windows API参数类型
            volume_name_buffer = ctypes.create_unicode_buffer(1024)
            file_system_buffer = ctypes.create_unicode_buffer(1024)

            # 调用Windows API获取卷信息
            success = ctypes.windll.kernel32.GetVolumeInformationW(
                ctypes.c_wchar_p(root_path.decode('utf-16le')),  # 根路径
                volume_name_buffer,                             # 卷名缓冲区
                ctypes.sizeof(volume_name_buffer),              # 缓冲区大小
                None,                                           # 序列号
                None,                                           # 最大组件长度
                None,                                           # 文件系统标志
                file_system_buffer,                             # 文件系统名称缓冲区
                ctypes.sizeof(file_system_buffer)               # 缓冲区大小
            )

            return success and file_system_buffer.value in ('exFAT', 'NTFS', 'ReFS')
        elif sys.platform == "linux":
            fs_type = os.statvfs(filePath).f_basetype
            return fs_type in ('ext4', 'xfs', 'btrfs', 'zfs')
        elif sys.platform == "darwin":  # macOS
            df_output = subprocess.check_output(
                ["df", "-h", filePath],
                stderr=subprocess.STDOUT,
                universal_newlines=True
            ).splitlines()

            # 提取设备节点 (第二行第二列)
            if len(df_output) < 2:
                return False
            device_node = df_output[1].split()[0]

            # 获取挂载信息
            mount_output = subprocess.check_output(
                ["mount"],
                universal_newlines=True
            )

            # 解析文件系统类型
            for line in mount_output.splitlines():
                if line.startswith(device_node):
                    parts = line.split()
                    for part in parts:
                        if part.startswith("(") and "," in part:
                            return part.strip("(),").split(",")[0] in ('apfs', 'hfs')
        return False
    except Exception as e:
        logger.warning(f"文件系统检测失败: {repr(e)}")
        return False

def createSparseFile(filePath: Path) -> bool:
    """创建稀疏文件的统一入口"""
    if not isSparseSupported(filePath):
        return False

    try:
        if sys.platform == "win32":
            try:
                # 创建空文件
                filePath.touch()
                # 设置稀疏属性
                result = subprocess.run(
                    ["fsutil", "sparse", "setflag", str(filePath)],
                    capture_output=True,
                    text=True,
                    check=True
                )
                if result.returncode != 0:
                    raise RuntimeError(f"fsutil失败: {result.stderr}")
            except subprocess.CalledProcessError as e:
                raise OSError(f"Windows 稀疏文件创建失败: {e.stderr}")
        elif sys.platform == "linux":
            try:
                # 使用fallocate快速创建稀疏文件
                with open(filePath, 'ab') as f:
                    os.truncate(f.fileno(), 0)
            except OSError as e:
                raise OSError(f"Linux 稀疏文件创建失败: {repr(e)}")
        elif sys.platform == "darwin":
            try:
                # APFS原生支持稀疏文件
                with open(filePath, 'w') as f:
                    os.ftruncate(f.fileno(), 0)
            except OSError as e:
                raise OSError(f"macOS 稀疏文件创建失败: {repr(e)}")
        return True
    except Exception as e:
        logger.error(f"创建稀疏文件失败: {repr(e)}")
        return False
