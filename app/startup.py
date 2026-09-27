"""桌面端独有的启动阶段：创建 Engine、加载翻译与 pack、启动时检查更新。"""
from __future__ import annotations


def loadTranslators(application):
    from PySide6.QtCore import QLocale, QTranslator
    from app.config.cfg import cfg

    translator = QTranslator(application)

    def setLocale():
        localeName = cfg.language.value.value
        locale = QLocale() if localeName == "Auto" else QLocale(localeName)
        application.removeTranslator(translator)
        if locale.name() != "zh_CN":
            if translator.load(locale, "gd3", ".", ":/i18n") or translator.load("gd3.en_US", ":/i18n"):
                application.installTranslator(translator)

    setLocale()
    cfg.language.valueChanged.connect(setLocale)


def createEngine(application):
    import sys
    from PySide6.QtCore import QFileSystemWatcher, QResource, QTimer
    from shiboken6 import isValid
    from app.config.paths import EXECUTABLE_DIR
    from app.engine import Engine
    from app.platform.desktop import loadCrx
    from app.services.coroutine_runner import CoroutineRunner

    QResource.registerResource(str(EXECUTABLE_DIR / "app" / "assets" / "resources.rcc"))

    loadTranslators(application)

    if sys.platform == "win32":
        from winloop import new_event_loop
    else:
        from uvloop import new_event_loop

    coroutineRunner = CoroutineRunner(
        lambda fn: QTimer.singleShot(0, application, fn), isAlive=isValid,
        loop=new_event_loop(),
    )
    coroutineRunner.start()
    return Engine(coroutineRunner, QFileSystemWatcher(), loadCrx)


def loadPacks(featureService, coroutineRunner, speedMeter):
    from app.models.pack import PackConfig, PackServices
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
    PackConfig.load()


def checkUpdateAtStartup(updateService):
    from app.config.cfg import cfg
    if not cfg.shouldCheckUpdateAtStartup.value:
        return
    updateService.check()
