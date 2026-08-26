from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import QCoreApplication


def resolveExecPath() -> str:
    if sys.platform == "linux":
        appimage = os.environ.get("APPIMAGE")
        if appimage and Path(appimage).is_file():
            return appimage
    return QCoreApplication.applicationFilePath()
