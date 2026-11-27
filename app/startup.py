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


def syncTheme(colorScheme=None) -> bool:
    """在 ThemeMode.AUTO 下同步全局主题与样式表（即使主窗口未创建或已关闭）。"""
    import sys
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication
    from qfluentwidgets import Theme, qconfig
    from qfluentwidgets.common import style_sheet
    from app.config.cfg import cfg
    from app.view.components.labels import IconBodyLabel

    if cfg.themeMode.value != Theme.AUTO:
        return False

    target = None
    if colorScheme == Qt.ColorScheme.Dark:
        target = Theme.DARK
    elif colorScheme == Qt.ColorScheme.Light:
        target = Theme.LIGHT

    if target is None and sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            ) as key:
                value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            target = Theme.DARK if int(value) == 0 else Theme.LIGHT
        except OSError:
            pass

    if target is None:
        app = QGuiApplication.instance()
        scheme = app.styleHints().colorScheme() if app is not None else Qt.ColorScheme.Unknown
        if scheme == Qt.ColorScheme.Dark:
            target = Theme.DARK
        elif scheme == Qt.ColorScheme.Light:
            target = Theme.LIGHT
        else:
            target = Theme.LIGHT

    prevTheme = qconfig.theme
    installedKey = getattr(style_sheet, "_installedKey", None)
    needsQssSync = installedKey is not None and installedKey[0] != target
    if prevTheme == target and not needsQssSync:
        return False

    qconfig.theme = target
    if prevTheme != target:
        qconfig.themeChanged.emit(qconfig.theme)
    style_sheet.updateStyleSheet()
    qconfig.themeChangedFinished.emit()
    IconBodyLabel.clearCache()
    return True


def setupThemeSync(application: Application) -> None:
    application.styleHints().colorSchemeChanged.connect(syncTheme)
    syncTheme()


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
    if not cfg.shouldCheckUpdateAtStartup.value:
        return
    updateService.check()

