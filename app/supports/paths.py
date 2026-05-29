import sys
from pathlib import Path

from PySide6.QtCore import QStandardPaths

executableDir = (
    Path(sys.executable).resolve().parent
    if "__compiled__" in globals()
    else Path(".")
)
APP_DATA_DIR: str = (
    str(executableDir / "GhostDownloader")
    if (executableDir / "GhostDownloader").is_dir()
    else f"{QStandardPaths.writableLocation(QStandardPaths.StandardLocation.GenericDataLocation)}/GhostDownloader"
)
