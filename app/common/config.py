# coding:utf-8

from PySide6.QtCore import QDir
from PySide6.QtWidgets import QApplication
from loguru import logger
from qfluentwidgets import (qconfig, QConfig, ConfigItem, OptionsConfigItem, BoolValidator,
                            OptionsValidator, RangeConfigItem, RangeValidator,
                            FolderValidator)
import os,sys
currentpath=os.path.dirname(sys.argv[0])
appDir=sys.argv[0]


class Config(QConfig):
    """ Config of application """
    # main executable
    path=ConfigItem("MainExecutable", "Path", appDir, restart=True)
    # download
    maxReassignSize = RangeConfigItem("Download", "MaxReassignSize", 15, RangeValidator(1, 100))
    downloadFolder = ConfigItem(
        "Download", "DownloadFolder", QDir.currentPath(), FolderValidator())

    maxBlockNum = RangeConfigItem("Download", "MaxBlockNum", 32, RangeValidator(1, 256))
    # browser
    enableBrowserExtension = ConfigItem("Browser", "EnableBrowserExtension", False, BoolValidator(), restart=True)

    # main window
    dpiScale = OptionsConfigItem(
        "MainWindow", "DpiScale", "Auto", OptionsValidator([1, 1.25, 1.5, 1.75, 2, "Auto"]), restart=True)

    # software
    checkUpdateAtStartUp = ConfigItem("Software", "CheckUpdateAtStartUp", True, BoolValidator())
    autoRun = ConfigItem("Software", "AutoRun", False, BoolValidator())


YEAR = 2024
AUTHOR = "XiaoYouChR"
VERSION = "3.3.3"
AUTHOR_URL = "https://space.bilibili.com/437313511"
FEEDBACK_URL = "https://github.com/XiaoYouChR/Ghost-Downloader-3/issues"
# RELEASE_URL = "https://github.com/XiaoYouChR/Ghost-Downloader-3/releases/latest"


cfg = Config()
try:
    qconfig.load('{}/Ghost Downloader 配置文件.json'.format(currentpath), cfg)
except Exception as e:
    logger.error(e)
