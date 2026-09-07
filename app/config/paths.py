from __future__ import annotations

import shutil
import sys
from pathlib import Path

from platformdirs import user_data_path, user_downloads_path

EXECUTABLE_DIR = (
    Path(sys.executable).resolve().parent
    if "__compiled__" in globals()
    else Path(".")
)

APP_DATA_DIR = (
    EXECUTABLE_DIR / "GhostDownloader"
    if (EXECUTABLE_DIR / "GhostDownloader").is_dir()
    else user_data_path("GhostDownloader", appauthor=False)
)

PORTABLE_DIR = EXECUTABLE_DIR / "GhostDownloader"

SEED_FEATURES_DIR = EXECUTABLE_DIR / "features"
FEATURES_DIR = (
    SEED_FEATURES_DIR
    if "__compiled__" not in globals()
    else APP_DATA_DIR / "features"
)
USER_DATA_DIR = user_data_path("GhostDownloader", appauthor=False)

DOWNLOAD_DIR = user_downloads_path()


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
