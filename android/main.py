"""Ghost Downloader 3 —— Android 运行时入口, 复刻桌面 Ghost-Downloader-3.py 的启动序列。"""

import sys


def _installOrjsonShim() -> None:
    """用 stdlib json 顶替 orjson(无 Android wheel), 必须在任何 `import orjson` 之前注册。"""
    import json
    import types

    shim = types.ModuleType("orjson")

    def dumps(obj, *_args, **_kwargs) -> bytes:
        # 对齐 orjson.dumps: UTF-8 bytes、紧凑、非 ASCII 不转义
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    def loads(data):
        return json.loads(data)

    shim.dumps = dumps
    shim.loads = loads
    sys.modules["orjson"] = shim


_installOrjsonShim()

import os

# 切后台不挂起事件循环(否则 QWebSocketServer + 限速 QTimer 全停)由 manifest background_running=true 实现(见 Dockerfile)
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


# enqueue=False: Android bionic 无 sem_open, enqueue=True 走的 multiprocessing.SimpleQueue 会 ImportError。
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

# 须在 MainWindow 构造前: 此后任何 Theme.AUTO 解析才会读到正确的系统深浅。
from app.view.mobile.setup import (
    setupAndroidMenuEmbedding,
    setupCollapsibleGroupTouch,
    setupFluentIconRendering,
    setupMobileDialogWidth,
    setupNativeDialogPaths,
    setupSystemFont,
    setupSystemTheme,
    setupTouchScrolling,
)
setupSystemTheme()
setupSystemFont()
setupFluentIconRendering()
setupNativeDialogPaths()
setupMobileDialogWidth()
setupCollapsibleGroupTouch()
setupAndroidMenuEmbedding()

# 主线程预热 lru_cache: ffmpegPaths() 等在 coreService 后台线程被调, 而 jnius autoclass 后台取不到 classloader
from app.supports.android import nativeLibraryDir as _preloadNativeLibDir
_preloadNativeLibDir()

import warnings
from PySide6.QtCore import Qt, QTranslator

from app.view.mobile.window import MobileMainWindow
from app.services.task_service import taskService
# noinspection PyUnresolvedReferences
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

requestNotificationPermission()  # Android 13+ 运行时弹 POST_NOTIFICATIONS, 否则通知被静默丢弃
requestIgnoreBatteryOptimizations()  # 跳电池优化豁免, 逃 Doze 后台限制(已豁免则静默)
# 浏览器扩展服务开启即须保活(随时接受扩展连接), 与下载各占一个保活理由, 引用计数互不踩
cfg.enableBrowserExtension.valueChanged.connect(lambda enabled: keepAlive.setReason("browser", bool(enabled)))
keepAlive.setReason("browser", cfg.enableBrowserExtension.value)

# 保活/测速由每秒 globalSpeedChanged(主线程可靠)驱动; 不走 coreService 跨线程信号(asyncio→plain slot 投递不可靠)
from app.supports.signal_bus import signalBus


def _onGlobalSpeedChanged(speed: int) -> None:
    downloading = bool(coreService.runningTasks)
    keepAlive.setWakeLock(downloading)
    keepAlive.setReason("download", downloading)
    keepAlive.updateSpeed(speed)


signalBus.globalSpeedChanged.connect(_onGlobalSpeedChanged)


def _onApplicationStateChanged(state: Qt.ApplicationState) -> None:
    # 主循环后台仍跑, 但挂起态绘制可能崩(eglSurface 敏感); 挂起禁重绘, 恢复再开
    if state == Qt.ApplicationState.ApplicationSuspended:
        mainWindow.setUpdatesEnabled(False)
    elif state == Qt.ApplicationState.ApplicationActive:
        mainWindow.setUpdatesEnabled(True)
        mainWindow.update()


application.applicationStateChanged.connect(_onApplicationStateChanged)

application.aboutToQuit.connect(coreService.stop)
application.aboutToQuit.connect(taskService.flushNow)

sys.exit(application.exec())
