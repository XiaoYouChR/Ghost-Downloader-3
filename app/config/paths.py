from __future__ import annotations

import shutil
import sys
from pathlib import Path

from platformdirs import user_data_path, user_downloads_path

executableDir = (
    Path(sys.executable).resolve().parent
    if "__compiled__" in globals()
    else Path(".")
)

APP_DATA_DIR: str = (
    str(executableDir / "GhostDownloader")
    if (executableDir / "GhostDownloader").is_dir()
    else str(user_data_path("GhostDownloader", appauthor=False))
)

PORTABLE_PATH = executableDir / "GhostDownloader"

SEED_FEATURES_DIR = executableDir / "features"
FEATURES_DIR = (
    SEED_FEATURES_DIR
    if "__compiled__" not in globals()
    else Path(APP_DATA_DIR) / "features"
)
USER_PATH = user_data_path("GhostDownloader", appauthor=False)

DOWNLOAD_DIR: str = str(user_downloads_path())

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
