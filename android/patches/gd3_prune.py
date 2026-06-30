import os
import re
import shutil
from os.path import isdir, join

KEEP = {
    "Core", "Core5Compat", "Concurrent", "DBus", "Gui", "Widgets",
    "Network", "WebSockets", "Xml", "Svg", "SvgWidgets",
    "OpenGL", "OpenGLWidgets", "PrintSupport", "Sql",
}

FFMPEG_LIBS = ("libavcodec", "libavformat", "libavutil", "libavdevice",
               "libavfilter", "libswscale", "libswresample", "libQt6FFmpegStub")

MODULE_RE = (
    re.compile(r"^libQt6([A-Za-z0-9]+)_arm64-v8a\.so$"),
    re.compile(r"^Qt([A-Za-z0-9]+)\.abi3\.so$"),
    re.compile(r"^Qt6([A-Za-z0-9]+)_arm64-v8a-android-dependencies\.xml$"),
)

UNUSED_PLUGINS = {
    "sceneparsers", "assetimporters", "renderers", "geometryloaders",
    "qmltooling", "scenegraph", "webview", "designer", "position", "sensors",
    "multimedia",
}


def pruneDir(d):
    if not isdir(d):
        return 0
    freed = 0
    for name in list(os.listdir(d)):
        mod = None
        for rx in MODULE_RE:
            m = rx.match(name)
            if m:
                mod = m.group(1)
                break
        if (mod is not None and mod not in KEEP) or name.startswith(FFMPEG_LIBS):
            p = join(d, name)
            try:
                freed += os.path.getsize(p)
                os.remove(p)
            except OSError:
                pass
    return freed


def removeDir(d):
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


def pruneQt(libs, pyside, log):
    freed = 0
    freed += pruneDir(libs)
    freed += pruneDir(join(pyside, "Qt", "lib"))
    freed += pruneDir(pyside)

    freed += removeDir(join(pyside, "Qt", "qml"))
    freed += removeDir(join(pyside, "Qt", "translations"))

    for plugin in UNUSED_PLUGINS:
        freed += removeDir(join(pyside, "Qt", "plugins", plugin))
    log("[gd3-prune] 裁掉未用 Qt 模块/QML/translations，释放 ~{} MB（keep={} 个模块）".format(
        freed // 1024 // 1024, len(KEEP)))
    return freed
