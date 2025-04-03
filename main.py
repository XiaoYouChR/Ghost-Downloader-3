# coding:utf-8

import os
# 创建 Application
import sys

from PySide6.QtWidgets import QApplication
from qfluentwidgets import qconfig

from app.common.config import cfg

# 设置程序运行路径, 便于调试
if "--debug" in sys.argv:  # 调试时候请使用相对路径！
    cfg.appPath = "./"
    qconfig.load('./Ghost Downloader 配置文件.json', cfg)
else:  # 编译后
    cfg.appPath = os.path.dirname(sys.executable)
    qconfig.load('{}/Ghost Downloader 配置文件.json'.format(os.path.dirname(sys.executable)), cfg)

    def exceptionHandler(type, value, traceback):  # 自定义错误捕捉函数
        logger.exception(f"意料之外的错误! {type}: {value}. Traceback: {traceback}")

    sys.excepthook = exceptionHandler

# 必须在 QApplication 创建前设置缩放比例
if cfg.get(cfg.dpiScale) == 0:
    pass
else:
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"
    os.environ["QT_SCALE_FACTOR"] = str(cfg.get(cfg.dpiScale))

app = QApplication(sys.argv)

# 检测程序重复运行
from PySide6.QtCore import QSharedMemory, QTimer

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
import time
import warnings

import darkdetect

from PySide6.QtGui import QColor

from loguru import logger
from qframelesswindow.utils import getSystemAccentColor

from qfluentwidgets import setTheme, Theme, setThemeColor

# noinspection PyUnresolvedReferences
import Res_rc

from app.common.methods import loadPlugins
from app.view.main_window import MainWindow

# 防止 Mica 背景失效
# app.setAttribute(Qt.AA_DontCreateNativeWidgetSiblings)

# config loguru
logger.add('{}/Ghost Downloader 运行日志.log'.format(cfg.appPath), rotation="512 KB")
logger.info(f"Ghost Downloader is launched at {time.time_ns()}")

warnings.warn = logger.warning

# Enable Theme
if cfg.customThemeMode.value == "System":
    setTheme(Theme.DARK if darkdetect.isDark() else Theme.LIGHT, save=False)
elif cfg.customThemeMode.value == "Light":
    setTheme(Theme.LIGHT, save=False)
else:
    setTheme(Theme.DARK, save=False)

# Get Theme Color
# try:
# 上游仅支持 Windows 和 macOS
if sys.platform == "win32" or "darwin":
    setThemeColor(getSystemAccentColor(), save=False)
if sys.platform == "linux":

    if 'KDE_SESSION_UID' in os.environ: # KDE Plasma

        import configparser
        config = configparser.ConfigParser()

        config.read(f"/home/{os.getlogin()}/.config/kdeglobals")

        # 获取 DecorationFocus 的值
        if 'Colors:Window' in config:
            color = list(map(int, config.get('Colors:Window', 'DecorationFocus').split(",")))
            setThemeColor(QColor(*color))

# except Exception as e:
#     logger.error(f"Cannot get theme color: {e}")

# create SpeedLimiter
speedLimiter = QTimer()  # 限速器
speedLimiter.setInterval(1000)  # 一秒刷新一次
speedLimiter.timeout.connect(cfg.resetGlobalSpeed)  # 刷新 globalSpeed为 0
speedLimiter.start()

# create main window, 加载插件在 mainWindow 中实现
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
