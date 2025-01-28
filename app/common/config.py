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

    preBlockNum = RangeConfigItem("Download", "PreBlockNum", 8, RangeValidator(1, 256))
    maxTaskNum = RangeConfigItem("Download", "MaxTaskNum", 3, RangeValidator(1, 10))
    speedLimitation = RangeConfigItem("Download", "SpeedLimitation", 0, RangeValidator(0, 104857600))  # 单位 KB
    autoSpeedUp = ConfigItem("Download", "AutoSpeedUp", True, BoolValidator())
    proxyServer = ConfigItem("Download", "ProxyServer", "Auto", ProxyValidator())

    # browser
    enableBrowserExtension = ConfigItem("Browser", "EnableBrowserExtension", False, BoolValidator())

    # personalization
    if sys.platform == "win32":
        backgroundEffect = OptionsConfigItem("Personalization", "BackgroundEffect", "Mica", OptionsValidator(["Acrylic", "Mica", "MicaBlur", "MicaAlt", "Aero", "None"]))
    customThemeMode = OptionsConfigItem("Personalization", "ThemeMode", "System", OptionsValidator(["Light", "Dark", "System"]))
    dpiScale = RangeConfigItem(
        "Personalization", "DpiScale", 0, RangeValidator(0, 5), restart=True)

    # software
    checkUpdateAtStartUp = ConfigItem("Software", "CheckUpdateAtStartUp", True, BoolValidator())
    autoRun = ConfigItem("Software", "AutoRun", False, BoolValidator())
    enableClipboardListener = ConfigItem("Software", "ClipboardListener", True, BoolValidator())
    geometry = ConfigItem("Software", "Geometry", "Default", GeometryValidator(), GeometrySerializer())  # 保存程序的位置和大小, Validator 在 mainWindow 中设置

    # 全局变量
    appPath = "./"
    globalSpeed = 0  # 用于记录每秒下载速度, 单位 KB/s

    def resetGlobalSpeed(self):
        self.globalSpeed = 0

YEAR = 2024
AUTHOR = "XiaoYouChR"
VERSION = "3.5.0"
LATEST_EXTENSION_VERSION = "1.1.0"
AUTHOR_URL = "https://space.bilibili.com/437313511"
FEEDBACK_URL = "https://github.com/XiaoYouChR/Ghost-Downloader-3/issues"
FIREFOX_ADDONS_URL = "https://addons.mozilla.org/zh-CN/firefox/addon/ghost-downloader/"
# RELEASE_URL = "https://github.com/XiaoYouChR/Ghost-Downloader-3/releases/latest"

Headers = {
    "accept-encoding": "deflate, br, gzip",
    "accept-language": "zh-CN,zh;q=0.9",
    "cookie": "down_ip=1",
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "none",
    "sec-fetch-user": "?1",
    "upgrade-insecure-requests": "1",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36 Edg/112.0.1722.64"}

# 附件类型必须全部小写
attachmentTypes = """3gp 7z aac ace aif arj asf avi bin bz2 dmg exe gz gzip img iso lzh m4a m4v mkv mov mp3 mp4 mpa mpe
                                 mpeg mpg msi msu ogg ogv pdf plj pps ppt qt ra rar rm rmvb sea sit sitx tar tif tiff
                                 wav wma wmv z zip esd wim msp apk apks apkm cab msp"""

cfg = Config()
