import importlib
import inspect
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from email.utils import decode_rfc2231
from functools import wraps
from time import sleep, localtime, time_ns
from urllib.parse import unquote, parse_qs, urlparse

import httpx
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication
from loguru import logger

from app.common.config import cfg
from app.common.plugin_base import PluginBase

plugins = []

# def isWin11():
#     return sys.platform == 'win32' and sys.getwindowsversion().build >= 22000

def loadPlugins(mainWindow, directory="{}/plugins".format(QApplication.applicationDirPath())):
    try:
        for filename in os.listdir(directory):
            if filename.endswith(".py"):
                module_name = filename[:-3]  # 去掉文件的 .py 后缀
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


def getProxy():
    # print(cfg.proxyServer.value)
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


def getLinkInfo(url:str, headers:dict, fileName:str="", verify:bool=False, proxy:str=getProxy(), followRedirects:bool=True) -> tuple:
    response = httpx.head(url, headers=headers, verify=verify, proxy=proxy, follow_redirects=followRedirects)
    response.raise_for_status()  # 如果状态码不是 2xx，抛出异常

    head = response.headers

    url = str(response.url)

    # 获取文件大小, 判断是否可以分块下载
    if "content-length" not in head:
        fileSize = 0
    else:
        fileSize = int(head["content-length"])

    # 获取文件名
    if not fileName:
        try:
            # 尝试处理 Content-Disposition 中的 fileName* (RFC 5987 格式)
            headerValue = head["content-disposition"]
            if 'fileName*' in headerValue:
                match = re.search(r'filename\*\s*=\s*([^;]+)', headerValue, re.IGNORECASE)
                if match:
                    fileName = match.group(1)
                    fileName = decode_rfc2231(fileName)[2] # fileName* 后的部分是编码信息

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

                if fileName:
                    logger.debug(f"方法3获取文件名成功, 文件名:{fileName}")
                else:
                    logger.debug("方法3获取文件名失败, 文件名为空")
                    # 什么都 Get 不到的情况
                    logger.info(f"获取文件名失败, 错误:{e}")
                    content_type = head["content-type"].split('/')[-1]
                    fileName = f"downloaded_file{int(time_ns())}.{content_type}"
                    logger.debug(f"方法4获取文件名成功, 文件名:{fileName}")

    return url, fileName, fileSize