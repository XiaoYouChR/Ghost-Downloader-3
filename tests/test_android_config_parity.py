from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path

from app.config.cfg import Config

desktopCfg = importlib.import_module("app.config.cfg")

ANDROID_CFG_PATH = Path(__file__).parents[1] / "android/app/src/main/python/app/config/cfg.py"

# 桌面窗口/Dock/菜单栏/开机自启/URL scheme/剪贴板监听/下载目录历史/设置页折叠状态；
# 主题与语言在 Android 走 SharedPreferences（见 android/CLAUDE.md「Config 按消费者分路」）
DESKTOP_ONLY = {
    ("Browser", "UrlSchemeRegistered"),
    ("GeneralDownload", "HistoryDownloadFolder"),
    ("Personalization", "BackgroundEffect"),
    ("Personalization", "DpiScale"),
    ("Personalization", "Language"),
    ("Personalization", "ShowDockIcon"),
    ("Personalization", "ShowDockSpeed"),
    ("Personalization", "ShowMenuBarSpeed"),
    ("Personalization", "ThemeMode"),
    ("Software", "AutoRun"),
    ("Software", "ClipboardListener"),
    ("Software", "CloseMode"),
    ("Software", "Geometry"),
    ("UI", "ExpandedSettingGroups"),
    ("UI", "SettingGroupOrder"),
}


def loadAndroidCfg():
    spec = importlib.util.spec_from_file_location("android_cfg", ANDROID_CFG_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def keysOf(configClass) -> set[tuple[str, str]]:
    return {
        (item.group, item.name)
        for item in vars(configClass).values()
        if hasattr(item, "group") and hasattr(item, "name") and hasattr(item, "validator")
    }


def test_android_config_covers_every_desktop_setting_except_desktop_only():
    missing = keysOf(Config) - keysOf(loadAndroidCfg().AndroidConfig) - DESKTOP_ONLY
    assert missing == set()


def signaturesOf(module) -> dict[str, inspect.Signature]:
    return {
        name: inspect.signature(value)
        for name, value in vars(module).items()
        if inspect.isfunction(value) and value.__module__ == module.__name__ and not name.startswith("_")
    }


def test_android_cfg_functions_match_desktop_signatures():
    desktop, android = signaturesOf(desktopCfg), signaturesOf(loadAndroidCfg())
    mismatched = {name for name in desktop.keys() & android.keys() if desktop[name] != android[name]}
    assert mismatched == set()
