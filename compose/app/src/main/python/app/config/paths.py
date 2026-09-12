from __future__ import annotations

from pathlib import Path

from java import jclass, cast

_AndroidPlatform = jclass("com.chaquo.python.android.AndroidPlatform")
_context = cast(_AndroidPlatform,
    jclass("com.chaquo.python.Python").getInstance().getPlatform()
).getApplication()
_Environment = jclass("android.os.Environment")

APP_DATA_DIR = Path(str(_context.getFilesDir()))
USER_DATA_DIR = APP_DATA_DIR
DOWNLOAD_DIR = Path(str(_Environment.getExternalStoragePublicDirectory(
    _Environment.DIRECTORY_DOWNLOADS)))

import features
FEATURES_DIR = Path(features.__path__[0])
SEED_FEATURES_DIR = FEATURES_DIR

EXECUTABLE_DIR = Path(".")


def isPortable() -> bool:
    return False
