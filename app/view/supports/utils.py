# Get Theme Color， 上游仅支持 Windows 和 macOS
import os
import sys

from PySide6.QtGui import QColor
from qfluentwidgets import setThemeColor
from qframelesswindow.utils import getSystemAccentColor


def setAppColor(color: QColor = None):
    if color is None or not isinstance(color, QColor):
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
    
    else:
        setThemeColor(color, save=False)