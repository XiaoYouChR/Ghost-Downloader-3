from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.engine import Engine
    from app.platform.application import Application
    from app.services.coroutine_runner import CoroutineRunner
    from app.services.feature_service import FeatureService
    from app.services.speed_meter import SpeedMeter
    from app.services.update_service import UpdateService


def loadResources(application: Application) -> None:
    from PySide6.QtCore import QResource
    from qfluentwidgets import load as loadQFluentWidgets
    from app.config.paths import EXECUTABLE_DIR

    loadQFluentWidgets(application)
    QResource.registerResource(str(EXECUTABLE_DIR / "app" / "assets" / "resources.rcc"))
    loadTranslators(application)


def loadTranslators(application: Application) -> None:
    from PySide6.QtCore import QLocale, QTranslator, Qt
    from app.config.cfg import cfg

    translator = QTranslator(application)
    if cfg.language.value not in cfg.language.options:
        cfg.language.value = "Auto"

    def setLocale():
        localeName = cfg.language.value
        locale = QLocale() if localeName == "Auto" else QLocale(localeName)
        application.removeTranslator(translator)
        application.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        if locale.name() != "zh_CN":
            if translator.load(locale, "gd3", ".", ":/i18n") or translator.load("gd3.en_US", ":/i18n"):
                application.installTranslator(translator)
                application.setLayoutDirection(QLocale(translator.language()).textDirection())

    setLocale()
    cfg.language.valueChanged.connect(setLocale)


def setupThemeColor(application: Application) -> None:
    import sys
    from PySide6.QtGui import QPalette
    from qfluentwidgets import setThemeColor
    from app.config.cfg import cfg

    # Issue #1054
    role = QPalette.ColorRole.Highlight if sys.platform == "win32" else QPalette.ColorRole.Accent

    def refresh() -> None:
        color = application.palette().color(QPalette.ColorGroup.Active, role)
        if color != cfg.themeColor.value:
            setThemeColor(color, save=False)

    refresh()
    application.systemPaletteChanged.connect(refresh)


def createEngine(application: Application) -> Engine:
    import sys
    from PySide6.QtCore import QFileSystemWatcher, QTimer
    from shiboken6 import isValid
    from app.engine import Engine
    from app.config.paths import APP_DATA_DIR
    from app.platform.desktop import deleteRecoverably, loadCrx
    from app.services.coroutine_runner import CoroutineRunner

    if sys.platform == "win32":
        from winloop import new_event_loop
    else:
        from uvloop import new_event_loop

    coroutineRunner = CoroutineRunner(
        lambda fn: QTimer.singleShot(0, application, fn), isAlive=isValid,
        loop=new_event_loop(),
    )
    coroutineRunner.start()
    return Engine(coroutineRunner, QFileSystemWatcher(), loadCrx, APP_DATA_DIR / "browser_extension",
                  deleteRecoverably)


def deleteBackupDir() -> None:
    import shutil
    from app.config.paths import APP_DIR

    if "__compiled__" not in globals():
        return
    backupDir = APP_DIR.parent / f"{APP_DIR.name}_backup"
    if backupDir.is_dir():
        shutil.rmtree(backupDir, ignore_errors=True)


def loadPacks(featureService: FeatureService, coroutineRunner: CoroutineRunner, speedMeter: SpeedMeter) -> None:
    from app.models.pack import PackServices
    from app.services.update_service import installPendingPacks
    from app.config.paths import FEATURES_DIR, SEED_FEATURES_DIR
    from app.loader import seedPacks

    installPendingPacks(FEATURES_DIR)
    seedPacks(SEED_FEATURES_DIR, FEATURES_DIR)

    services = PackServices(
        coroutineRunner=coroutineRunner,
        speedMeter=speedMeter,
    )
    featureService.load(services)


def checkUpdateAtStartup(updateService: UpdateService) -> None:
    from app.config.cfg import cfg
    from app.config.paths import IS_COMPILED, hasNoAutoUpdateMarker

    if hasNoAutoUpdateMarker():
        from loguru import logger
        logger.info("Auto update disabled by gd_no_auto_update marker")
        if cfg.shouldCheckUpdateAtStartup.value:
            cfg.set(cfg.shouldCheckUpdateAtStartup, False)
        return
    if not IS_COMPILED:
        return
    if not cfg.shouldCheckUpdateAtStartup.value:
        return
    updateService.check()
