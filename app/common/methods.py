import importlib
import inspect
import os
import sys

from PySide6.QtWidgets import QApplication
from loguru import logger

from app.common.plugin_base import PluginBase

currentpath=os.path.dirname(sys.argv[0]).replace("/Contents/MacOS","/Contents")

plugins = []

# def isWin11():
#     return sys.platform == 'win32' and sys.getwindowsversion().build >= 22000

def loadPlugins(mainWindow, directory="{}/plugins".format(currentpath)):
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


def getWindowsProxy():
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
    else:  # 读取 Linux 系统代理
        try:
            return os.environ.get("http_proxy")
        except Exception as e:
            logger.error(f"Cannot get Linux proxy server：{e}")
            return None


def getReadableSize(size):
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    unit_index = 0
    K = 1024.0
    while size >= K:
        size = size / K
        unit_index += 1
    return "%.2f %s" % (size, units[unit_index])
