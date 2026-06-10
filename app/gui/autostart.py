import sys
from pathlib import Path

from PySide6.QtCore import QCoreApplication

from app.supports.config import DESKTOP_ID, VERSION

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_RUN_NAME = "GhostDownloader"
_MAC_AGENT = "Library/LaunchAgents/com.xiaoyouchr.ghostdownloader.plist"


def applyAutoRun(enabled: bool) -> None:
    """把 GD 注册 / 移除到操作系统的开机启动项。纯桌面 OS 动作，只在 gui 端调
    （headless daemon / Android 不涉及开机自启，故不放共享层）。"""
    exe = QCoreApplication.applicationFilePath()

    if sys.platform == "win32":
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_WRITE) as key:
            if enabled:
                winreg.SetValueEx(key, _RUN_NAME, 0, winreg.REG_SZ, f'"{exe.replace("/", chr(92))}" --silence')
            else:
                try:
                    winreg.DeleteValue(key, _RUN_NAME)
                except FileNotFoundError:
                    pass  # 本就没注册，移除即满足

    elif sys.platform == "darwin":
        agent = Path.home() / _MAC_AGENT
        if enabled:
            agent.write_text(
                '<?xml version="1.0" encoding="UTF-8"?>\n'
                '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
                '<plist version="1.0"><dict>'
                "<key>Label</key><string>com.xiaoyouchr.ghostdownloader</string>"
                "<key>ProgramArguments</key>"
                f"<array><string>{exe}</string><string>--silence</string></array>"
                "<key>RunAtLoad</key><true/>"
                "</dict></plist>\n",
                encoding="utf-8",
            )
        else:
            agent.unlink(missing_ok=True)

    elif sys.platform == "linux":
        autoStartDir = Path.home() / ".config/autostart"
        desktopFile = autoStartDir / f"{DESKTOP_ID}.desktop"
        (autoStartDir / "gd3.desktop").unlink(missing_ok=True)  # 旧版固定名，无论开关都清掉
        if enabled:
            autoStartDir.mkdir(parents=True, exist_ok=True)
            desktopFile.write_text(
                "[Desktop Entry]\n"
                "Type=Application\n"
                f"Version={VERSION}\n"
                "Name=Ghost Downloader 3\n"
                "Comment=A multi-threading downloader with QThread based on PySide6\n"
                f'Exec="{exe}" --silence\n'
                "StartupNotify=false\n"
                "Terminal=false\n",
                encoding="utf-8",
            )
        else:
            desktopFile.unlink(missing_ok=True)
