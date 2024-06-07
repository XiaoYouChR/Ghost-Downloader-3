# coding:utf-8
import ctypes
import sys

import darkdetect

# noinspection PyUnresolvedReferences
import Res_rc

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication
from qfluentwidgets import setTheme, Theme, setThemeColor

from app.view.main_window import MainWindow


# create application
app = QApplication(sys.argv)
app.setAttribute(Qt.AA_DontCreateNativeWidgetSiblings)

# Enable Theme
setTheme(Theme.DARK if darkdetect.isDark() else Theme.LIGHT)

# Get Theme Color
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

    setThemeColor(QColor(r, g, b))

except Exception as e:
    print("获取主题色失败", e)

# create main window
w = MainWindow()

w.show()

sys.exit(app.exec())
