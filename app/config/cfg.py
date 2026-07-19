import sys
from enum import Enum
from re import compile
from urllib.request import getproxies

from PySide6.QtCore import QRect, QStandardPaths, QLocale
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
    EnumSerializer,
    FolderListValidator,
    Theme,
)

from app.platform.android import IS_ANDROID

BASE_HEADERS = {
    "accept-encoding": "deflate, br, gzip",
    "accept-language": "zh-CN,zh;q=0.9",
    "cookie": "down_ip=1",
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "none",
    "sec-fetch-user": "?1",
    "upgrade-insecure-requests": "1",
}

class Language(Enum):
    CHINESE_SIMPLIFIED = QLocale(QLocale.Language.Chinese, QLocale.Country.China)
    CHINESE_TRADITIONAL = QLocale(QLocale.Language.Chinese, QLocale.Country.Taiwan)
    CANTONESE = QLocale(QLocale.Language.Cantonese, QLocale.Country.HongKong)
    ENGLISH_UNITED_STATES = QLocale(QLocale.Language.English, QLocale.Country.UnitedStates)
    JAPANESE = QLocale(QLocale.Language.Japanese, QLocale.Country.Japan)
    RUSSIAN = QLocale(QLocale.Language.Russian, QLocale.Country.Russia)
    PORTUGUESE_BRAZIL = QLocale(QLocale.Language.Portuguese, QLocale.Country.Brazil)
    AUTO = QLocale()


# 语言的展示标签，AUTO 由视图层翻译
LANGUAGE_TEXTS = {
    Language.CHINESE_SIMPLIFIED: "简体中文 (中国大陆)",
    Language.CHINESE_TRADITIONAL: "正體中文 (台灣)",
    Language.CANTONESE: "粤语 (香港)",
    Language.ENGLISH_UNITED_STATES: "English (US)",
    Language.JAPANESE: "日本語 (日本)",
    Language.RUSSIAN: "Русский (Россия)",
    Language.PORTUGUESE_BRAZIL: "Português (Brasil)",
}


class CloseMode(Enum):
    ASK = "Ask"
    BACKGROUND = "Background"
    QUIT = "Quit"


class ProxyValidator(ConfigValidator):
    PATTERN = compile(
        r"^"
        r"(?P<protocol>http|https|socks4|socks5|socks5h)://"
        r"(?:(?P<user>\w+):(?P<password>[\w!@#$%^&*()]+)@)?"
        r"(?:"
        r"(?P<ip>(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?))|"
        r"(?P<domain>(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,6})"
        r")"
        r":(?P<port>\d{1,5})"
        r"$"
    )

    def validate(self, value: str) -> bool:
        return bool(self.PATTERN.match(value)) or value in {"Auto", "Off"}

    def correct(self, value) -> str:
        return value if self.validate(value) else "Auto"


class GeometrySerializer(ConfigSerializer):
    def serialize(self, value: QRect) -> str:
        x, y, w, h = value.x(), value.y(), value.width(), value.height()
        return f"{x},{y},{w},{h}"

    def deserialize(self, value: str) -> QRect:
        try:
            x, y, w, h = map(int, value.split(","))
            return QRect(x, y, w, h)
        except (ValueError, TypeError):
            return QRect()


class LanguageSerializer(ConfigSerializer):
    def serialize(self, language):
        return language.value.name() if language != Language.AUTO else "Auto"

    def deserialize(self, value: str):
        return Language(QLocale(value)) if value != "Auto" else Language.AUTO


class ThemeSerializer(ConfigSerializer):
    def serialize(self, theme: Theme) -> str:
        return theme.value

    def deserialize(self, value: str) -> Theme:
        try:
            return Theme(value)
        except ValueError:
            return Theme.AUTO


class StringListValidator(ConfigValidator):
    def validate(self, value) -> bool:
        return isinstance(value, list) and all(isinstance(i, str) for i in value)

    def correct(self, value) -> list:
        if not isinstance(value, list):
            return []
        return [i for i in value if isinstance(i, str)]


class CategoryListValidator(ConfigValidator):
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
    def __init__(self, expected: type, fallback):
        self._expected = expected
        self._fallback = fallback

    def serialize(self, value) -> str:
        import json
        return json.dumps(value, ensure_ascii=False)

    def deserialize(self, value: str):
        import json
        try:
            result = json.loads(value)
            return result if isinstance(result, self._expected) else self._fallback()
        except (ValueError, TypeError):
            return self._fallback()


class ClientProfileValidator(ConfigValidator):
    def validate(self, value) -> bool:
        return isinstance(value, str) and bool(value)

    def correct(self, value) -> str:
        return value if self.validate(value) else "auto"


class IdentityPresetListValidator(ConfigValidator):
    REQUIRED_KEYS = {"name", "clientProfile", "userAgent", "hosts"}

    def _isValidPreset(self, item) -> bool:
        return (
            isinstance(item, dict)
            and self.REQUIRED_KEYS <= item.keys()
            and isinstance(item["name"], str)
            and isinstance(item["clientProfile"], str)
            and isinstance(item["userAgent"], str)
            and isinstance(item["hosts"], list)
            and all(isinstance(h, str) for h in item["hosts"])
        )

    def validate(self, value) -> bool:
        return isinstance(value, list) and all(self._isValidPreset(item) for item in value)

    def correct(self, value) -> list:
        if not isinstance(value, list):
            return []
        return [item for item in value if self._isValidPreset(item)]


class HeadersValidator(ConfigValidator):
    def validate(self, value) -> bool:
        return isinstance(value, dict) and bool(value) and all(
            isinstance(k, str) and isinstance(v, str) for k, v in value.items()
        )

    def correct(self, value) -> dict:
        return value if self.validate(value) else dict(BASE_HEADERS)


class Config(QConfig):

    # 覆盖 QConfig.themeMode，让 QConfig.load() 自动用正确的 key 和 default
    themeMode = OptionsConfigItem(
        "Personalization", "ThemeMode", Theme.AUTO,
        OptionsValidator(Theme), ThemeSerializer(),
    )

    # 下载
    downloadFolder = ConfigItem(
        "GeneralDownload", "DownloadFolder",
        "/storage/emulated/0/Download" if IS_ANDROID
        else QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation),
        FolderValidator(),
    )
    memoryDownloadFolders = ConfigItem(
        "GeneralDownload", "HistoryDownloadFolder", [], FolderListValidator()
    )
    maxTaskNum = RangeConfigItem("GeneralDownload", "MaxTaskNum", 3, RangeValidator(1, 10))
    shouldStartAheadDownload = ConfigItem(
        "GeneralDownload", "StartAheadDownload", True, BoolValidator()
    )
    isSpeedLimitEnabled = ConfigItem("GeneralDownload", "isSpeedLimitEnabled", False, BoolValidator())
    speedLimitation = RangeConfigItem(
        "GeneralDownload", "SpeedLimitation", 4194304, RangeValidator(1024, 104857600)
    )
    shouldVerifySsl = ConfigItem("GeneralDownload", "shouldVerifySsl", False, BoolValidator(), restart=True)
    proxyServer = ConfigItem("GeneralDownload", "ProxyServer", "Auto", ProxyValidator())
    preBlockNum = RangeConfigItem("GeneralDownload", "PreBlockNum", 8, RangeValidator(1, 256))
    autoSpeedUp = ConfigItem("GeneralDownload", "AutoSpeedUp", True, BoolValidator())
    shouldPreserveLastModified = ConfigItem("GeneralDownload", "PreserveLastModified", False, BoolValidator())
    shouldDeleteFilesOnRemove = ConfigItem("GeneralDownload", "DeleteFilesOnRemove", False, BoolValidator())
    maxReassignSize = RangeConfigItem(
        "GeneralDownload", "MaxReassignSize", 512, RangeValidator(64, 102400)
    )

    # 分类
    isCategoryEnabled = ConfigItem("Category", "EnableCategory", False, BoolValidator())
    categoryRules = ConfigItem(
        "Category", "CategoryRules", [],
        CategoryListValidator(), JsonConfigSerializer(list, list),
    )

    # 浏览器扩展
    isBrowserExtensionEnabled = ConfigItem("Browser", "EnableBrowserExtension", True, BoolValidator())
    browserExtensionPairToken = ConfigItem("Browser", "BrowserExtensionPairToken", "")
    browserExtensionPort = RangeConfigItem("Browser", "Port", 14370, RangeValidator(1024, 65535))
    shouldDraftTakenDownload = ConfigItem(
        "Browser", "EnableRaiseWindowWhenReceiveMsg", False, BoolValidator()
    )
    isUrlSchemeRegistered = ConfigItem("Browser", "UrlSchemeRegistered", False, BoolValidator())

    # Aria2 RPC 兼容
    isAria2RpcEnabled = ConfigItem("Aria2Rpc", "Enabled", False, BoolValidator())
    aria2RpcPort = RangeConfigItem("Aria2Rpc", "Port", 16800, RangeValidator(1024, 65535))
    aria2RpcToken = ConfigItem("Aria2Rpc", "Token", "")
    aria2RpcEmulateFingerprint = ConfigItem("Aria2Rpc", "EmulateFingerprint", False, BoolValidator())

    # 个性化
    if sys.platform == "win32":
        from app.platform.windows import isWin10
        backgroundEffect = OptionsConfigItem(
            "Personalization", "BackgroundEffect",
            "Acrylic" if isWin10() else "Mica",
            OptionsValidator(["Acrylic", "Mica", "MicaAlt", "Aero", "None"]),
        )
    dpiScale = RangeConfigItem("Personalization", "DpiScale", 0, RangeValidator(0, 5), restart=True)
    if sys.platform == "darwin":
        shouldShowDockIcon = ConfigItem("Personalization", "ShowDockIcon", True, BoolValidator())
        shouldShowDockSpeed = ConfigItem("Personalization", "ShowDockSpeed", True, BoolValidator())
        shouldShowMenuBarSpeed = ConfigItem("Personalization", "ShowMenuBarSpeed", True, BoolValidator())
    language = OptionsConfigItem(
        "Personalization", "Language", Language.AUTO,
        OptionsValidator(Language), LanguageSerializer(), restart=True,
    )

    # 软件
    shouldCheckUpdateAtStartup = ConfigItem("Software", "CheckUpdateAtStartUp", True, BoolValidator())
    shouldRunAtLogin = ConfigItem("Software", "AutoRun", False, BoolValidator())
    closeMode = OptionsConfigItem(
        "Software", "CloseMode", CloseMode.ASK,
        OptionsValidator(CloseMode), EnumSerializer(CloseMode),
    )
    isClipboardListenerEnabled = ConfigItem("Software", "ClipboardListener", True, BoolValidator())
    geometry = ConfigItem(
        "Software", "Geometry", QRect(0, 0, 0, 0), serializer=GeometrySerializer(),
    )

    # OOBE
    hasCompletedOobe = ConfigItem("Software", "HasCompletedOobe", False, BoolValidator())

    # UI 状态
    expandedSettingGroups = ConfigItem("UI", "ExpandedSettingGroups", [], StringListValidator())
    settingGroupOrder = ConfigItem("UI", "SettingGroupOrder", [], StringListValidator())

    # 网络
    clientProfile = ConfigItem("Network", "ClientProfile", "auto", ClientProfileValidator())
    defaultRequestHeaders = ConfigItem(
        "Network", "DefaultHeaders", dict(BASE_HEADERS),
        HeadersValidator(), JsonConfigSerializer(dict, lambda: dict(BASE_HEADERS)),
    )
    identityPresets = ConfigItem(
        "Network", "IdentityPresets",
        [{"name": "百度网盘客户端", "clientProfile": "raw",
          "userAgent": "pan.baidu.com", "hosts": ["*.pcs.baidu.com"],
          "isEnabled": True}],
        IdentityPresetListValidator(), JsonConfigSerializer(list, list),
    )


cfg = Config()


def proxy() -> str | None:
    if cfg.proxyServer.value == "Off":
        return None
    if cfg.proxyServer.value == "Auto":
        system = getproxies()
        return next((v for v in system.values() if v), None) if system else None
    server = str(cfg.proxyServer.value).strip()
    return server or None
