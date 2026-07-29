from __future__ import annotations

import re
import sys
from functools import lru_cache

IS_ANDROID = hasattr(sys, "getandroidapilevel")


@lru_cache(maxsize=1)
def nativeLibraryDir() -> str:
    from jnius import autoclass
    activity = autoclass("org.kivy.android.PythonActivity").mActivity
    return activity.getApplicationInfo().nativeLibraryDir


def isSystemDark() -> bool:
    from jnius import autoclass
    Configuration = autoclass("android.content.res.Configuration")
    activity = autoclass("org.kivy.android.PythonActivity").mActivity
    uiMode = activity.getResources().getConfiguration().uiMode
    return (uiMode & Configuration.UI_MODE_NIGHT_MASK) == Configuration.UI_MODE_NIGHT_YES


WRITE_EXTERNAL_STORAGE = "android.permission.WRITE_EXTERNAL_STORAGE"


def isStorageGranted() -> bool:
    from jnius import autoclass
    # API30+ scoped storage 下下载到任意公共目录需 All Files Access; API<30(Android 9/10)回退运行时 WRITE 权限
    # (Android 10 靠 manifest 的 requestLegacyExternalStorage 让 WRITE 仍能自由写外置存储)。
    if autoclass("android.os.Build$VERSION").SDK_INT >= 30:
        return autoclass("android.os.Environment").isExternalStorageManager()
    PackageManager = autoclass("android.content.pm.PackageManager")
    activity = autoclass("org.kivy.android.PythonActivity").mActivity
    return activity.checkSelfPermission(WRITE_EXTERNAL_STORAGE) == PackageManager.PERMISSION_GRANTED


def requestStoragePermission() -> None:
    from jnius import autoclass
    activity = autoclass("org.kivy.android.PythonActivity").mActivity
    if autoclass("android.os.Build$VERSION").SDK_INT >= 30:
        Settings = autoclass("android.provider.Settings")
        Uri = autoclass("android.net.Uri")
        Intent = autoclass("android.content.Intent")
        intent = Intent(Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION)
        intent.setData(Uri.parse("package:" + activity.getPackageName()))
        activity.startActivity(intent)
        return
    # <30 弹运行时权限对话框; 结果由 MainWindow 的 applicationStateChanged 重查 banner, 无需回调。
    activity.requestPermissions([WRITE_EXTERNAL_STORAGE], 0)


_fileUriPolicyRelaxed = False


def _relaxFileUriPolicy() -> None:
    # Android 24+ 用 Uri.fromFile 调起外部应用会抛 FileUriExposedException, 放宽 StrictMode
    global _fileUriPolicyRelaxed
    if _fileUriPolicyRelaxed:
        return
    from jnius import autoclass
    StrictMode = autoclass("android.os.StrictMode")
    VmPolicyBuilder = autoclass("android.os.StrictMode$VmPolicy$Builder")
    StrictMode.setVmPolicy(VmPolicyBuilder().build())
    _fileUriPolicyRelaxed = True


def _launchView(path: str, mimeType: str) -> None:
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
    except Exception as error:
        from loguru import logger
        logger.opt(exception=error).info("打开失败, 放弃: {} ({})", path, mimeType)


def openFile(filePath) -> None:
    from jnius import autoclass
    text = str(filePath)
    extension = text.rsplit(".", 1)[-1].lower() if "." in text else ""
    mimeType = autoclass("android.webkit.MimeTypeMap").getSingleton().getMimeTypeFromExtension(extension) or "*/*"
    _launchView(text, mimeType)


def openFolder(folder) -> None:
    _launchView(str(folder), "vnd.android.document/directory")


def toFileUri(activity: "JavaObject", contentUri: "JavaObject") -> str | None:
    from pathlib import Path
    from jnius import autoclass

    try:
        resolver = activity.getContentResolver()

        displayName = "shared"
        cursor = resolver.query(contentUri, None, None, None, None)
        if cursor is not None:
            try:
                if cursor.moveToFirst():
                    idx = cursor.getColumnIndex("_display_name")
                    if idx >= 0:
                        displayName = cursor.getString(idx) or displayName
            finally:
                cursor.close()

        cacheDir = Path(activity.getCacheDir().getAbsolutePath()) / "shared"
        cacheDir.mkdir(parents=True, exist_ok=True)
        dest = cacheDir / displayName

        inputStream = resolver.openInputStream(contentUri)
        if inputStream is None:
            return None
        try:
            Files = autoclass("java.nio.file.Files")
            Paths = autoclass("java.nio.file.Paths")
            if dest.exists():
                dest.unlink()
            Files.copy(inputStream, Paths.get(str(dest)))
        finally:
            inputStream.close()

        return dest.as_uri()

    except Exception as error:
        from loguru import logger
        logger.opt(exception=error).warning("content:// 拷贝失败")
        return None


def parseShare() -> list[str] | None:
    from jnius import autoclass, cast
    Intent = autoclass("android.content.Intent")
    activity = autoclass("org.kivy.android.PythonActivity").mActivity
    intent = activity.getIntent()
    if intent is None:
        return None

    action = intent.getAction()
    if action not in (Intent.ACTION_SEND, Intent.ACTION_SEND_MULTIPLE):
        return None

    if action == Intent.ACTION_SEND_MULTIPLE:
        streams = intent.getParcelableArrayListExtra(Intent.EXTRA_STREAM)
        if not streams:
            return []
        return [fileUri for i in range(streams.size())
                if (fileUri := toFileUri(activity, cast("android.net.Uri", streams.get(i))))]

    stream = intent.getParcelableExtra(Intent.EXTRA_STREAM)
    if stream is not None:
        uri = toFileUri(activity, cast("android.net.Uri", stream))
        return [uri] if uri else []

    # 文本分享（ACTION_SEND 且无 EXTRA_STREAM）
    text = intent.getCharSequenceExtra(Intent.EXTRA_TEXT)
    if text is None:
        return []
    text = text if isinstance(text, str) else text.toString()

    standard = re.findall(r'(?i)(?:https?|ftps?|ed2k)://[^\s"\'<>，。！？、；：）》】」]+', text)
    magnets = re.findall(r'(?i)magnet:\?[^\s"\'<>，。！？、；：）》】」]+', text)
    return [url.rstrip(".,!?;:)]}>") for url in standard + magnets]


def clearShare() -> None:
    from jnius import autoclass
    Intent = autoclass("android.content.Intent")
    activity = autoclass("org.kivy.android.PythonActivity").mActivity
    intent = activity.getIntent()
    if intent is not None:
        intent.setAction(Intent.ACTION_MAIN)  # 分享已取走, 防回前台重复添加同一分享
