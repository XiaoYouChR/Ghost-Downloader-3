# coding:utf-8
import ctypes
import os
import sys
import time
import warnings

import darkdetect
from PySide6.QtCore import Qt, QSharedMemory
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication
from loguru import logger
from qfluentwidgets import setTheme, Theme, setThemeColor

# noinspection PyUnresolvedReferences
import Res_rc
from app.common.config import cfg
from app.common.methods import loadPlugins
from app.view.main_window import MainWindow

# create shareMemory
shareMemory = QSharedMemory()
shareMemory.setKey("Ghost Downloader")
if shareMemory.attach():
    if sys.platform == "win32":
        import win32gui
        hWnd = win32gui.FindWindow(None, "Ghost Downloader")
        win32gui.ShowWindow(hWnd, 1)
        win32gui.SetForegroundWindow(hWnd)
    sys.exit(-1)
shareMemory.create(1)

# config loguru
logger.add("Ghost Downloader 运行日志.log", rotation="512 KB")
logger.info(f"Ghost Downloader is launched at {time.time_ns()}")
warnings.warn = logger.warning

# enable dpi scale
if cfg.get(cfg.dpiScale) == "Auto":
    pass
else:
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"
    os.environ["QT_SCALE_FACTOR"] = str(cfg.get(cfg.dpiScale))

# create application
app = QApplication(sys.argv)
app.setAttribute(Qt.AA_DontCreateNativeWidgetSiblings)

# Enable Theme
setTheme(Theme.DARK if darkdetect.isDark() else Theme.LIGHT, save=False)

# Get Theme Color
# Windows Only
if sys.platform == "win32":
    try:
        # 定义用于获取主题色的函数

        ctypes.windll.dwmapi.DwmGetColorizationColor.restype = ctypes.c_ulong
        ctypes.windll.dwmapi.DwmGetColorizationColor.argtypes = [ctypes.POINTER(ctypes.c_ulong),
                                                                ctypes.POINTER(ctypes.c_bool)]

        color = ctypes.c_ulong()
        opaque = ctypes.c_bool()

        # 获取主题颜色值
        ctypes.windll.dwmapi.DwmGetColorizationColor(ctypes.byref(color), ctypes.byref(opaque))

        # 将颜色值转换为RGB元组
        b, g, r = color.value % 256, (color.value >> 8) % 256, (color.value >> 16) % 256

        setThemeColor(QColor(r, g, b), save=False)

    except Exception as e:
        logger.error(f"Cannot get theme color: {e}")
elif sys.platform == "darwin":  # macOS Only
    # 咱就是说为什么苹果要把开发者文档做成英文，出个中文版不好吗？
    # TM的让我找得好苦…… - By YHX
    import objc # PyObjC
    from Foundation import NSBundle

    # 加载AppKit框架
    AppKit = NSBundle.bundleWithIdentifier_('com.apple.AppKit')

    # 获取NSColor类
    NSColor = AppKit.classNamed_('NSColor')
    NSColorSpace = AppKit.classNamed_('NSColorSpace')

    # 获取当前主题色
    theme_color = NSColor.controlAccentColor() #md就是这个API让我找了好久……
    # 欸，这时还不能用，因为现在这是NSColor Catalog color，还要转换！
    color = theme_color.colorUsingColorSpace_(NSColorSpace.sRGBColorSpace())
    # 获取颜色的 RGB 分量
    red = color.redComponent()
    green = color.greenComponent()
    blue = color.blueComponent()
    
    # 将颜色分量转换为 0-255 范围
    red = int(red * 255)
    green = int(green * 255)
    blue = int(blue * 255)

    setThemeColor(QColor(red, green, blue), save=False)
else:
    logger.warning("Cannot get theme color on this platform: "+sys.platform)
    
# create main window
w = MainWindow()

# loading plugins
pluginsPath=os.path.join(os.path.dirname(__file__), "plugins")
loadPlugins(w, pluginsPath)

try:  # 静默启动
    if sys.argv[1] == "--silence":
        w.hide()
except:
    w.show()

sys.exit(app.exec())
