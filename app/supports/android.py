"""Android 平台辅助 —— 平台检测 + pyjnius 调系统 API。须主线程调(后台线程 autoclass 取不到 classloader)。

ffmpeg/ffprobe/N_m3u8DL-RE 改名 lib*.so 打进 jniLibs, 释放到只读可执行的 nativeLibraryDir 后从那 exec(W^X 下唯一合法路径)。
"""

import sys
from functools import lru_cache

IS_ANDROID = hasattr(sys, "getandroidapilevel")


@lru_cache(maxsize=1)
def nativeLibraryDir() -> str | None:
    if not IS_ANDROID:
        return None
    from jnius import autoclass

    activity = autoclass("org.kivy.android.PythonActivity").mActivity
    return activity.getApplicationInfo().nativeLibraryDir


def isSystemDark() -> bool | None:
    # darkdetect 在 Android 无后端恒 None, 不接管则 Theme.AUTO 永远浅色
    if not IS_ANDROID:
        return None
    from jnius import autoclass

    Configuration = autoclass("android.content.res.Configuration")
    activity = autoclass("org.kivy.android.PythonActivity").mActivity
    uiMode = activity.getResources().getConfiguration().uiMode
    return (uiMode & Configuration.UI_MODE_NIGHT_MASK) == Configuration.UI_MODE_NIGHT_YES


def isStorageGranted() -> bool:
    if not IS_ANDROID:
        return True
    from jnius import autoclass

    return autoclass("android.os.Environment").isExternalStorageManager()


_fileUriPolicyRelaxed = False


def _relaxFileUriPolicy() -> None:
    # 放宽 VmPolicy, 否则 startActivity(file://) 抛 FileUriExposedException(持 MANAGE_EXTERNAL_STORAGE, 省 FileProvider)
    global _fileUriPolicyRelaxed
    if _fileUriPolicyRelaxed:
        return
    from jnius import autoclass

    StrictMode = autoclass("android.os.StrictMode")
    VmPolicyBuilder = autoclass("android.os.StrictMode$VmPolicy$Builder")
    StrictMode.setVmPolicy(VmPolicyBuilder().build())
    _fileUriPolicyRelaxed = True


def _launchView(path: str, mimeType: str) -> bool:
    from jnius import autoclass

    _relaxFileUriPolicy()
    Uri = autoclass("android.net.Uri")
    File = autoclass("java.io.File")
    Intent = autoclass("android.content.Intent")
    activity = autoclass("org.kivy.android.PythonActivity").mActivity

    intent = Intent(Intent.ACTION_VIEW)
    intent.setDataAndType(Uri.fromFile(File(path)), mimeType)
    intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
    try:
        activity.startActivity(intent)
        return True
    except Exception as error:
        from loguru import logger

        logger.opt(exception=error).info("打开失败, 放弃: {} ({})", path, mimeType)
        return False


def openFile(path) -> None:
    if not IS_ANDROID:
        return
    from jnius import autoclass

    MimeTypeMap = autoclass("android.webkit.MimeTypeMap")
    text = str(path)
    extension = text.rsplit(".", 1)[-1].lower() if "." in text else ""
    mimeType = MimeTypeMap.getSingleton().getMimeTypeFromExtension(extension) or "*/*"
    _launchView(text, mimeType)


def openFolder(path) -> None:
    if not IS_ANDROID:
        return
    from pathlib import Path

    target = Path(str(path))
    directory = target if target.is_dir() else target.parent
    _launchView(str(directory), "vnd.android.document/directory")


def requestStoragePermission() -> None:
    # MANAGE_EXTERNAL_STORAGE 无运行时弹窗, 只能 Intent 跳系统设置页
    if not IS_ANDROID:
        return
    from jnius import autoclass

    Settings = autoclass("android.provider.Settings")
    Uri = autoclass("android.net.Uri")
    Intent = autoclass("android.content.Intent")
    activity = autoclass("org.kivy.android.PythonActivity").mActivity

    intent = Intent(Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION)
    intent.setData(Uri.parse("package:" + activity.getPackageName()))
    activity.startActivity(intent)
