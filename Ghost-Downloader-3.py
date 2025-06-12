# coding:utf-8

import os
import sys

from qfluentwidgets import qconfig

from app.view.supports.application import SingletonApplication
from app.view.supports.config import cfg

# 设置程序运行路径, 便于调试
if not "__compiled__" in globals():  # 调试时候使用相对路径
    cfg.appPath = "./"
    qconfig.load('./gd3_config.json', cfg)
else:  # 编译后
    cfg.appPath = os.path.dirname(sys.executable)
    qconfig.load('{}/gd3_config.json'.format(os.path.dirname(sys.executable)), cfg)

# 必须在 QApplication 创建前设置缩放比例
if cfg.get(cfg.dpiScale) != 0:
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"
    os.environ["QT_SCALE_FACTOR"] = str(cfg.get(cfg.dpiScale))

application = SingletonApplication(sys.argv, "Ghost Downloader")

# Starting Program
import time
import warnings

from PySide6.QtCore import QTranslator
from PySide6.QtGui import QColor
from loguru import logger
from qfluentwidgets import setTheme, Theme, setThemeColor

# noinspection PyUnresolvedReferences
from app.assets import Res_rc
from app.view.supports.utils import setAppColor

# 防止 Mica 背景失效
# application.setAttribute(Qt.AA_DontCreateNativeWidgetSiblings)

# config loguru
logger.add('{}/gd3.log'.format(cfg.appPath), rotation="512 KB")
logger.info(f"Ghost Downloader is launched at {time.time_ns()}")

warnings.warn = logger.warning

# internationalization
locale = cfg.language.value.value
translator = QTranslator()
translator.load(locale, "gd3", ".", ":/i18n")
application.installTranslator(translator)

# Enable Theme
if cfg.customThemeMode.value == "System":
    setTheme(Theme.AUTO, save=False)
elif cfg.customThemeMode.value == "Light":
    setTheme(Theme.LIGHT, save=False)
else:
    setTheme(Theme.DARK, save=False)

if cfg.isColorDependsOnSystem.value:
    setAppColor()
else:
    setThemeColor(QColor(cfg.get(cfg.appColor.value)), save=False)

if "--silence" in sys.argv:
    w = mainWindow(silence=True)
else:
    w = mainWindow()

sys.exit(application.exec())
