from __future__ import annotations

import sys
from functools import lru_cache

IS_ANDROID = hasattr(sys, "getandroidapilevel")


@lru_cache(maxsize=1)
def nativeLibraryDir() -> str:
    from java import jclass
    activity = jclass("com.chaquo.python.Python").getPlatform().getApplication()
    return activity.getApplicationInfo().nativeLibraryDir
