import sys
import os

# import orjson
# sys.modules['json'] = orjson

from PySide6.QtCore import QStandardPaths

from qfluentwidgets import qconfig

from app.supports.application import SingletonApplication
from app.supports.config import cfg

appLocalDataLocation = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)

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
from app.supports.recorder import taskRecorder
# noinspection PyUnresolvedReferences
import app.assets.resources
from app.services.core_service import coreService
from app.services.feature_service import featureService
from niquests.packages import urllib3

logger.add(f"{appLocalDataLocation}/GhostDownloader/GhostDownloader.log", rotation="512 KB", enqueue=True)
logger.info(f"Ghost Downloader v{VERSION} is Launched at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))}")

urllib3.disable_warnings()
warnings.warn = logger.warning

isSilently = "silent" in sys.argv
coreService.start()
mainWindow = MainWindow(isSilently)
featureService.loadFeatures(mainWindow)
taskRecorder.load()
mainWindow.taskPage.resumeMemorizedTasks()
if not isSilently:
    mainWindow.splashScreen.finish()

application.aboutToQuit.connect(coreService.stop)
application.aboutToQuit.connect(taskRecorder.flush)

sys.exit(application.exec())
