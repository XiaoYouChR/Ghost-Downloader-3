import os
import sys
import traceback
from time import localtime, strftime, time

from loguru import logger
from PySide6.QtCore import QStandardPaths

# import orjson
# sys.modules['json'] = orjson

exceptionSignalBus = None

def exceptionHook(exceptionType, value, tb):
    exceptionInfo = (exceptionType, value, tb)
    message = "".join(traceback.format_exception(*exceptionInfo)).rstrip()
    logger.opt(exception=exceptionInfo).error("Unhandled application exception")

    if exceptionSignalBus is not None:
        try:
            exceptionSignalBus.catchException.emit(message)
        except Exception as error:
            logger.opt(exception=error).warning("Failed to emit application exception signal")

    if "__compiled__" not in globals():
        sys.__excepthook__(*exceptionInfo)

appLocalDataLocation = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.GenericDataLocation)
logger.add(f"{appLocalDataLocation}/GhostDownloader/GhostDownloader.log", rotation="512 KB", enqueue=True)
sys.excepthook = exceptionHook

from qfluentwidgets import qconfig
from app.supports.application import SingletonApplication
from app.supports.config import VERSION, cfg
from app.supports.signal_bus import signalBus as exceptionSignalBus

logger.info(
    "Ghost Downloader v{} is launched at {}",
    VERSION,
    strftime("%Y-%m-%d %H:%M:%S", localtime(time())),
)

qconfig.load(f"{appLocalDataLocation}/GhostDownloader/UserConfig.json", cfg)

if cfg.get(cfg.dpiScale) != 0:
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"
    os.environ["QT_SCALE_FACTOR"] = str(cfg.get(cfg.dpiScale))

application = SingletonApplication(sys.argv, "gd3")

# --- Start Program ---
import warnings
from PySide6.QtCore import QTranslator

from app.view.windows.main_window import MainWindow
from app.supports.recorder import taskRecorder
# noinspection PyUnresolvedReferences
import app.assets.resources
from app.services.core_service import coreService
from app.services.feature_service import featureService

warnings.warn = logger.warning

# internationalization
locale = cfg.language.value.value
translator = QTranslator()
translator.load(locale, "gd3", ".", ":/i18n")
application.installTranslator(translator)

isSilently = "--silence" in sys.argv
coreService.start()
mainWindow = MainWindow(isSilently)
featureService.loadFeatures(mainWindow)
taskRecorder.load()
mainWindow.taskPage.resumeMemorizedTasks()
mainWindow.syncThemeColor()

if not isSilently:
    mainWindow.splashScreen.finish()

application.aboutToQuit.connect(coreService.stop)
application.aboutToQuit.connect(taskRecorder.flush)

sys.exit(application.exec())
