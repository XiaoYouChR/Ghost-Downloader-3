import sys

def _installOrjsonShim() -> None:
    import json
    import types

    shim = types.ModuleType("orjson")

    def dumps(obj, *_args, **_kwargs) -> bytes:
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    def loads(data):
        return json.loads(data)

    shim.dumps = dumps
    shim.loads = loads
    sys.modules["orjson"] = shim

_installOrjsonShim()

import os

import traceback
from pathlib import Path
from time import localtime, strftime, time

from loguru import logger

from app.supports.paths import APP_DATA_DIR

Path(APP_DATA_DIR).mkdir(parents=True, exist_ok=True)

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

logger.add(f"{APP_DATA_DIR}/GhostDownloader.log", rotation="512 KB", enqueue=False)
sys.excepthook = exceptionHook

from qfluentwidgets import qconfig
from app.supports.application import SingletonApplication
from app.supports.config import VERSION, cfg
from app.supports.signal_bus import signalBus as exceptionSignalBus

logger.info(
    "Ghost Downloader v{} (Android) is launched at {}",
    VERSION,
    strftime("%Y-%m-%d %H:%M:%S", localtime(time())),
)

qconfig.load(f"{APP_DATA_DIR}/UserConfig.json", cfg)

if cfg.get(cfg.dpiScale) != 0:
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"
    os.environ["QT_SCALE_FACTOR"] = str(cfg.get(cfg.dpiScale))

application = SingletonApplication(sys.argv, "gd3")

from app.view.mobile.dialog_patch import patchFileDialogs, patchMessageBoxWidth
from app.view.mobile.fluent_patch import patchAndroidMenus, patchFluentIconRendering
from app.view.mobile.theme_runtime import setSystemFont, setSystemTheme
from app.view.mobile.touch_runtime import patchCollapsibleGroupTouch, setupTouchScrolling
setSystemTheme()
setSystemFont()
patchFluentIconRendering()
patchFileDialogs()
patchMessageBoxWidth()
patchCollapsibleGroupTouch()
patchAndroidMenus()

from app.supports.android import nativeLibraryDir as _preloadNativeLibDir
_preloadNativeLibDir()

import warnings
from PySide6.QtCore import Qt, QTranslator

from app.view.mobile.window import MobileMainWindow
from app.services.task_service import taskService

import app.assets.resources
from app.services.core_service import coreService
from app.services.feature_service import featureService

warnings.warn = logger.warning

locale = cfg.language.value.value
translator = QTranslator()
translator.load(locale, "gd3", ".", ":/i18n")
application.installTranslator(translator)

coreService.start()

from app.supports.android_keepalive import keepAlive, requestIgnoreBatteryOptimizations
from app.supports.android_notification import requestNotificationPermission

mainWindow = MobileMainWindow()
featureService.load(mainWindow)
taskService.load()
mainWindow.taskPage.resumeMemorizedTasks()
mainWindow.updateThemeColor()
mainWindow.show()
setupTouchScrolling(mainWindow)

requestNotificationPermission()
requestIgnoreBatteryOptimizations()

cfg.enableBrowserExtension.valueChanged.connect(lambda enabled: keepAlive.setActiveReason("browser", bool(enabled)))
keepAlive.setActiveReason("browser", cfg.enableBrowserExtension.value)

from app.supports.signal_bus import signalBus

def _onGlobalSpeedChanged(speed: int) -> None:
    downloading = bool(coreService.runningTasks)
    keepAlive.setWakeLock(downloading)
    keepAlive.setActiveReason("download", downloading)
    keepAlive.updateSpeed(speed)

signalBus.globalSpeedChanged.connect(_onGlobalSpeedChanged)

def _onApplicationStateChanged(state: Qt.ApplicationState) -> None:
    if state == Qt.ApplicationState.ApplicationSuspended:
        mainWindow.setUpdatesEnabled(False)
    elif state == Qt.ApplicationState.ApplicationActive:
        mainWindow.setUpdatesEnabled(True)
        mainWindow.update()

application.applicationStateChanged.connect(_onApplicationStateChanged)

application.aboutToQuit.connect(featureService.shutdown)
application.aboutToQuit.connect(coreService.stop)
application.aboutToQuit.connect(taskService.flushNow)

sys.exit(application.exec())
