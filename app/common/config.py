# coding:utf-8
import sys
from re import compile

from PySide6.QtCore import QDir, QRect
from qfluentwidgets import (QConfig, ConfigItem, OptionsConfigItem, BoolValidator,
                            OptionsValidator, RangeConfigItem, RangeValidator,
                            FolderValidator, ConfigValidator, ConfigSerializer)


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

class GeometryValidator(ConfigValidator):  # geometry 为程序的位置和大小, 保存为字符串 "x,y,w,h," 默认为 Default
    def validate(self, value: QRect) -> bool:
        if value == "Default":
            return True
        if type(value) == QRect:
            return True

    def correct(self, value) -> str:
        return value if self.validate(value) else "Default"

class GeometrySerializer(ConfigSerializer):  # 将字符串 "x,y,w,h," 转换为QRect (x, y, w, h), "Default" 除外
    def serialize(self, value: QRect) -> str:
        if value == "Default":
            return value
        return f"{value.x()},{value.y()},{value.width()},{value.height()}"

    def deserialize(self, value: str) -> QRect:
        if value == "Default":
            return value
        x, y, w, h = map(int, value.split(","))
        return QRect(x, y, w, h)

class Config(QConfig):
    """ Config of application """
    # download
    maxReassignSize = RangeConfigItem("Download", "MaxReassignSize", 8, RangeValidator(1, 100))
    downloadFolder = ConfigItem(
        "Download", "DownloadFolder", QDir.currentPath(), FolderValidator())

    maxBlockNum = RangeConfigItem("Download", "MaxBlockNum", 8, RangeValidator(1, 256))
    autoSpeedUp = ConfigItem("Download", "AutoSpeedUp", True, BoolValidator())
    proxyServer = ConfigItem("Download", "ProxyServer", "Auto", ProxyValidator())

    # browser
    enableBrowserExtension = ConfigItem("Browser", "EnableBrowserExtension", False, BoolValidator())

    # personalization
    if sys.platform == "win32":
        # backgroundEffect = OptionsConfigItem("Personalization", "BackgroundEffect", "Mica", OptionsValidator(["Acrylic", "Mica", "MicaBlur", "MicaAlt", "Transparent", "Aero", "None"]))
        backgroundEffect = OptionsConfigItem("Personalization", "BackgroundEffect", "Mica", OptionsValidator(["Acrylic", "Mica", "MicaBlur", "MicaAlt", "Aero"]))
    dpiScale = OptionsConfigItem(
        "Personalization", "DpiScale", "Auto", OptionsValidator([1, 1.25, 1.5, 1.75, 2, "Auto"]), restart=True)

    # software
    checkUpdateAtStartUp = ConfigItem("Software", "CheckUpdateAtStartUp", True, BoolValidator())
    autoRun = ConfigItem("Software", "AutoRun", False, BoolValidator())
    geometry = ConfigItem("Software", "Geometry", "Default", GeometryValidator(), GeometrySerializer())  # 保存程序的位置和大小, Validator 在 mainWindow 中设置
    # 程序运行路径
    appPath = "./"


YEAR = 2024
AUTHOR = "XiaoYouChR"
VERSION = "3.4.5"
LATEST_EXTENSION_VERSION = "1.0.4"
AUTHOR_URL = "https://space.bilibili.com/437313511"
FEEDBACK_URL = "https://github.com/XiaoYouChR/Ghost-Downloader-3/issues"
# RELEASE_URL = "https://github.com/XiaoYouChR/Ghost-Downloader-3/releases/latest"


cfg = Config()
