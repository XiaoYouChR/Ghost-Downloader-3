import os
import sys

from PySide6.QtCore import QStandardPaths

from qfluentwidgets import qconfig

from app.supports.application import SingletonApplication
from app.supports.config import cfg

appLocalDataLocation = QStandardPaths.standardLocations(QStandardPaths.StandardLocation.AppLocalDataLocation)[0]

qconfig.load(f"{appLocalDataLocation}/GhostDownloader/UserConfig.json", cfg)

if cfg.get(cfg.dpiScale) != 0:
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"
    os.environ["QT_SCALE_FACTOR"] = str(cfg.get(cfg.dpiScale))

application = SingletonApplication(sys.argv, "gd3")

# --- Start Program ---
from loguru import logger
import time
import warnings

from app.supports.config import VERSION
from app.view.windows.main_window import MainWindow
# noinspection PyUnresolvedReferences
import app.assets.resources

logger.add(f"{appLocalDataLocation}/GhostDownloader/GhostDownloader.log", rotation="512 KB", enqueue=True)
logger.info(f"Ghost Downloader v{VERSION} is Launched at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))}")
warnings.warn = logger.warning

mainWindow = MainWindow(silent = "silent" in sys.argv)

sys.exit(application.exec())
