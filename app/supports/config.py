import sys
from asyncio import sleep
from enum import Enum
from re import compile

from PySide6.QtCore import QRect, QStandardPaths, QLocale, QOperatingSystemVersion
from orjson import dumps, loads
from qfluentwidgets import (
    QConfig,
    ConfigItem,
    OptionsConfigItem,
    BoolValidator,
    OptionsValidator,
    RangeConfigItem,
    RangeValidator,
    FolderValidator,
    ConfigValidator,
    ConfigSerializer,
    FolderListValidator,
)

DEFAULT_HEADERS = {
    "accept-encoding": "deflate, br, gzip",
    "accept-language": "zh-CN,zh;q=0.9",
    "cookie": "down_ip=1",
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "none",
    "sec-fetch-user": "?1",
    "upgrade-insecure-requests": "1",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36 Edg/144.0.0.0",
}


def isGreaterEqualWin10():
    cv = QOperatingSystemVersion.current()
    return sys.platform == "win32" and cv.majorVersion() >= 10


def isWin10():
    return isGreaterEqualWin10() and sys.getwindowsversion().build < 22000


def isLessThanWin10():
    cv = QOperatingSystemVersion.current()
    return sys.platform == "win32" and cv.majorVersion() < 10


def isGreaterEqualWin11():
    """determine if the Windows version ≥ Win11"""
    return isGreaterEqualWin10() and sys.getwindowsversion().build >= 22000


class Language(Enum):
    """Language enumeration"""

    CHINESE_SIMPLIFIED = QLocale(QLocale.Language.Chinese, QLocale.Country.China)
    CHINESE_TRADITIONAL = QLocale(QLocale.Language.Chinese, QLocale.Country.Taiwan)
    CANTONESE = QLocale(QLocale.Language.Cantonese, QLocale.Country.HongKong)
    # CHINESE_LITERARY = QLocale(
    #     QLocale.Language.Chinese, QLocale.Country.Macau
    # )  # lzh is invalid.
    ENGLISH_UNITED_STATES = QLocale(
        QLocale.Language.English, QLocale.Country.UnitedStates
    )
    JAPANESE = QLocale(QLocale.Language.Japanese, QLocale.Country.Japan)
    RUSSIAN = QLocale(QLocale.Language.Russian, QLocale.Country.Russia)
    AUTO = QLocale()


class ProxyValidator(ConfigValidator):
    PATTERN = compile(
        r"^"
        r"(?P<protocol>http|https|socks4|socks5)://"  # 1. 协议
        r"(?:(?P<user>\w+):(?P<password>[\w!@#$%^&*()]+)@)?"  # 2. 认证 (可选)
        r"(?:"
        r"(?P<ip>(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?))|"  # 3. IP
        r"(?P<domain>(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,6})"  # 4. 域名
        r")"
        r":(?P<port>\d{1,5})"  # 5. 端口
        r"$"
    )

    def validate(self, value: str) -> bool:
        return bool(self.PATTERN.match(value)) or value == "Auto" or value == "Off"

    def correct(self, value) -> str:
        return value if self.validate(value) else "Auto"


class GeometryValidator(ConfigValidator):
    def validate(self, value: QRect) -> bool:
        """由于 QScreen 必须在 QApplication 初始化之后调用, 所以由 MainWindow 处理特殊情况"""
        x, y, w, h = value.x(), value.y(), value.width(), value.height()
        if x < 0 or y < 0 or w < 0 or h < 0:
            return False
        return True

    def correct(self, value) -> QRect:
        return value if self.validate(value) else QRect(0, 0, 0, 0)


class GeometrySerializer(ConfigSerializer):
    def serialize(self, value: QRect) -> str:
        """保存为字符串 "x,y,w,h"."""
        x, y, w, h = value.x(), value.y(), value.width(), value.height()
        return f"{x},{y},{w},{h}"

    def deserialize(self, value: str) -> QRect:
        """将字符串 "x,y,w,h" 转换为 QRect (x, y, w, h)"""
        x, y, w, h = map(int, value.split(","))
        return QRect(x, y, w, h)


class LanguageSerializer(ConfigSerializer):
    def serialize(self, language):
        return language.value.name() if language != Language.AUTO else "Auto"

    def deserialize(self, value: str):
        return Language(QLocale(value)) if value != "Auto" else Language.AUTO


class HeadersValidator(ConfigValidator):
    """Headers 验证器"""

    def validate(self, value: dict) -> bool:
        """验证 Headers 是否为非空字典类型"""
        return isinstance(value, dict) and len(value) > 0

    def correct(self, value) -> dict:
        """如果验证失败，返回默认的 Headers"""
        return value if self.validate(value) else DEFAULT_HEADERS


class HeadersSerializer(ConfigSerializer):
    """Headers 序列化器"""

    def serialize(self, value: dict) -> str:
        """将字典序列化为 JSON 字符串"""
        return dumps(value).decode("utf-8")

    def deserialize(self, value: str) -> dict:
        """将 JSON 字符串反序列化为字典，如果失败则返回默认值"""
        try:
            result = loads(value)
            return (
                result
                if isinstance(result, dict) and len(result) > 0
                else DEFAULT_HEADERS
            )
        except (ValueError, TypeError):
            return DEFAULT_HEADERS


class Config(QConfig):

    # 总下载设置
    downloadFolder = ConfigItem(
        "GeneralDownload",
        "DownloadFolder",
        QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.DownloadLocation
        ),
        FolderValidator(),
    )
    memoryDownloadFolders = ConfigItem(
        "GeneralDownload", "HistoryDownloadFolder", [], FolderListValidator()
    )
    maxTaskNum = RangeConfigItem(
        "GeneralDownload", "MaxTaskNum", 3, RangeValidator(1, 10)
    )
    enableSpeedLimitation = ConfigItem("GeneralDownload", "enableSpeedLimitation", False, BoolValidator())
    speedLimitation = RangeConfigItem(
        "GeneralDownload", "SpeedLimitation", 4194304, RangeValidator(1024, 104857600)
    )  # 单位 B/s
    SSLVerify = ConfigItem(
        "GeneralDownload", "SSLVerify", False, BoolValidator(), restart=True
    )
    proxyServer = ConfigItem("GeneralDownload", "ProxyServer", "Auto", ProxyValidator())
    preBlockNum = RangeConfigItem("GeneralDownload", "PreBlockNum", 8, RangeValidator(1, 256))
    autoSpeedUp = ConfigItem("GeneralDownload", "AutoSpeedUp", True, BoolValidator())
    maxReassignSize = RangeConfigItem(
        "GeneralDownload", "MaxReassignSize", 3, RangeValidator(1, 100)
    )

    # 浏览器插件设置
    enableBrowserExtension = ConfigItem(
        "Browser", "EnableBrowserExtension", False, BoolValidator()
    )
    browserExtensionPairToken = ConfigItem(
        "Browser", "BrowserExtensionPairToken", ""
    )
    enableRaiseWindowWhenReceiveMsg = ConfigItem(
        "Browser", "EnableRaiseWindowWhenReceiveMsg", False, BoolValidator()
    )

    # 个性化设置
    if sys.platform == "win32":
        backgroundEffect = OptionsConfigItem(
            "Personalization",
            "BackgroundEffect",
            "Acrylic" if isWin10() else "Mica",
            OptionsValidator(
                ["Acrylic", "Mica", "MicaAlt", "Aero", "None"]
            ),
        )
    customThemeMode = OptionsConfigItem(
        "Personalization",
        "ThemeMode",
        "System",
        OptionsValidator(["Light", "Dark", "System"]),
    )
    dpiScale = RangeConfigItem(
        "Personalization", "DpiScale", 0, RangeValidator(0, 5), restart=True
    )
    language = OptionsConfigItem(
        "Personalization",
        "Language",
        Language.AUTO,
        OptionsValidator(Language),
        LanguageSerializer(),
        restart=True,
    )

    # 软件设置
    checkUpdateAtStartUp = ConfigItem(
        "Software", "CheckUpdateAtStartUp", True, BoolValidator()
    )
    autoRun = ConfigItem("Software", "AutoRun", False, BoolValidator())
    enableClipboardListener = ConfigItem(
        "Software", "ClipboardListener", True, BoolValidator()
    )
    geometry = ConfigItem(
        "Software",
        "Geometry",
        QRect(0, 0, 0, 0),
        GeometryValidator(),
        GeometrySerializer(),
    )  # 由于 QScreen 必须在 QApplication 初始化之后调用, 所以由 MainWindow 处理特殊情况

    # 网络设置
    # headers = ConfigItem(
    #     "Network",
    #     "Headers",
    #     DEFAULT_HEADERS,
    #     HeadersValidator(),
    #     HeadersSerializer(),
    # )

    # 全局变量
    globalSpeed = 0  # 用于记录每秒下载速度, 单位 KB/s

    def resetGlobalSpeed(self):
        self.globalSpeed = 0

    async def checkSpeedLimitation(self):
        if self.enableSpeedLimitation.value:
            while self.globalSpeed > self.speedLimitation.value:
                await sleep(0.1)


YEAR = 2026
AUTHOR = "XiaoYouChR"
VERSION = "3.7.4"
LATEST_EXTENSION_VERSION = "1.1.1"
AUTHOR_URL = "https://space.bilibili.com/437313511"
FEEDBACK_URL = "https://github.com/XiaoYouChR/Ghost-Downloader-3/issues"
FIREFOX_ADDONS_URL = "https://addons.mozilla.org/zh-CN/firefox/addon/ghost-downloader/"
EDGE_ADDONS_URL = "https://microsoftedge.microsoft.com/addons/detail/ghost-downloader-browser/odaohmfjjbompdkmfbambadnagplcmce"
CHROME_ADDONS_URL = "https://chromewebstore.google.com/detail/ghost-downloader-browser/pinckpkeeajogfgajbicpnengimiblch"
GD3_COPY_MIME_TYPE = "application/x-gd3-copy"
# RELEASE_URL = "https://github.com/XiaoYouChR/Ghost-Downloader-3/releases/latest"
# BASE_EFFICIENCY_THRESHOLD = 0.8  # 判断阈值

# TODO 自定义附件捕捉类型
attachmentTypes = """3gp 7z aac ace aif arj asf avi bin bz2 dmg exe gz gzip img iso lzh m4a m4v mkv mov mp3 mp4 mpa mpe
                                 mpeg mpg msi msu ogg ogv pdf plj pps ppt qt ra rar rm rmvb sea sit sitx tar tif tiff
                                 wav wma wmv z zip esd wim msp apk apks apkm cab msp pkg"""

cfg = Config()
