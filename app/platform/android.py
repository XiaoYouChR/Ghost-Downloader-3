from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

from loguru import logger

IS_ANDROID = hasattr(sys, "getandroidapilevel")


@lru_cache(maxsize=1)
def application():
    from java import jclass
    return jclass("com.chaquo.python.Python").getPlatform().getApplication()


@lru_cache(maxsize=1)
def nativeLibraryDir() -> str:
    return application().getApplicationInfo().nativeLibraryDir


def isUnmeteredNetwork() -> bool:
    try:
        from java import jclass
        cm = application().getSystemService(jclass("android.content.Context").CONNECTIVITY_SERVICE)
        return cm is not None and cm.getActiveNetwork() is not None and not cm.isActiveNetworkMetered()
    except Exception as e:
        logger.debug("检查网络计费状态失败: {}", repr(e))
        return False


def patchApk(patchPath: Path, outputPath: Path) -> None:
    from java import jclass
    oldApk = application().getApplicationInfo().sourceDir
    code = jclass("com.github.sisong.HPatch").patch(oldApk, str(patchPath), str(outputPath))
    if code != 0:
        raise RuntimeError(f"HPatch.patch failed ({code})")


def installApk(apkPath: Path) -> bool:
    try:
        from java import jclass
        app = application()
        uri = jclass("androidx.core.content.FileProvider").getUriForFile(
            app, f"{app.getPackageName()}.fileprovider", jclass("java.io.File")(str(apkPath)),
        )
        Intent = jclass("android.content.Intent")
        intent = Intent(Intent.ACTION_VIEW)
        intent.setDataAndType(uri, "application/vnd.android.package-archive")
        intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_ACTIVITY_NEW_TASK)
        app.startActivity(intent)
        return True
    except Exception as e:
        logger.warning("启动 APK 安装失败: {}", repr(e))
        return False
