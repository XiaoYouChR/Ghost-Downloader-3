# coding:utf-8
import sys

from PySide6.QtCore import Qt, QSharedMemory, QDir
from PySide6.QtWidgets import QApplication

import ctypes
import os

currentpath=os.path.dirname(sys.argv[0])
currentuser=os.getlogin()
# macOS实测有时VS Code中终端用户为root，所以请在默认终端中运行，不然会报错
# Microsoft出来讨个说法！

print(sys.argv, currentpath, currentuser)

import time
import warnings

import darkdetect

from PySide6.QtGui import QColor

from loguru import logger
from qfluentwidgets import setTheme, Theme, setThemeColor

# noinspection PyUnresolvedReferences
import Res_rc
from app.common.config import cfg
from app.common.methods import loadPlugins
from app.view.main_window import MainWindow

# create application
app = QApplication(sys.argv)
app.setAttribute(Qt.AA_DontCreateNativeWidgetSiblings)

try:
    with open('{}/Ghost Downloader 配置文件.json'.format(currentpath), 'r'):
        pass
except FileNotFoundError: # 如果配置文件不存在，就直接“偷梁换柱”
    # 设置默认下载路径
    if sys.platform == "win32":
        downloadPath=os.path.join('C:\\Users', currentuser, 'Downloads')
    elif sys.platform == "darwin": # macOS
        downloadPath=os.path.join('/Users', currentuser, 'Downloads')
    else: # 其他平台？（不确定）
        downloadPath=os.path.expanduser('~/Downloads')

    cfg.downloadFolder.value=downloadPath # 舒服～


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
# logger.add("Ghost Downloader 运行日志.log", rotation="512 KB")
logger.add('{}/Ghost Downloader 运行日志.log'.format(currentpath))
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
        # 获取颜色的 RGB 分量
        red = color.redComponent()
        green = color.greenComponent()
        blue = color.blueComponent()

        # 将颜色分量转换为 0-255 范围
        red = int(red * 255)
        green = int(green * 255)
        blue = int(blue * 255)

        setThemeColor(QColor(red, green, blue), save=False)
except Exception as e:
    logger.error(f"Cannot get theme color: {e}")
    
# create main window
w = MainWindow()

# loading plugins
if sys.platform=='win32':
    pluginsPath=os.path.join(app.applicationDirPath(), "plugins")
elif sys.platform=='darwin':#逆天 macOS，将可执行文件藏在 .app/Contents/MacOS/ 下，要特殊处理
    execuableDir=currentpath.replace("/Contents/MacOS","/Contents")
    pluginsPath=os.path.join(execuableDir, "plugins")
else: # 不确定 Linux 下是不是这样，按照 Windows 相同方式处理
    pluginsPath=os.path.join(app.applicationDirPath(), "plugins")
# pluginsPath=("./plugins")
loadPlugins(w, pluginsPath)

try:  # 静默启动
    if sys.argv[1] == "--silence":
        w.hide()
except:
    w.show()

sys.exit(app.exec())
