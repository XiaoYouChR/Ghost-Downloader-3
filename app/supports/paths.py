import sys
from pathlib import Path

from PySide6.QtCore import QStandardPaths

from app.supports.android import IS_ANDROID

executableDir = (
    Path(sys.executable).resolve().parent
    if "__compiled__" in globals()
    else Path(".")
)
# Android 应用数据落 AppDataLocation 作用域目录(便携目录在 Android 是只读释放区写不进); 下载产物另走公共 Downloads
APP_DATA_DIR: str = (
    f"{QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)}/GhostDownloader"
    if IS_ANDROID
    else str(executableDir / "GhostDownloader")
    if (executableDir / "GhostDownloader").is_dir()
    else f"{QStandardPaths.writableLocation(QStandardPaths.StandardLocation.GenericDataLocation)}/GhostDownloader"
)
