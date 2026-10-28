from __future__ import annotations

import importlib
import importlib.util
import inspect
import json
import re
import shutil
import subprocess
import sys
from fnmatch import fnmatch
from pathlib import Path

from app.config.cfg import Config

ROOT = Path(__file__).parents[1]
GRADLE = (ROOT / "android/app/build.gradle.kts").read_text(encoding="utf-8")
SCRIPT = Path(__file__).parent / "import_android_packs.py"
ANDROID_CFG_PATH = ROOT / "android/app/src/main/python/app/config/cfg.py"
desktopCfg = importlib.import_module("app.config.cfg")

# 桌面窗口/Dock/菜单栏/开机自启/URL scheme/剪贴板监听/下载目录历史/设置页折叠状态/桌面通知/完成后打开文件夹；
# 主题与语言在 Android 走 SharedPreferences（见 android/CLAUDE.md「Config 按消费者分路」）
DESKTOP_ONLY = {
    ("Browser", "UrlSchemeRegistered"),
    ("GeneralDownload", "HistoryDownloadFolder"),
    ("GeneralDownload", "OpenFolderMinSize"),
    ("GeneralDownload", "OpenFolderWhenCompleted"),
    ("GeneralDownload", "RecentFolders"),
    ("Notifications", "TaskCompletedNotification"),
    ("Notifications", "TaskStartedNotification"),
    ("Personalization", "BackgroundEffect"),
    ("Personalization", "DpiScale"),
    ("Personalization", "Language"),
    ("Personalization", "ShowDockIcon"),
    ("Personalization", "ShowDockSpeed"),
    ("Personalization", "ShowMenuBarSpeed"),
    ("Personalization", "ThemeMode"),
    ("Software", "AutoRun"),
    ("Software", "ClipboardIgnoredPacks"),
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
        for attrName, item in vars(configClass).items()
        if not attrName.startswith("pack_") and hasattr(item, "group") and hasattr(item, "name") and hasattr(item, "validator")
    }


def signaturesOf(module) -> dict[str, inspect.Signature]:
    return {
        name: inspect.signature(value)
        for name, value in vars(module).items()
        if inspect.isfunction(value) and value.__module__ == module.__name__ and not name.startswith("_")
    }


def gradleBlock(name: str) -> str:
    start = GRADLE.index(f'register<Sync>("{name}")')
    return GRADLE[start:GRADLE.index("\n}\n", start)]


def excludesOf(block: str) -> list[str]:
    return re.findall(r'exclude\("([^"]+)"\)', block)


def createCopy(source: Path, target: Path, excludes: list[str], includes: tuple[str, ...]) -> None:
    for path in source.rglob("*"):
        relative = path.relative_to(source).as_posix()
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        if not any(fnmatch(relative, pattern) for pattern in includes):
            continue
        if any(fnmatch(relative, pattern) for pattern in excludes):
            continue
        (target / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(path, target / relative)


def buildAndroidTree(tree: Path) -> list[str]:
    engine = gradleBlock("syncEngineSource")
    createCopy(ROOT / "app", tree / "app", excludesOf(engine), ("*.py",))
    shutil.copytree(ROOT / "android/app/src/main/python/app", tree / "app", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__"))

    packs = re.search(r"androidPacks = listOf\((.*?)\)", GRADLE, re.S).group(1)
    packs = re.findall(r'"([^"]+)"', packs)
    featureExcludes = excludesOf(gradleBlock("syncFeatureSource"))
    for pack in packs:
        createCopy(ROOT / "features" / pack, tree / "features" / pack, featureExcludes,
               ("*.py", "manifest.toml", "lists/*"))
    (tree / "features/__init__.py").write_text("")
    return packs


def test_load_android_config_with_every_desktop_setting():
    missing = keysOf(Config) - keysOf(loadAndroidCfg().AndroidConfig) - DESKTOP_ONLY
    assert missing == set()


def test_load_android_config_functions_like_desktop():
    desktop, android = signaturesOf(desktopCfg), signaturesOf(loadAndroidCfg())
    mismatched = {name for name in desktop.keys() & android.keys() if desktop[name] != android[name]}
    assert mismatched == set()


def test_load_every_pack_on_android(tmp_path):
    packs = buildAndroidTree(tmp_path / "tree")

    result = subprocess.run(
        [sys.executable, "-I", str(SCRIPT), str(tmp_path / "tree"), *packs],
        capture_output=True, text=True, cwd=tmp_path,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout.splitlines()[-1]) == {}
