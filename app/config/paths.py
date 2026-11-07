from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from PySide6.QtCore import QStandardPaths

IS_COMPILED = "__compiled__" in globals()

EXECUTABLE_PATH = (
    Path(os.environ["APPIMAGE"]) if "APPIMAGE" in os.environ
    else Path(sys.argv[0]).resolve() if IS_COMPILED
    else Path(sys.executable).resolve()
)

EXECUTABLE_DIR = (
    Path(sys.executable).resolve().parent
    if IS_COMPILED
    else Path(".")
)

APP_DATA_DIR = (
    EXECUTABLE_DIR / "GhostDownloader"
    if (EXECUTABLE_DIR / "GhostDownloader").is_dir()
    else Path(QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.GenericDataLocation
    )) / "GhostDownloader"
)

PORTABLE_DIR = EXECUTABLE_DIR / "GhostDownloader"

SEED_FEATURES_DIR = EXECUTABLE_DIR / "features"
FEATURES_DIR = (
    SEED_FEATURES_DIR
    if not IS_COMPILED
    else APP_DATA_DIR / "features"
)
USER_DATA_DIR = Path(QStandardPaths.writableLocation(
    QStandardPaths.StandardLocation.GenericDataLocation
)) / "GhostDownloader"

DOWNLOAD_DIR = Path(QStandardPaths.writableLocation(
    QStandardPaths.StandardLocation.DownloadLocation
))


def hasNoAutoUpdateMarker() -> bool:
    return (EXECUTABLE_DIR / "gd_no_auto_update").is_file()


def isPortable() -> bool:
    return APP_DATA_DIR == PORTABLE_DIR


def migrate(target: Path) -> None:
    from loguru import logger
    logger.remove()
    source = APP_DATA_DIR
    target.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target, dirs_exist_ok=True)
    if isPortable():
        source.rename(source.with_suffix(".bak"))
