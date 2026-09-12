from __future__ import annotations

import json
from pathlib import Path
from re import compile
from urllib.request import getproxies

from app.config.paths import DOWNLOAD_DIR
from app.signal import BoundSignal

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


class ConfigValidator:
    def validate(self, value) -> bool:
        return True

    def correct(self, value):
        return value


class RangeValidator(ConfigValidator):
    def __init__(self, min, max):
        self.min = min
        self.max = max
        self.range = (min, max)

    def validate(self, value) -> bool:
        return self.min <= value <= self.max

    def correct(self, value):
        return min(max(self.min, value), self.max)


class OptionsValidator(ConfigValidator):
    def __init__(self, options):
        if not options:
            raise ValueError("The `options` can't be empty.")
        self.options = list(options)

    def validate(self, value) -> bool:
        return value in self.options

    def correct(self, value):
        return value if self.validate(value) else self.options[0]


class BoolValidator(ConfigValidator):
    def validate(self, value) -> bool:
        return isinstance(value, bool)

    def correct(self, value) -> bool:
        return bool(value)


class FolderValidator(ConfigValidator):
    def validate(self, value) -> bool:
        return Path(value).exists()

    def correct(self, value) -> str:
        path = Path(value)
        path.mkdir(parents=True, exist_ok=True)
        return str(path.absolute())


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


class ClientProfileValidator(ConfigValidator):
    def validate(self, value) -> bool:
        return isinstance(value, str) and bool(value)

    def correct(self, value) -> str:
        return value if self.validate(value) else "auto"


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


class HeadersValidator(ConfigValidator):
    def validate(self, value) -> bool:
        return isinstance(value, dict) and all(
            isinstance(k, str) and isinstance(v, str) for k, v in value.items()
        )

    def correct(self, value) -> dict:
        return value if self.validate(value) else dict(BASE_HEADERS)


class HeadersPresetListValidator(ConfigValidator):
    def _isValid(self, item) -> bool:
        return (
            isinstance(item, dict)
            and {"name", "headers"} <= item.keys()
            and isinstance(item["name"], str)
            and HeadersValidator().validate(item["headers"])
        )

    def validate(self, value) -> bool:
        return isinstance(value, list) and bool(value) and all(map(self._isValid, value))

    def correct(self, value) -> list:
        presets = [i for i in value if self._isValid(i)] if isinstance(value, list) else []
        return presets or [{"name": "默认", "headers": dict(BASE_HEADERS)}]


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


class ConfigSerializer:
    def serialize(self, value):
        return value

    def deserialize(self, value):
        return value


class ConfigItem:
    def __init__(self, group, name, default, validator=None, serializer=None, restart=False):
        self.group = group
        self.name = name
        self.validator = validator or ConfigValidator()
        self.serializer = serializer or ConfigSerializer()
        self.restart = restart
        self.defaultValue = self.validator.correct(default)
        self._value = self.defaultValue
        self.valueChanged = BoundSignal()

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, v):
        v = self.validator.correct(v)
        old = self._value
        self._value = v
        if old != v:
            self.valueChanged.emit(v)

    @property
    def key(self):
        return f"{self.group}/{self.name}" if self.name else self.group

    def serialize(self):
        return self.serializer.serialize(self.value)

    def deserializeFrom(self, value):
        self._value = self.validator.correct(self.serializer.deserialize(value))


class RangeConfigItem(ConfigItem):
    @property
    def range(self):
        return self.validator.range


class OptionsConfigItem(ConfigItem):
    @property
    def options(self):
        return self.validator.options


class AndroidConfig:
    downloadFolder = ConfigItem("GeneralDownload", "DownloadFolder", str(DOWNLOAD_DIR), FolderValidator())
    maxTaskNum = RangeConfigItem("GeneralDownload", "MaxTaskNum", 3, RangeValidator(1, 10))
    isSpeedLimitEnabled = ConfigItem("GeneralDownload", "isSpeedLimitEnabled", False, BoolValidator())
    speedLimitation = RangeConfigItem("GeneralDownload", "SpeedLimitation", 4194304, RangeValidator(1024, 104857600))
    shouldVerifySsl = ConfigItem("GeneralDownload", "shouldVerifySsl", False, BoolValidator())
    proxyServer = ConfigItem("GeneralDownload", "ProxyServer", "Auto", ProxyValidator())
    preBlockNum = RangeConfigItem("GeneralDownload", "PreBlockNum", 8, RangeValidator(1, 256))
    autoSpeedUp = ConfigItem("GeneralDownload", "AutoSpeedUp", True, BoolValidator())
    shouldPreserveLastModified = ConfigItem("GeneralDownload", "PreserveLastModified", False, BoolValidator())
    shouldDeleteFilesOnRemove = ConfigItem("GeneralDownload", "DeleteFilesOnRemove", False, BoolValidator())
    maxReassignSize = RangeConfigItem("GeneralDownload", "MaxReassignSize", 512, RangeValidator(64, 102400))

    isCategoryEnabled = ConfigItem("Category", "EnableCategory", False, BoolValidator())
    categoryRules = ConfigItem("Category", "CategoryRules", [], CategoryListValidator())

    shouldDraftTakenDownload = ConfigItem(
        "Browser", "EnableRaiseWindowWhenReceiveMsg", False, BoolValidator())
    # 桌面默认开；Android 默认关，因为开着意味着一条永不消失的前台通知
    isBrowserExtensionEnabled = ConfigItem(
        "Browser", "EnableBrowserExtension", False, BoolValidator())
    browserExtensionPairToken = ConfigItem("Browser", "BrowserExtensionPairToken", "")
    browserExtensionPort = RangeConfigItem("Browser", "Port", 14370, RangeValidator(1024, 65535))

    isAria2RpcEnabled = ConfigItem("Aria2Rpc", "Enabled", False, BoolValidator())
    aria2RpcPort = RangeConfigItem("Aria2Rpc", "Port", 16800, RangeValidator(1024, 65535))
    aria2RpcToken = ConfigItem("Aria2Rpc", "Token", "")
    aria2RpcEmulateFingerprint = ConfigItem(
        "Aria2Rpc", "EmulateFingerprint", False, BoolValidator())

    clientProfile = ConfigItem("Network", "ClientProfile", "auto", ClientProfileValidator())
    shouldUseSystemDns = ConfigItem("Network", "ShouldUseSystemDns", True, BoolValidator())
    headersPresets = ConfigItem(
        "Network", "HeadersPresets",
        [{"name": "默认", "headers": dict(BASE_HEADERS)}],
        HeadersPresetListValidator(),
    )
    currentHeadersPreset = RangeConfigItem("Network", "CurrentHeadersPreset", 0, RangeValidator(0, 99))
    identityPresets = ConfigItem(
        "Network", "IdentityPresets",
        [{"name": "百度网盘客户端", "clientProfile": "raw",
          "userAgent": "pan.baidu.com", "hosts": ["*.pcs.baidu.com"],
          "isEnabled": True}],
        IdentityPresetListValidator(),
    )

    shouldCheckUpdateAtStartup = ConfigItem("Software", "CheckUpdateAtStartUp", False, BoolValidator())

    def __init__(self):
        self._path: str | None = None
        self._items: dict[str, ConfigItem] = {}
        self.byName: dict[str, ConfigItem] = {}
        self._index()

    def _index(self):
        self._items.clear()
        self.byName.clear()
        for attrName in dir(self.__class__):
            item = getattr(self.__class__, attrName)
            if isinstance(item, ConfigItem):
                self._items[item.key] = item
                self.byName[attrName] = item

    def set(self, item: ConfigItem, value, save=True):
        if item.value == value:
            return
        item.value = value
        if save and self._path:
            self._save()

    def load(self, path: str):
        self._path = path
        self._index()
        p = Path(path)
        if not p.exists():
            return
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        for groupName, group in data.items():
            if not isinstance(group, dict):
                continue
            for key, raw in group.items():
                fullKey = f"{groupName}/{key}"
                item = self._items.get(fullKey)
                if item is not None:
                    item.deserializeFrom(raw)

    def _save(self):
        if not self._path:
            return
        data: dict[str, dict] = {}
        for item in self._items.values():
            group = data.setdefault(item.group, {})
            group[item.name] = item.serialize()

        p = Path(self._path)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(data, ensure_ascii=False, indent=4),
            encoding="utf-8",
        )
        tmp.replace(p)


cfg = AndroidConfig()


def currentHeadersPresetIndex() -> int:
    return min(cfg.currentHeadersPreset.value, len(cfg.headersPresets.value) - 1)


def currentHeaders() -> dict:
    return dict(cfg.headersPresets.value[currentHeadersPresetIndex()]["headers"])


def toProxyUrl(url: str) -> str:
    if "://" not in url:
        return "http://" + url
    if url.startswith("socks://"):
        return "socks5://" + url[len("socks://"):]
    return url


def proxy() -> str | None:
    if cfg.proxyServer.value == "Off":
        return None
    if cfg.proxyServer.value == "Auto":
        system = getproxies()
        if not system:
            return None
        for key in ("http", "https", "socks"):
            if url := system.get(key):
                return toProxyUrl(url)
        return None
    server = str(cfg.proxyServer.value).strip()
    return toProxyUrl(server) if server else None
