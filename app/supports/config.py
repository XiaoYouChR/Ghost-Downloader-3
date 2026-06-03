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

DEFAULT_USER_AGENT_PRESETS: list[dict[str, str]] = [
    {
        "name": "Chrome (Windows)",
        "value": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
    },
    {
        "name": "Edge (Windows)",
        "value": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36 Edg/144.0.0.0",
    },
    {
        "name": "Firefox (Windows)",
        "value": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
    },
    {
        "name": "Safari (macOS)",
        "value": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15",
    },
    {
        "name": "Chrome (Android)",
        "value": "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Mobile Safari/537.36",
    },
]


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


class CategoryListSerializer(ConfigSerializer):
    """下载分类规则列表序列化器"""

    def serialize(self, value: list) -> str:
        return dumps(value).decode("utf-8")

    def deserialize(self, value: str) -> list:
        try:
            result = loads(value)
            return result if isinstance(result, list) else []
        except (ValueError, TypeError):
            return []


class UserAgentListValidator(ConfigValidator):
    """User-Agent 预设列表验证器"""

    def validate(self, value) -> bool:
        if not isinstance(value, list):
            return False
        return all(
            isinstance(item, dict)
            and isinstance(item.get("name"), str)
            and isinstance(item.get("value"), str)
            and item["value"]
            for item in value
        )

    def correct(self, value) -> list:
        return value if self.validate(value) else list(DEFAULT_USER_AGENT_PRESETS)


class UserAgentListSerializer(ConfigSerializer):
    """User-Agent 预设列表序列化器"""

    def serialize(self, value: list) -> str:
        return dumps(value).decode("utf-8")

    def deserialize(self, value: str) -> list:
        try:
            result = loads(value)
            return result if isinstance(result, list) else list(DEFAULT_USER_AGENT_PRESETS)
        except (ValueError, TypeError):
            return list(DEFAULT_USER_AGENT_PRESETS)


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

    # 下载分类
    enableCategory = ConfigItem(
        "Category", "EnableCategory", False, BoolValidator()
    )
    categoryRules = ConfigItem(
        "Category",
        "CategoryRules",
        [],
        CategoryListValidator(),
        CategoryListSerializer(),
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
    userAgents = ConfigItem(
        "Network",
        "UserAgents",
        list(DEFAULT_USER_AGENT_PRESETS),
        UserAgentListValidator(),
        UserAgentListSerializer(),
    )
    activeUserAgent = ConfigItem(
        "Network",
        "ActiveUserAgent",
        DEFAULT_USER_AGENT_PRESETS[0]["value"],
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
VERSION = "3.10.3"
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


def activeUserAgent() -> str:
    value = cfg.activeUserAgent.value
    if value:
        return value
    presets = cfg.userAgents.value
    return presets[0]["value"] if presets else DEFAULT_USER_AGENT_PRESETS[0]["value"]


def defaultHeaders() -> dict[str, str]:
    return {**_BASE_HEADERS, "user-agent": activeUserAgent()}
