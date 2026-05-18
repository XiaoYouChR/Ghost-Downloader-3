import sys
from pathlib import Path

from PySide6.QtCore import QStandardPaths

_executableDir = Path(sys.argv[0]).resolve().parent
APP_DATA_DIR: str = (
    str(_executableDir / "GhostDownloader")
    if (_executableDir / "GhostDownloader").is_dir()
    else f"{QStandardPaths.writableLocation(QStandardPaths.StandardLocation.GenericDataLocation)}/GhostDownloader"
)
