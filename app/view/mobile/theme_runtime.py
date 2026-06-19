def setSystemTheme() -> None:
    import darkdetect
    from qfluentwidgets import setTheme

    from app.supports.android import isSystemDark
    from app.supports.config import cfg, toQFluentTheme

    def themeName() -> str:
        return "Dark" if isSystemDark() else "Light"

    darkdetect.theme = themeName
    darkdetect.isDark = isSystemDark
    setTheme(toQFluentTheme(cfg.customThemeMode.value), save=False)

def setSystemFont() -> None:
    from pathlib import Path

    from loguru import logger
    from PySide6.QtGui import QFontDatabase
    from qfluentwidgets import qconfig

    candidates = [
        ("MiSans VF", "/system/fonts/MiSansVF.ttf"),
        ("MiSans", "/system/fonts/MiSans-Regular.ttf"),
        ("OPPO Sans", "/system/fonts/OPPOSans.ttf"),
        ("OplusSans", "/system/fonts/OplusSans3.0.ttf"),
        ("HarmonyOS Sans SC", "/system/fonts/HarmonyOS_Sans_SC_Regular.ttf"),
        ("vivo Sans", "/system/fonts/VivoFont.ttf"),
    ]
    families = set(QFontDatabase.families())

    picked = None
    for name, path in candidates:
        if name in families:
            picked = name
            break
        if Path(path).exists():
            loaded = QFontDatabase.applicationFontFamilies(QFontDatabase.addApplicationFont(path))
            if loaded:
                picked = loaded[0]
                break

    logger.info("系统字体: {}", picked or "Roboto(未识别 OEM 字体, 回退)")
    qconfig.set(qconfig.fontFamilies, [picked, "sans-serif"] if picked else ["sans-serif"], save=False)
