# coding:utf-8

from re import compile

from PySide6.QtCore import QDir
from qfluentwidgets import (QConfig, ConfigItem, OptionsConfigItem, BoolValidator,
                            OptionsValidator, RangeConfigItem, RangeValidator,
                            FolderValidator, ConfigValidator)


class ProxyValidator(ConfigValidator):

    PATTERN = compile(r'^(socks5|http|https):\/\/'
                      r'((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}'
                      r'(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?):'
                      r'(6553[0-5]|655[0-2][0-9]|65[0-4][0-9]{2}|[1-5]?[0-9]{1,4})$')

    def validate(self, value: str) -> bool:
        # 判断代理地址是否合法
        # print(value, self.PATTERN.match(value))
        return bool(self.PATTERN.match(value)) or value == "Auto" or value == "Off"

    def correct(self, value) -> str:
        return value if self.validate(value) else "Auto"

class Config(QConfig):
    """ Config of application """
    # download
    maxReassignSize = RangeConfigItem("Download", "MaxReassignSize", 15, RangeValidator(1, 100))
    downloadFolder = ConfigItem(
        "Download", "DownloadFolder", QDir.currentPath(), FolderValidator())

    maxBlockNum = RangeConfigItem("Download", "MaxBlockNum", 32, RangeValidator(1, 256))
    proxyServer = ConfigItem("Download", "ProxyServer", "Auto", ProxyValidator())

    # browser
    enableBrowserExtension = ConfigItem("Browser", "EnableBrowserExtension", False, BoolValidator())

    # personalization
    # backgroundEffect = OptionsConfigItem("Personalization", "BackgroundEffect", "Mica", OptionsValidator(["Acrylic", "Mica", "MicaBlur", "MicaAlt", "Transparent", "Aero", "None"]))
    backgroundEffect = OptionsConfigItem("Personalization", "BackgroundEffect", "Mica", OptionsValidator(["Acrylic", "Mica", "MicaBlur", "MicaAlt", "Aero"]))
    dpiScale = OptionsConfigItem(
        "Personalization", "DpiScale", "Auto", OptionsValidator([1, 1.25, 1.5, 1.75, 2, "Auto"]), restart=True)

    # software
    checkUpdateAtStartUp = ConfigItem("Software", "CheckUpdateAtStartUp", True, BoolValidator())
    autoRun = ConfigItem("Software", "AutoRun", False, BoolValidator())

    # 程序运行路径
    appPath = "./"


YEAR = 2024
AUTHOR = "XiaoYouChR"
VERSION = "3.4.0"
AUTHOR_URL = "https://space.bilibili.com/437313511"
FEEDBACK_URL = "https://github.com/XiaoYouChR/Ghost-Downloader-3/issues"
# RELEASE_URL = "https://github.com/XiaoYouChR/Ghost-Downloader-3/releases/latest"


cfg = Config()
