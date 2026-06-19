import sys
from asyncio import sleep
from enum import Enum
from re import compile
from typing import Callable

from PySide6.QtCore import QRect, QStandardPaths, QLocale, QOperatingSystemVersion
from orjson import dumps, loads

from app.supports.android import IS_ANDROID
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
    Theme,
)

_BASE_HEADERS = {
    "accept-encoding": "deflate, br, gzip",
    "accept-language": "zh-CN,zh;q=0.9",
    "cookie": "down_ip=1",
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "none",
    "sec-fetch-user": "?1",
    "upgrade-insecure-requests": "1",
}

def factoryHeaders() -> dict[str, str]:
    return dict(_BASE_HEADERS)


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


class StringListValidator(ConfigValidator):
    """字符串列表验证器"""

    def validate(self, value) -> bool:
        return isinstance(value, list) and all(isinstance(i, str) for i in value)

    def correct(self, value) -> list:
        if not isinstance(value, list):
            return []
        return [i for i in value if isinstance(i, str)]


class CategoryListValidator(ConfigValidator):
    """下载分类规则列表验证器"""

    def validate(self, value) -> bool:
        if not isinstance(value, list):
            return False
        return all(
            isinstance(item, dict) and isinstance(item.get("name"), str)
            for item in value
        )

    def correct(self, value) -> list:
        return value if self.validate(value) else []


class JsonConfigSerializer(ConfigSerializer):
    def __init__(self, expected: type, fallback: Callable[[], object]) -> None:
        self._expected = expected
        self._fallback = fallback

    def serialize(self, value) -> str:
        return dumps(value).decode("utf-8")

    def deserialize(self, value: str):
        try:
            result = loads(value)
            return result if isinstance(result, self._expected) else self._fallback()
        except (ValueError, TypeError):
            return self._fallback()


class ClientProfileValidator(ConfigValidator):
    def validate(self, value) -> bool:
        return isinstance(value, str) and bool(value)

    def correct(self, value) -> str:
        return value if self.validate(value) else "auto"


class HeadersValidator(ConfigValidator):
    def validate(self, value) -> bool:
        return isinstance(value, dict) and bool(value) and all(
            isinstance(name, str) and isinstance(text, str) for name, text in value.items()
        )

    def correct(self, value) -> dict:
        return value if self.validate(value) else factoryHeaders()


def toQFluentTheme(value: str) -> Theme:
    return {
        "Dark": Theme.DARK,
        "Light": Theme.LIGHT,
    }.get(value, Theme.AUTO)


class Config(QConfig):

    # 总下载设置
    downloadFolder = ConfigItem(
        "GeneralDownload",
        "DownloadFolder",
        # Android 落公共 Downloads(文件管理器可见); 桌面默认目录在 Android 是用户不可见的作用域目录
        "/storage/emulated/0/Download"
        if IS_ANDROID
        else QStandardPaths.writableLocation(
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

    # 下载分类
    enableCategory = ConfigItem(
        "Category", "EnableCategory", False, BoolValidator()
    )
    categoryRules = ConfigItem(
        "Category",
        "CategoryRules",
        [],
        CategoryListValidator(),
        JsonConfigSerializer(list, list),
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
    showDockIcon = ConfigItem("Personalization", "ShowDockIcon", True, BoolValidator())
    showDockSpeed = ConfigItem("Personalization", "ShowDockSpeed", True, BoolValidator())
    showMenuBarSpeed = ConfigItem("Personalization", "ShowMenuBarSpeed", True, BoolValidator())
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
        serializer=GeometrySerializer(),
    )  # 配置层够不到 QScreen，位置可用性留给 MainWindow 首次 show 时判定，这里只管序列化

    # 设置页 UI 状态
    collapsedSettingGroups = ConfigItem(
        "UI", "CollapsedSettingGroups", [], StringListValidator()
    )
    settingGroupOrder = ConfigItem(
        "UI", "SettingGroupOrder", [], StringListValidator()
    )

    # 网络设置
    clientProfile = ConfigItem(
        "Network", "ClientProfile", "auto", ClientProfileValidator()
    )
    defaultRequestHeaders = ConfigItem(
        "Network",
        "DefaultHeaders",
        factoryHeaders(),
        HeadersValidator(),
        JsonConfigSerializer(dict, factoryHeaders),
    )

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
VERSION = "3.10.4"
DESKTOP_ID = "io.github.xiaoyouchr.GhostDownloader"
DESKTOP_OBJECT_PATH = "/" + DESKTOP_ID.replace(".", "/")
LATEST_EXTENSION_VERSION = "1.4.0"
AUTHOR_URL = "https://space.bilibili.com/437313511"
FEEDBACK_URL = "https://github.com/XiaoYouChR/Ghost-Downloader-3/issues"
FIREFOX_ADDONS_URL = "https://addons.mozilla.org/zh-CN/firefox/addon/ghost-downloader/"
EDGE_ADDONS_URL = "https://microsoftedge.microsoft.com/addons/detail/ghost-downloader-browser/odaohmfjjbompdkmfbambadnagplcmce"
# CHROME_ADDONS_URL = "https://chromewebstore.google.com/detail/ghost-downloader-browser/pinckpkeeajogfgajbicpnengimiblch"
# RELEASE_URL = "https://github.com/XiaoYouChR/Ghost-Downloader-3/releases/latest"
# BASE_EFFICIENCY_THRESHOLD = 0.8  # 判断阈值

cfg = Config()


def defaultHeaders() -> dict[str, str]:
    return dict(cfg.defaultRequestHeaders.value)
