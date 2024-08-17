# coding:utf-8

# 创建 Application
import sys
from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv)

# 检测程序重复运行
from PySide6.QtCore import QSharedMemory

# 尝试访问
sharedMemory = QSharedMemory()
sharedMemory.setKey("Ghost Downloader")

if sharedMemory.attach():  # 访问成功, 说明程序正在运行

    if sys.platform == "win32":
        import win32gui
        import win32con

        hWnd = win32gui.FindWindow(None, "Ghost Downloader")
        win32gui.ShowWindow(hWnd, 1)

        # 发送自定义信息唤醒窗口
        # WM_CUSTOM = win32con.WM_USER + 1
        # win32gui.SendMessage(hWnd, WM_CUSTOM, 0, 0)
        win32gui.SendMessage(hWnd, win32con.WM_USER + 1, 0, 0)

        win32gui.SetForegroundWindow(hWnd)

    sys.exit(-1)
# 创建 SharedMemory
sharedMemory.create(1)

# Starting Program
import os

import time
import warnings

import darkdetect

from PySide6.QtGui import QColor
from PySide6.QtCore import Qt

from loguru import logger
from qfluentwidgets import setTheme, Theme, setThemeColor, qconfig

# noinspection PyUnresolvedReferences
import Res_rc

from app.common.config import cfg
from app.common.methods import loadPlugins
from app.view.main_window import MainWindow

# 设置程序运行路径, 便于调试
if "--debug" in sys.argv:  # 调试时候请使用相对路径！
    cfg.appPath = "./"
    qconfig.load('./Ghost Downloader 配置文件.json', cfg)
else:  # 编译后
    cfg.appPath = app.applicationDirPath()
    qconfig.load('{}/Ghost Downloader 配置文件.json'.format(QApplication.applicationDirPath()), cfg)


    def exceptionHandler(type, value, traceback):  # 自定义错误捕捉函数
        logger.exception(f"意料之外的错误! {type}: {value}. Traceback: {traceback}")


    sys.excepthook = exceptionHandler

# 防止 Mica 背景失效
app.setAttribute(Qt.AA_DontCreateNativeWidgetSiblings)

# config loguru
logger.add('{}/Ghost Downloader 运行日志.log'.format(cfg.appPath), rotation="512 KB")
logger.info(f"Ghost Downloader is launched at {time.time_ns()}")

warnings.warn = logger.warning


# enable dpi scale
if cfg.get(cfg.dpiScale) == "Auto":
    pass
else:
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"
    os.environ["QT_SCALE_FACTOR"] = str(cfg.get(cfg.dpiScale))

# Enable Theme
setTheme(Theme.DARK if darkdetect.isDark() else Theme.LIGHT, save=False)

# Get Theme Color
try:
    # Windows Only
    if sys.platform == "win32":
        import ctypes
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

    elif sys.platform == "darwin":  # macOS Only
        # 咱就是说为什么苹果要把开发者文档做成英文，出个中文版不好吗？
        # TM的让我找得好苦…… - By YHX (#17)
        import objc # PyObjC
        from Foundation import NSBundle

        # 加载AppKit框架
        AppKit = NSBundle.bundleWithIdentifier_('com.apple.AppKit')

        # 获取NSColor类
        NSColor = AppKit.classNamed_('NSColor')
        NSColorSpace = AppKit.classNamed_('NSColorSpace')

        # 获取当前主题色
        color = NSColor.controlAccentColor() #md就是这个API让我找了好久……
        # 欸，这时还不能用，因为现在这是NSColor Catalog color，还要转换！
        color = color.colorUsingColorSpace_(NSColorSpace.sRGBColorSpace())
        # 获取颜色的 RGB 分量, 并将颜色分量转换为 0-255 范围
        r, g, b = int(color.redComponent() * 255), int(color.greenComponent() * 255), int(color.blueComponent() * 255)

        setThemeColor(QColor(r, g, b), save=False)

except Exception as e:
    logger.error(f"Cannot get theme color: {e}")
    
# create main window
w = MainWindow()

# loading plugins
pluginsPath=os.path.join(cfg.appPath, "plugins")
loadPlugins(w, pluginsPath)

try:  # 静默启动
    if "--silence" in sys.argv:
        w.hide()
except:
    w.show()

sys.exit(app.exec())
