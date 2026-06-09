"""APK 瘦身 —— allowlist 删掉纯 QWidget app 用不到的 Qt 模块(PySide6 全套 Qt 顶层 lib/ 与 bundle 各一份, 重复 ~129MB)。"""

import os
import re
import shutil
from os.path import isdir, join

# 保留: app+QFluentWidgets 实际 import 的 + 传递依赖(Concurrent) + 小而稳妥保留的几个。
KEEP = {
    "Core", "Core5Compat", "Concurrent", "DBus", "Gui", "Widgets",
    "Network", "WebSockets", "Xml", "Svg", "SvgWidgets",
    "OpenGL", "OpenGLWidgets", "PrintSupport", "Sql",
}
# Multimedia 不在 KEEP, 连带删 Qt 自带 ffmpeg 后端(~16MB); 合流用 gd3ffmpeg 独立二进制, 与 Qt Multimedia 无关
_EXTRA_LIB_PREFIXES = ("libavcodec", "libavformat", "libavutil", "libavdevice",
                       "libavfilter", "libswscale", "libswresample", "libQt6FFmpegStub")

# libQt6<Module>_arm64-v8a.so / Qt<Module>.abi3.so / Qt6<Module>_..-dependencies.xml
_PATTERNS = (
    re.compile(r"^libQt6([A-Za-z0-9]+)_arm64-v8a\.so$"),
    re.compile(r"^Qt([A-Za-z0-9]+)\.abi3\.so$"),
    re.compile(r"^Qt6([A-Za-z0-9]+)_arm64-v8a-android-dependencies\.xml$"),
)

# 已移除模块的孤儿插件目录(模块都删了, 这些插件不可能被加载)。不在此集的插件目录一律保留(platforms 对 android 关键)。
_PLUGIN_REMOVE = {
    "sceneparsers", "assetimporters", "renderers", "geometryloaders",
    "qmltooling", "scenegraph", "webview", "designer", "position", "sensors",
    "multimedia",  # Multimedia 已删，其播放后端插件（android/ffmpeg mediaplugin）随之死掉
}


def _matched_module(name):
    for rx in _PATTERNS:
        m = rx.match(name)
        if m:
            return m.group(1)
    return None


def _prune_flat(d):
    """删 d 下匹配 Qt 模块命名且不在 KEEP 的文件，返回释放字节。"""
    if not isdir(d):
        return 0
    freed = 0
    for name in list(os.listdir(d)):
        mod = _matched_module(name)
        remove = (mod is not None and mod not in KEEP) or name.startswith(_EXTRA_LIB_PREFIXES)
        if remove:
            p = join(d, name)
            try:
                freed += os.path.getsize(p)
                os.remove(p)
            except OSError:
                pass
    return freed


def _rmtree_size(d):
    if not isdir(d):
        return 0
    total = 0
    for root, _, files in os.walk(d):
        for f in files:
            try:
                total += os.path.getsize(join(root, f))
            except OSError:
                pass
    shutil.rmtree(d, ignore_errors=True)
    return total


def prune_qt(libs_dir, pyside_dir, log):
    """libs_dir=顶层 libs/<arch>（distribute_libs 源）；pyside_dir=bundle 源里的 PySide6。"""
    freed = 0
    freed += _prune_flat(libs_dir)                       # 顶层 lib/<arch>
    freed += _prune_flat(join(pyside_dir, "Qt", "lib"))  # bundle 源 PySide6/Qt/lib(重复的那份)
    freed += _prune_flat(pyside_dir)                     # bundle 源 PySide6/*.abi3.so
    # 整目录删: qml(纯 QML 不用) + translations(Qt 内置对话框翻译, app 自带 i18n)
    freed += _rmtree_size(join(pyside_dir, "Qt", "qml"))
    freed += _rmtree_size(join(pyside_dir, "Qt", "translations"))
    # 删已移除模块的孤儿插件目录
    for cat in _PLUGIN_REMOVE:
        freed += _rmtree_size(join(pyside_dir, "Qt", "plugins", cat))
    log("[gd3-prune] 裁掉未用 Qt 模块/QML/translations，释放 ~{} MB（keep={} 个模块）".format(
        freed // 1024 // 1024, len(KEEP)))
    return freed
