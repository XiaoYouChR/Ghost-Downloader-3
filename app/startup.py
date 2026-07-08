"""Shared engine startup, binding, and shutdown for desktop and Android."""
from __future__ import annotations


def loadEngine(application) -> None:
    from PySide6.QtCore import QTranslator
    from app.config.cfg import cfg
    from app.services.coroutine_runner import coroutineRunner

    import app.assets.resources  # noqa: F401

    locale = cfg.language.value.value
    translator = QTranslator(application)
    translator.load(locale, "gd3", ".", ":/i18n")
    application.installTranslator(translator)

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

    # 清理上次遗留的更新文件
    _cleanupUpdateDirectory()


def _cleanupUpdateDirectory() -> None:
    """清理 update 目录中的临时文件"""
    from pathlib import Path
    from app.config.paths import UPDATE_DIR
    from loguru import logger

    updatePath = Path(UPDATE_DIR)
    if not updatePath.exists():
        return

    try:
        import shutil
        shutil.rmtree(updatePath, ignore_errors=True)
        updatePath.mkdir(parents=True, exist_ok=True)
        logger.info("Cleaned up update directory: {}", UPDATE_DIR)
    except Exception as e:
        logger.opt(exception=e).warning("Failed to clean update directory")


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


def checkRuntimeUpdatesAtStartup() -> None:
    """在启动时检查所有运行时的状态

    这个函数会刷新所有 BinaryRuntime 的版本信息，
    为用户提供最新的运行时状态。
    """
    from app.config.cfg import cfg
    if not cfg.shouldCheckUpdateAtStartup.value:
        return

    from app.services.feature_service import featureService
    from app.services.runtime_status import runtimeStatusService
    from loguru import logger

    runtimes = featureService.runtimes()
    if not runtimes:
        return

    logger.info(f"Checking {len(runtimes)} runtime(s) at startup")

    for runtime in runtimes:
        if runtime.canInstall:
            # 刷新运行时状态（异步探测版本）
            runtimeStatusService.refresh(runtime, force=False)


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

    # 退出时再次清理更新目录
    _cleanupUpdateDirectory()
