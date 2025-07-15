# coding:utf-8

import os
import sys

# --- Allow Ctrl+C to stop the PyQt application (SIGINT handler) ---
import signal
def _sigint_handler(signum, frame):
    print("\nCtrl+C pressed, exiting...")
    sys.exit(0)
signal.signal(signal.SIGINT, _sigint_handler)

from qfluentwidgets import qconfig

# noinspection PyUnresolvedReferences
from app.common import monkey_patch
from app.common.application import SingletonApplication
from app.common.config import cfg

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

# noinspection PyUnresolvedReferences
import winrt._winrt_windows_foundation  # 修复 Nuitka 编译后 Windows 不显示弹窗的问题

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

w = MainWindow(silence=True if "--silence" in sys.argv else False)

# loading plugins
pluginsPath=os.path.join(cfg.appPath, "plugins")
loadPlugins(w, pluginsPath)

sys.exit(app.exec())
