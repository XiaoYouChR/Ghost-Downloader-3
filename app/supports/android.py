"""Android 平台辅助 —— 平台检测 + 经 pyjnius 取 native 库目录。

预编 ffmpeg/ffprobe 改名 lib*.so 打进 jniLibs, 释放到只读可执行的 nativeLibraryDir 后从那 exec
(Android 10+ W^X 下唯一合法路径)。桌面端 IS_ANDROID 为 False, 相关函数返回 None, jnius 永不 import。
"""

import sys
from functools import lru_cache

IS_ANDROID = hasattr(sys, "getandroidapilevel")


@lru_cache(maxsize=1)
def nativeLibraryDir() -> str | None:
    """app 的 nativeLibraryDir(native .so 释放处, 只读可执行); 非 Android 返回 None。"""
    if not IS_ANDROID:
        return None
    from jnius import autoclass

    activity = autoclass("org.kivy.android.PythonActivity").mActivity
    return activity.getApplicationInfo().nativeLibraryDir


def isSystemDark() -> bool | None:
    """系统当前是否深色(读 Configuration.uiMode 的 night 位); 非 Android 返回 None。

    桥接 darkdetect: 其在 Android 无后端恒返回 None, 不接管则 Theme.AUTO 永远落浅色。
    须在主线程调(pyjnius autoclass 在后台线程取不到 classloader)。
    """
    if not IS_ANDROID:
        return None
    from jnius import autoclass

    Configuration = autoclass("android.content.res.Configuration")
    activity = autoclass("org.kivy.android.PythonActivity").mActivity
    uiMode = activity.getResources().getConfiguration().uiMode
    return (uiMode & Configuration.UI_MODE_NIGHT_MASK) == Configuration.UI_MODE_NIGHT_YES


def isStorageGranted() -> bool:
    """是否已拿到「所有文件访问」(MANAGE_EXTERNAL_STORAGE); 非 Android 恒 True(桌面无此门)。"""
    if not IS_ANDROID:
        return True
    from jnius import autoclass

    return autoclass("android.os.Environment").isExternalStorageManager()


_fileUriPolicyRelaxed = False


def _relaxFileUriPolicy() -> None:
    """放宽本进程 StrictMode 的 file:// 暴露检查, 否则 startActivity(file://) 抛 FileUriExposedException。

    Android 7+ 强制 Intent 用 content://; 本 app 持 MANAGE_EXTERNAL_STORAGE、文件都在公共存储,
    放宽 VmPolicy 让 file:// 直接可用, 省去自建 FileProvider。
    """
    global _fileUriPolicyRelaxed
    if _fileUriPolicyRelaxed:
        return
    from jnius import autoclass

    StrictMode = autoclass("android.os.StrictMode")
    VmPolicyBuilder = autoclass("android.os.StrictMode$VmPolicy$Builder")
    StrictMode.setVmPolicy(VmPolicyBuilder().build())
    _fileUriPolicyRelaxed = True


def _launchView(path: str, mimeType: str) -> bool:
    """以 ACTION_VIEW + file:// 把路径交给系统应用打开; 无可处理应用则吞异常返回 False。"""
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
    """用系统应用打开下载好的文件(ACTION_VIEW + file:// + 按扩展名定 MIME); 非 Android 空操作。"""
    if not IS_ANDROID:
        return
    from jnius import autoclass

    MimeTypeMap = autoclass("android.webkit.MimeTypeMap")
    text = str(path)
    extension = text.rsplit(".", 1)[-1].lower() if "." in text else ""
    mimeType = MimeTypeMap.getSingleton().getMimeTypeFromExtension(extension) or "*/*"
    _launchView(text, mimeType)


def openFolder(path) -> None:
    """在系统文件管理器中打开 path 所在目录; 非 Android 空操作。各 OEM 支持参差, 打不开静默放弃。"""
    if not IS_ANDROID:
        return
    from pathlib import Path

    target = Path(str(path))
    directory = target if target.is_dir() else target.parent
    _launchView(str(directory), "vnd.android.document/directory")


def requestStoragePermission() -> None:
    """拉系统「所有文件访问」设置页授权(非阻塞); 非 Android 空操作。须在主线程调。

    MANAGE_EXTERNAL_STORAGE 无运行时弹窗, 只能 Intent 跳系统设置页。
    """
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
