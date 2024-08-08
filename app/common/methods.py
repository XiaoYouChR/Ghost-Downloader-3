import importlib
import inspect
import os
import winreg

from loguru import logger

from app.common.plugin_base import PluginBase

def loadPlugins(mainWindow, directory="./plugins"):
    plugins = []

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
                    # 实例化插件并调用 load 方法
                    plugin_instance = obj(mainWindow)
                    plugin_instance.load()
                    plugins.append(plugin_instance)

    return plugins

def getWindowsProxy():
    try:
        # 打开 Windows 注册表项
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r'Software\Microsoft\Windows\CurrentVersion\Internet Settings')

        # 获取代理开关状态
        proxy_enable, _ = winreg.QueryValueEx(key, 'ProxyEnable')

        if proxy_enable:
            # 获取代理地址和端口号
            proxy_server, _ = winreg.QueryValueEx(key, 'ProxyServer')
            return {
                "http": proxy_server,
                "https": proxy_server,
            }
        else:
            return {
                "http": None,
                "https": None,
            }

    except Exception as e:
        logger.error(f"Cannot get Windows proxy server：{e}")
        return {
            "http": None,
            "https": None,
        }


def getReadableSize(size):
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    unit_index = 0
    K = 1024.0
    while size >= K:
        size = size / K
        unit_index += 1
    return "%.2f %s" % (size, units[unit_index])
