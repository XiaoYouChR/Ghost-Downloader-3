# coding:utf-8

import os
import sys
import signal  # 添加 signal 模块
import threading  # 添加 threading 模块

from qfluentwidgets import qconfig

from app.common.application import SingletonApplication
from app.common.config import cfg

# 创建全局退出事件
global_shutdown_event = threading.Event()

# 信号处理函数
def signal_handler(sig, frame):
    print("\n程序终止请求")
    global_shutdown_event.set()
    # 等待一段时间让线程退出
    app.quit()  # 优雅退出应用程序

# 设置信号处理
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# 设置程序运行路径, 便于调试
if not "__compiled__" in globals():  # 调试时候使用相对路径
    cfg.appPath = "./"
    qconfig.load('./Ghost Downloader 配置文件.json', cfg)
else:  # 编译后
    cfg.appPath = os.path.dirname(sys.executable)
    qconfig.load('{}/Ghost Downloader 配置文件.json'.format(os.path.dirname(sys.executable)), cfg)

# 必须在 QApplication 创建前设置缩放比例
if cfg.get(cfg.dpiScale) != 0:
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"
    os.environ["QT_SCALE_FACTOR"] = str(cfg.get(cfg.dpiScale))

app = SingletonApplication(sys.argv, "Ghost Downloader")

# 在应用程序中设置全局退出事件
app.global_shutdown_event = global_shutdown_event

# Starting Program
import time
import warnings

from PySide6.QtCore import QTimer, QTranslator
from PySide6.QtGui import QColor
from loguru import logger
from qframelesswindow.utils import getSystemAccentColor
from qfluentwidgets import setTheme, Theme, setThemeColor

# noinspection PyUnresolvedReferences
import resources.Res_rc

from app.common.methods import loadPlugins
from app.view.main_window import MainWindow

# 防止 Mica 背景失效
# app.setAttribute(Qt.AA_DontCreateNativeWidgetSiblings)

# config loguru
logger.add('{}/Ghost Downloader 运行日志.log'.format(cfg.appPath), rotation="512 KB")
logger.info(f"Ghost Downloader is launched at {time.time_ns()}")

warnings.warn = logger.warning

# internationalization
locale = cfg.language.value.value
translator = QTranslator()
translator.load(locale, "gd3", ".", ":/i18n")
app.installTranslator(translator)

# Enable Theme
if cfg.customThemeMode.value == "System":
    setTheme(Theme.AUTO, save=False)
elif cfg.customThemeMode.value == "Light":
    setTheme(Theme.LIGHT, save=False)
else:
    setTheme(Theme.DARK, save=False)

# Get Theme Color， 上游仅支持 Windows 和 macOS
if sys.platform == "win32" or "darwin":
    setThemeColor(getSystemAccentColor(), save=False)
if sys.platform == "linux":

    if 'KDE_SESSION_UID' in os.environ:  # KDE Plasma

        import configparser
        config = configparser.ConfigParser()

        config.read(f"/home/{os.getlogin()}/.config/kdeglobals")

        # 获取 DecorationFocus 的值
        if 'Colors:Window' in config:
            color = list(map(int, config.get('Colors:Window', 'DecorationFocus').split(",")))
            setThemeColor(QColor(*color))

# create SpeedLimiter
speedLimiter = QTimer()  # 限速器
speedLimiter.setInterval(1000)  # 一秒刷新一次
speedLimiter.timeout.connect(cfg.resetGlobalSpeed)  # 刷新 globalSpeed为 0
speedLimiter.start()

# 在应用程序退出时停止定时器
app.aboutToQuit.connect(speedLimiter.stop)

# create main window
w = MainWindow()

# 在主窗口中也设置全局退出事件
w.global_shutdown_event = global_shutdown_event

# loading plugins
pluginsPath=os.path.join(cfg.appPath, "plugins")
loadPlugins(w, pluginsPath)

try:  # 静默启动
    if "--silence" in sys.argv:
        w.hide()
except:
    w.show()

sys.exit(app.exec())