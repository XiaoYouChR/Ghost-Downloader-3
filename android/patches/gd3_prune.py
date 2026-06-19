import os
import re
import shutil
from os.path import isdir, join

KEEP = {
    "Core", "Core5Compat", "Concurrent", "DBus", "Gui", "Widgets",
    "Network", "WebSockets", "Xml", "Svg", "SvgWidgets",
    "OpenGL", "OpenGLWidgets", "PrintSupport", "Sql",
}

_EXTRA_LIB_PREFIXES = ("libavcodec", "libavformat", "libavutil", "libavdevice",
                       "libavfilter", "libswscale", "libswresample", "libQt6FFmpegStub")

_PATTERNS = (
    re.compile(r"^libQt6([A-Za-z0-9]+)_arm64-v8a\.so$"),
    re.compile(r"^Qt([A-Za-z0-9]+)\.abi3\.so$"),
    re.compile(r"^Qt6([A-Za-z0-9]+)_arm64-v8a-android-dependencies\.xml$"),
)

_PLUGIN_REMOVE = {
    "sceneparsers", "assetimporters", "renderers", "geometryloaders",
    "qmltooling", "scenegraph", "webview", "designer", "position", "sensors",
    "multimedia",
}

def _matchedModule(name):
    for rx in _PATTERNS:
        m = rx.match(name)
        if m:
            return m.group(1)
    return None

def _pruneFlat(d):
    if not isdir(d):
        return 0
    freed = 0
    for name in list(os.listdir(d)):
        mod = _matchedModule(name)
        remove = (mod is not None and mod not in KEEP) or name.startswith(_EXTRA_LIB_PREFIXES)
        if remove:
            p = join(d, name)
            try:
                freed += os.path.getsize(p)
                os.remove(p)
            except OSError:
                pass
    return freed

def _rmtreeSize(d):
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

def pruneQt(libs_dir, pyside_dir, log):
    freed = 0
    freed += _pruneFlat(libs_dir)
    freed += _pruneFlat(join(pyside_dir, "Qt", "lib"))
    freed += _pruneFlat(pyside_dir)

    freed += _rmtreeSize(join(pyside_dir, "Qt", "qml"))
    freed += _rmtreeSize(join(pyside_dir, "Qt", "translations"))

    for cat in _PLUGIN_REMOVE:
        freed += _rmtreeSize(join(pyside_dir, "Qt", "plugins", cat))
    log("[gd3-prune] 裁掉未用 Qt 模块/QML/translations，释放 ~{} MB（keep={} 个模块）".format(
        freed // 1024 // 1024, len(KEEP)))
    return freed
