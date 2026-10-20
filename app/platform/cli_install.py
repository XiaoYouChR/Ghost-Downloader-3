from __future__ import annotations

import asyncio
import shlex
import sys
from pathlib import Path

from app.config.paths import EXECUTABLE_DIR, EXECUTABLE_PATH
from app.models.task import TaskError

LINK_PATH = Path("/usr/local/bin/ghd") if sys.platform == "darwin" else Path.home() / ".local/bin/ghd"
BIN_FOLDER = str(EXECUTABLE_DIR / "bin")


def isInstalled() -> bool:
    if sys.platform == "win32":
        return BIN_FOLDER.lower() in (entry.lower() for entry in loadUserPath()[0].split(";"))
    return LINK_PATH.is_symlink() and LINK_PATH.resolve() == EXECUTABLE_PATH.resolve()


async def install() -> None:
    if sys.platform == "win32":
        path, kind = loadUserPath()
        if not isInstalled():
            await asyncio.to_thread(saveUserPath, ";".join(entry for entry in (path, BIN_FOLDER) if entry), kind)
        return
    if LINK_PATH.exists() and not LINK_PATH.is_symlink():
        raise TaskError("{path} 已被其他文件占用", path=LINK_PATH)
    try:
        LINK_PATH.parent.mkdir(parents=True, exist_ok=True)
        LINK_PATH.unlink(missing_ok=True)
        LINK_PATH.symlink_to(EXECUTABLE_PATH)
    except PermissionError:
        if sys.platform != "darwin":
            raise
        await runAsAdministrator(f"mkdir -p {shlex.quote(str(LINK_PATH.parent))} && "
                                 f"ln -sfn {shlex.quote(str(EXECUTABLE_PATH))} {shlex.quote(str(LINK_PATH))}")


async def delete() -> None:
    if sys.platform == "win32":
        path, kind = loadUserPath()
        entries = [entry for entry in path.split(";") if entry.lower() != BIN_FOLDER.lower()]
        await asyncio.to_thread(saveUserPath, ";".join(entries), kind)
        return
    if not LINK_PATH.is_symlink():
        return
    try:
        LINK_PATH.unlink()
    except PermissionError:
        if sys.platform != "darwin":
            raise
        await runAsAdministrator(f"rm -f {shlex.quote(str(LINK_PATH))}")


async def runAsAdministrator(command: str) -> None:
    script = command.replace("\\", "\\\\").replace('"', '\\"')
    process = await asyncio.create_subprocess_exec(
        "osascript", "-e", f'do shell script "{script}" with administrator privileges',
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
    )
    if await process.wait() != 0:
        raise TaskError("未获得管理员授权")


def loadUserPath() -> tuple[str, int]:
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
        try:
            return winreg.QueryValueEx(key, "Path")
        except FileNotFoundError:
            return "", winreg.REG_EXPAND_SZ


def saveUserPath(path: str, kind: int) -> None:
    import winreg
    import win32con
    import win32gui
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, "Path", 0, kind, path)
    win32gui.SendMessageTimeout(win32con.HWND_BROADCAST, win32con.WM_SETTINGCHANGE, 0, "Environment",
                                win32con.SMTO_ABORTIFHUNG, 5000)
