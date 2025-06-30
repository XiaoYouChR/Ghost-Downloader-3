# coding:utf-8
import sys
from enum import Enum
from re import compile, VERBOSE, IGNORECASE
from typing import Literal

from PySide6.QtCore import QRect, QStandardPaths, QLocale
from PySide6.QtWidgets import QApplication
from qfluentwidgets import (QConfig, ConfigItem, OptionsConfigItem, BoolValidator,
                            OptionsValidator, RangeConfigItem, RangeValidator,
                            FolderValidator, ConfigValidator, ConfigSerializer, FolderListValidator, ColorValidator,
                            ColorSerializer)


class Language(Enum):
    """ Language enumeration """

    CHINESE_SIMPLIFIED = QLocale(QLocale.Language.Chinese, QLocale.Country.China)
    CHINESE_TRADITIONAL = QLocale(QLocale.Language.Chinese, QLocale.Country.Taiwan)
    CHINESE_LITERARY = QLocale(QLocale.Language.Chinese, QLocale.Country.Macau)  # lzh is invalid, I don't know what to do, sorry
    ENGLISH_UNITED_STATES = QLocale(QLocale.Language.English, QLocale.Country.UnitedStates)
    JAPANESE = QLocale(QLocale.Language.Japanese, QLocale.Country.Japan)
    AUTO = QLocale()

class ProxyValidator(ConfigValidator):
    PATTERN = compile(
        r"""
        ^                                       # 字符串开始
        (?P<protocol>socks5|http|https)://      # 协议头 (http, https, socks5)
        (?:                                     # 认证信息组 (可选)
            (?P<user>[^:@\s/]+)                 # 用户名 (不能包含 : @ / 或空白)
            (?::(?P<password>[^@\s/]*))?        # 密码 (可选, 不能包含 @ / 或空白)
            @
        )?
        (?P<host>                               # 主机地址组
            localhost|                          # 本地主机
            # IP 地址 v4
            (?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)|
            # 域名
            (?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,6}
        )
        :                                       # 端口分隔符
        (?P<port>                               # 端口号组 (1-65535)
            [1-9][0-9]{0,3}|                    # 1-9999
            [1-5][0-9]{4}|                      # 10000-59999
            6[0-4][0-9]{3}|                     # 60000-64999
            65[0-4][0-9]{2}|                    # 65000-65499
            655[0-2][0-9]|                      # 65500-65529
            6553[0-5]                           # 65530-65535
        )
        /?                                      # 可选的末尾斜杠
        $                                       # 字符串结束
        """,
        VERBOSE | IGNORECASE
    )

    def validate(self, value: str) -> bool: # type: ignore
        """判断代理地址是否合法"""
        return bool(self.PATTERN.match(value)) or value == "Auto" or value == "Off"

    def correct(self, value) -> str:
        return value if self.validate(value) else "Auto"


class GeometryValidator(ConfigValidator):  # geometry 为程序的位置和大小, 保存为字符串 "x,y,w,h," 默认为 Default
    def validate(self, value: QRect) -> bool:  # type: ignore
        if value == "Default":
            return True
        if isinstance(value, QRect):
            screen = QApplication.primaryScreen()
            if not screen:
                return False
            if not screen.availableGeometry().contains(value):
                return False
            return True

        return False

    def correct(self, value) -> str:
        return value if self.validate(value) else "Default"


class GeometrySerializer(ConfigSerializer):  # 将字符串 "x,y,w,h," 转换为QRect (x, y, w, h), "Default" 除外
    def serialize(self, value: QRect) -> str:
        if value == "Default":
            return "Default"
        return f"{value.x()},{value.y()},{value.width()},{value.height()}"

    def deserialize(self, value: str) -> Literal["Default"] | QRect:
        if value == "Default":
            return value
        x, y, w, h = map(int, value.split(","))
        return QRect(x, y, w, h)

class LanguageSerializer(ConfigSerializer):
    """ Language serializer """

    def serialize(self, language):  # type: ignore
        return language.value.name() if language != Language.AUTO else "Auto"

    def deserialize(self, value: str):
        return Language(QLocale(value)) if value != "Auto" else Language.AUTO

class Config(QConfig):
    """ Config of application """
    # download
    maxReassignSize = RangeConfigItem("Download", "MaxReassignSize", 8, RangeValidator(1, 100))
    downloadFolder = ConfigItem(
        "Download", "DownloadFolder", QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation), FolderValidator())
    historyDownloadFolder = ConfigItem("Download", "HistoryDownloadFolder", [], FolderListValidator())

    preBlockNum = RangeConfigItem("Download", "PreBlockNum", 8, RangeValidator(1, 256))
    maxTaskNum = RangeConfigItem("Download", "MaxTaskNum", 3, RangeValidator(1, 10))
    speedLimitation = RangeConfigItem("Download", "SpeedLimitation", 0, RangeValidator(0, 104857600))  # 单位 KB
    autoSpeedUp = ConfigItem("Download", "AutoSpeedUp", True, BoolValidator())
    SSLVerify = ConfigItem("Download", "SSLVerify", True, BoolValidator(), restart=True)
    proxyServer = ConfigItem("Download", "ProxyServer", "Auto", ProxyValidator())

    # browser
    enableBrowserExtension = ConfigItem("Browser", "EnableBrowserExtension", False, BoolValidator())
    enableRaiseWindowWhenReceiveMsg = ConfigItem("Browser", "EnableRaiseWindowWhenReceiveMsg", False, BoolValidator())

    # personalization
    if sys.platform == "win32":
        backgroundEffect = OptionsConfigItem("Personalization", "BackgroundEffect", "Mica", OptionsValidator(
            ["Acrylic", "Mica", "MicaBlur", "MicaAlt", "Aero", "None"]))
    customThemeMode = OptionsConfigItem("Personalization", "ThemeMode", "System",
                                        OptionsValidator(["Light", "Dark", "System"]))
    isColorDependsOnSystem = ConfigItem("Personalization", "IsColorDependsOnSystem", True, BoolValidator())
    appColor = ConfigItem("Personalization", "AppColor", "#0078D4FF", ColorValidator("#0078D4FF"), ColorSerializer())
    dpiScale = RangeConfigItem(
        "Personalization", "DpiScale", 0, RangeValidator(0, 5), restart=True)
    language = OptionsConfigItem(
        "MainWindow", "Language", Language.AUTO, OptionsValidator(Language), LanguageSerializer(), restart=True)

    # software
    checkUpdateAtStartUp = ConfigItem("Software", "CheckUpdateAtStartUp", True, BoolValidator())
    autoRun = ConfigItem("Software", "AutoRun", False, BoolValidator())
    enableClipboardListener = ConfigItem("Software", "ClipboardListener", True, BoolValidator())
    geometry = ConfigItem("Software", "Geometry", "Default", GeometryValidator(),
                          GeometrySerializer())  # 保存程序的位置和大小, Validator 在 mainWindow 中设置

    # 全局变量
    appPath = "./"


YEAR = 2025
AUTHOR = "XiaoYouChR"
VERSION = "3.6"
LATEST_EXTENSION_VERSION = "2.0"
AUTHOR_URL = "https://space.bilibili.com/437313511"
FEEDBACK_URL = "https://github.com/XiaoYouChR/Ghost-Downloader-3/issues"
FIREFOX_ADDONS_URL = "https://addons.mozilla.org/zh-CN/firefox/addon/ghost-downloader/"
# RELEASE_URL = "https://github.com/XiaoYouChR/Ghost-Downloader-3/releases/latest"
BASE_UTILIZATION_THRESHOLD = 0.1 # 判断阈值
TIME_WEIGHT_FACTOR = 1  # 判断精度

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

cfg = Config()
