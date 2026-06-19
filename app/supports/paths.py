import sys
from pathlib import Path

from PySide6.QtCore import QStandardPaths

from app.supports.android import IS_ANDROID

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
