import shutil
import sys
from pathlib import Path

from PySide6.QtCore import QStandardPaths

from app.platform.android import IS_ANDROID

executableDir = (
    Path(sys.executable).resolve().parent
    if "__compiled__" in globals()
    else Path(".")
)

APP_DATA_DIR: str = (
    f"{QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)}/GhostDownloader"
    if IS_ANDROID
    else str(executableDir / "GhostDownloader")
    if (executableDir / "GhostDownloader").is_dir()
    else f"{QStandardPaths.writableLocation(QStandardPaths.StandardLocation.GenericDataLocation)}/GhostDownloader"
)

PORTABLE_PATH = executableDir / "GhostDownloader"
USER_PATH = Path(QStandardPaths.writableLocation(
    QStandardPaths.StandardLocation.GenericDataLocation
)) / "GhostDownloader"

def isPortable() -> bool:
    return APP_DATA_DIR == str(PORTABLE_PATH)


def migrate(target: Path) -> None:
    from loguru import logger
    logger.remove()
    source = Path(APP_DATA_DIR)
    target.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target, dirs_exist_ok=True)
    if isPortable():
        source.rename(source.with_suffix(".bak"))
