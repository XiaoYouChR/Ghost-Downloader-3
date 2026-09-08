"""Android configuration adapter — same interface as desktop qfluentwidgets QConfig."""
from __future__ import annotations

import json
from pathlib import Path
from urllib.request import getproxies

from app.signal import BoundSignal

DOWNLOAD_DIR = "/storage/emulated/0/Download"

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


class BoolValidator(ConfigValidator):
    def validate(self, value) -> bool:
        return isinstance(value, bool)

    def correct(self, value) -> bool:
        return bool(value)


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
        self.options = list(options)

    def validate(self, value) -> bool:
        return value in self.options

    def correct(self, value):
        return value if self.validate(value) else self.options[0]


class FolderValidator(ConfigValidator):
    def validate(self, value) -> bool:
        return Path(value).exists()

    def correct(self, value) -> str:
        path = Path(value)
        path.mkdir(parents=True, exist_ok=True)
        return str(path.absolute()).replace("\\", "/")


class ConfigSerializer:
    def serialize(self, value):
        return value

    def deserialize(self, value):
        return value


class ConfigItem:
    def __init__(self, group, key, default, validator=None, serializer=None, **_kw):
        self._group = group
        self._key = key
        self._default = default
        self._validator = validator
        self._serializer = serializer
        self._value = default
        self.valueChanged = BoundSignal()

    @property
    def value(self):
        return self._value

    @property
    def key(self):
        return self._key

    def _load(self, raw):
        value = raw
        if self._serializer and hasattr(self._serializer, "deserialize"):
            value = self._serializer.deserialize(value)
        if self._validator and hasattr(self._validator, "correct"):
            value = self._validator.correct(value)
        self._value = value


class RangeConfigItem(ConfigItem):
    pass


class OptionsConfigItem(ConfigItem):
    pass


class AndroidConfig:
    downloadFolder = ConfigItem("GeneralDownload", "DownloadFolder", DOWNLOAD_DIR, FolderValidator())
    maxTaskNum = RangeConfigItem("GeneralDownload", "MaxTaskNum", 3, RangeValidator(1, 10))
    isSpeedLimitEnabled = ConfigItem("GeneralDownload", "isSpeedLimitEnabled", False, BoolValidator())
    speedLimitation = RangeConfigItem("GeneralDownload", "SpeedLimitation", 4194304, RangeValidator(1024, 104857600))
    shouldVerifySsl = ConfigItem("GeneralDownload", "shouldVerifySsl", False, BoolValidator())
    proxyServer = ConfigItem("GeneralDownload", "ProxyServer", "Auto")
    preBlockNum = RangeConfigItem("GeneralDownload", "PreBlockNum", 8, RangeValidator(1, 256))
    autoSpeedUp = ConfigItem("GeneralDownload", "AutoSpeedUp", True, BoolValidator())
    shouldPreserveLastModified = ConfigItem("GeneralDownload", "PreserveLastModified", False, BoolValidator())
    shouldDeleteFilesOnRemove = ConfigItem("GeneralDownload", "DeleteFilesOnRemove", False, BoolValidator())
    maxReassignSize = RangeConfigItem("GeneralDownload", "MaxReassignSize", 512, RangeValidator(64, 102400))

    isCategoryEnabled = ConfigItem("Category", "EnableCategory", False, BoolValidator())
    categoryRules = ConfigItem("Category", "CategoryRules", [])

    # 本机服务。group/key 与桌面保持一致，配置文件可以互相看懂
    shouldDraftTakenDownload = ConfigItem(
        "Browser", "EnableRaiseWindowWhenReceiveMsg", False, BoolValidator())
    # 桌面默认开，这里默认关：开着就意味着一条永不消失的前台通知，
    # 没装扩展的用户不该先付这个代价
    isBrowserExtensionEnabled = ConfigItem(
        "Browser", "EnableBrowserExtension", False, BoolValidator())
    browserExtensionPairToken = ConfigItem("Browser", "BrowserExtensionPairToken", "")
    browserExtensionPort = RangeConfigItem("Browser", "Port", 14370, RangeValidator(1024, 65535))

    isAria2RpcEnabled = ConfigItem("Aria2Rpc", "Enabled", False, BoolValidator())
    aria2RpcPort = RangeConfigItem("Aria2Rpc", "Port", 16800, RangeValidator(1024, 65535))
    aria2RpcToken = ConfigItem("Aria2Rpc", "Token", "")
    aria2RpcEmulateFingerprint = ConfigItem(
        "Aria2Rpc", "EmulateFingerprint", False, BoolValidator())

    clientProfile = ConfigItem("Network", "ClientProfile", "auto")
    shouldUseSystemDns = ConfigItem("Network", "ShouldUseSystemDns", True, BoolValidator())
    headersPresets = ConfigItem(
        "Network", "HeadersPresets",
        [{"name": "默认", "headers": dict(BASE_HEADERS)}],
    )
    currentHeadersPreset = RangeConfigItem("Network", "CurrentHeadersPreset", 0, RangeValidator(0, 99))
    identityPresets = ConfigItem(
        "Network", "IdentityPresets",
        [{"name": "百度网盘客户端", "clientProfile": "raw",
          "userAgent": "pan.baidu.com", "hosts": ["*.pcs.baidu.com"],
          "isEnabled": True}],
    )

    shouldCheckUpdateAtStartup = ConfigItem("Software", "CheckUpdateAtStartUp", False, BoolValidator())

    def __init__(self):
        self._path: str | None = None
        self._items: dict[str, ConfigItem] = {}
        self.byName: dict[str, ConfigItem] = {}
        self._index()

    # pack 在 import 时才把自己的 ConfigItem 注册到本类上，所以索引不能只建一次
    def _index(self):
        self._items.clear()
        self.byName.clear()
        for name in dir(self.__class__):
            attr = getattr(self.__class__, name)
            if isinstance(attr, ConfigItem):
                self._items[f"{attr._group}/{attr._key}"] = attr
                self.byName[name] = attr

    def set(self, item: ConfigItem, value, save=True):
        old = item._value
        item._value = value
        if old != value:
            item.valueChanged.emit(value)
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
                    item._load(raw)

    def _save(self):
        if not self._path:
            return
        data: dict[str, dict] = {}
        for item in self._items.values():
            group = data.setdefault(item._group, {})
            value = item._value
            if item._serializer and hasattr(item._serializer, "serialize"):
                value = item._serializer.serialize(value)
            group[item._key] = value

        Path(self._path).write_text(
            json.dumps(data, ensure_ascii=False, indent=4),
            encoding="utf-8",
        )


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
