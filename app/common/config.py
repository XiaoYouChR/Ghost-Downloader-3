# coding:utf-8
import sys
from enum import Enum

from PySide6.QtCore import QDir
from qfluentwidgets import (qconfig, QConfig, ConfigItem, OptionsConfigItem, BoolValidator,
                            OptionsValidator, RangeConfigItem, RangeValidator,
                            FolderListValidator, Theme, FolderValidator, ConfigValidator, ColorConfigItem,
                            EnumSerializer)




class Config(QConfig):
    """ Config of application """
    # download
    maxReassignSize = RangeConfigItem("Download", "MaxReassignSize", 15, RangeValidator(1, 100))
    downloadFolder = ConfigItem(
        "Download", "DownloadFolder", QDir.currentPath(), FolderValidator())

    maxBlockNum = RangeConfigItem("Download", "MaxBlockNum", 32, RangeValidator(1, 256))
    # browser
    enableBrowserExtension = ConfigItem("Browser", "EnableBrowserExtension", False, BoolValidator())

    # main window
    dpiScale = OptionsConfigItem(
        "MainWindow", "DpiScale", "Auto", OptionsValidator([1, 1.25, 1.5, 1.75, 2, "Auto"]), restart=True)

    # software update
    checkUpdateAtStartUp = ConfigItem("Update", "CheckUpdateAtStartUp", True, BoolValidator())


YEAR = 2024
AUTHOR = "XiaoYouChR"
VERSION = "3.3.0"
AUTHOR_URL = "https://space.bilibili.com/437313511"
FEEDBACK_URL = "https://github.com/XiaoYouChR/Ghost-Downloader-3/issues"
# RELEASE_URL = "https://github.com/XiaoYouChR/Ghost-Downloader-3/releases/latest"


cfg = Config()
qconfig.load('./Ghost Downloader 配置文件.json', cfg)