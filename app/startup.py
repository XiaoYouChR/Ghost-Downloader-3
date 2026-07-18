"""Shared engine startup, binding, and shutdown for desktop and Android."""
from __future__ import annotations


def loadTranslation(application) -> None:
    from PySide6.QtCore import QTranslator
    from app.config.cfg import cfg

    import app.assets.resources  # noqa: F401

    previous = getattr(application, "_gd3Translator", None)
    if previous is not None:
        application.removeTranslator(previous)

    locale = cfg.language.value.value
    translator = QTranslator(application)
    translator.load(locale, "gd3", ".", ":/i18n")
    application.installTranslator(translator)
    application._gd3Translator = translator


def loadEngine(application) -> None:
    from app.services.coroutine_runner import coroutineRunner

    loadTranslation(application)
    coroutineRunner.start()


def loadPacks() -> None:
    from app.models.pack import PackConfig
    from app.services.feature_service import featureService

    featureService.load()
    PackConfig.load()


def startEngine() -> None:
    from app.services.feature_service import featureService
    from app.services.speed_meter import speedMeter
    from app.services.task_service import taskService

    taskService.taskStarted.connect(lambda _: speedMeter.start())
    taskService.tasksAllCompleted.connect(speedMeter.stop)
    taskService.resumeSaved()
    featureService.start()


def bindNotifications(notifyCompleted, notifyDiskSpace) -> None:
    from app.services.task_service import taskService
    taskService.taskCompleted.connect(notifyCompleted)
    taskService.diskSpaceInsufficient.connect(notifyDiskSpace)


def checkUpdateAtStartup() -> None:
    from app.config.cfg import cfg
    if not cfg.shouldCheckUpdateAtStartup.value:
        return
    from app.services.coroutine_runner import coroutineRunner
    from app.signal_bus import signalBus
    from app.update import fetchRelease, isOutdated

    def _onFetched(release):
        if isOutdated(release):
            signalBus.updateAvailable.emit(release)

    coroutineRunner.submit(fetchRelease(), done=_onFetched)


def stopEngine() -> None:
    from app.services.aria2_rpc import aria2RpcServer
    from app.services.browser_service import browserService
    from app.services.coroutine_runner import coroutineRunner
    from app.services.feature_service import featureService
    from app.services.task_service import taskService

    taskService.stop()
    taskService.flush()
    browserService.stop()
    aria2RpcServer.stop()
    featureService.stop()
    coroutineRunner.stop()
