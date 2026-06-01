import subprocess
import sys
from pathlib import Path

from loguru import logger
from PySide6.QtCore import QCoreApplication

from app.bases.interfaces import FileType
from app.supports.config import DESKTOP_ID
from app.supports.paths import executableDir

if sys.platform == "win32":
    import winreg

DESKTOP_DIR = Path.home() / ".local/share/applications"
DBUS_SERVICE_DIR = Path.home() / ".local/share/dbus-1/services"


def register(fileTypes: list[FileType]) -> None:
    if not fileTypes:
        return
    try:
        if sys.platform == "win32":
            _registerWindows(fileTypes)
        elif sys.platform == "linux":
            _applyLinuxAssociation(_linuxMimes() | {ft.mimeType for ft in fileTypes})
    except Exception as e:
        logger.opt(exception=e).error("注册文件关联失败")


def unregister(fileTypes: list[FileType]) -> None:
    if not fileTypes:
        return
    try:
        if sys.platform == "win32":
            _unregisterWindows(fileTypes)
        elif sys.platform == "linux":
            _applyLinuxAssociation(_linuxMimes() - {ft.mimeType for ft in fileTypes})
    except Exception as e:
        logger.opt(exception=e).error("取消文件关联失败")


def iconFile(name: str, extension: str) -> Path:
    return executableDir / "app" / "assets" / "file_icons" / f"{name}.{extension}"


# Windows 文件关联写在 per-user 的 HKCU\Software\Classes, 免管理员权限

def _progId(extension: str) -> str:
    return f"GhostDownloader{extension}"


def _registerWindows(fileTypes: list[FileType]) -> None:
    command = f'"{QCoreApplication.applicationFilePath().replace("/", chr(92))}" "%1"'
    for fileType in fileTypes:
        icon = str(iconFile(fileType.icon, "ico")).replace("/", "\\")
        for extension in fileType.extensions:
            progId = _progId(extension)
            _writeKey(rf"Software\Classes\{progId}", fileType.displayName)
            _writeKey(rf"Software\Classes\{progId}\DefaultIcon", icon)
            _writeKey(rf"Software\Classes\{progId}\shell\open\command", command)
            _writeKey(rf"Software\Classes\{extension}", progId)
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"Software\Classes\{extension}\OpenWithProgids") as key:
                winreg.SetValueEx(key, progId, 0, winreg.REG_NONE, b"")
    _announceAssociationChange()


def _unregisterWindows(fileTypes: list[FileType]) -> None:
    for fileType in fileTypes:
        for extension in fileType.extensions:
            progId = _progId(extension)
            _deleteTree(rf"Software\Classes\{progId}")
            _deleteValue(rf"Software\Classes\{extension}\OpenWithProgids", progId)
            # 默认值是别人时不要动, 只清掉确实是我们写的那个
            if _keyDefault(rf"Software\Classes\{extension}") == progId:
                _deleteValue(rf"Software\Classes\{extension}", "")
    _announceAssociationChange()


def _writeKey(path: str, value: str) -> None:
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, path) as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, value)


def _keyDefault(path: str) -> str | None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
            return winreg.QueryValueEx(key, "")[0]
    except FileNotFoundError:
        return None


def _deleteValue(path: str, name: str) -> None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, name)
    except FileNotFoundError:
        pass


def _deleteTree(path: str) -> None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_ALL_ACCESS) as key:
            while True:
                try:
                    child = winreg.EnumKey(key, 0)
                except OSError:
                    break
                _deleteTree(rf"{path}\{child}")
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
    except FileNotFoundError:
        pass


def _announceAssociationChange() -> None:
    import ctypes

    SHCNE_ASSOCCHANGED = 0x08000000
    ctypes.windll.shell32.SHChangeNotify(SHCNE_ASSOCCHANGED, 0, None, None)


# Linux 文件关联写在 ~/.local/share 下的 .desktop + xdg-mime, 免 root

def _desktopPath() -> Path:
    return DESKTOP_DIR / f"{DESKTOP_ID}.desktop"


def _linuxMimes() -> set[str]:
    path = _desktopPath()
    if not path.exists():
        return set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("MimeType="):
            return {mime for mime in line[len("MimeType="):].split(";") if mime}
    return set()


def _applyLinuxAssociation(mimes: set[str]) -> None:
    path = _desktopPath()
    if not mimes:
        path.unlink(missing_ok=True)
        (DBUS_SERVICE_DIR / f"{DESKTOP_ID}.service").unlink(missing_ok=True)
        _refreshLinuxDatabases()
        return

    DESKTOP_DIR.mkdir(parents=True, exist_ok=True)
    DBUS_SERVICE_DIR.mkdir(parents=True, exist_ok=True)
    mimeLine = ";".join(sorted(mimes)) + ";"
    path.write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Ghost Downloader\n"
        f"Exec={QCoreApplication.applicationFilePath()} %F\n"
        "Icon=ghost-downloader\n"
        "Terminal=false\n"
        "Categories=Network;Utility;\n"
        "DBusActivatable=true\n"
        f"MimeType={mimeLine}\n",
        encoding="utf-8",
    )
    (DBUS_SERVICE_DIR / f"{DESKTOP_ID}.service").write_text(
        "[D-BUS Service]\n"
        f"Name={DESKTOP_ID}\n"
        f"Exec={QCoreApplication.applicationFilePath()}\n",
        encoding="utf-8",
    )
    _refreshLinuxDatabases()
    for mime in mimes:
        _run(["xdg-mime", "default", f"{DESKTOP_ID}.desktop", mime])


def _refreshLinuxDatabases() -> None:
    _run(["update-desktop-database", str(DESKTOP_DIR)])


def _run(args: list[str]) -> None:
    try:
        subprocess.run(args, check=False, capture_output=True)
    except FileNotFoundError:
        logger.warning("缺少命令, 跳过: {}", args[0])
