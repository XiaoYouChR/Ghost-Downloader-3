"""Windows 10/11 Toast 通知，支持进度条实时更新。"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QStandardPaths
from loguru import logger

if TYPE_CHECKING:
    from collections.abc import Callable

_APP_ID = "Ghost Downloader"
_GROUP = "GhostDownloader"


def _ensure_aumid_registered() -> None:
    import winreg
    key_path = f"SOFTWARE\\Classes\\AppUserModelId\\{_APP_ID}"
    try:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key_path) as key:
            winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, _APP_ID)
            icon = _get_logo_path()
            if icon.exists():
                winreg.SetValueEx(key, "IconUri", 0, winreg.REG_SZ, icon.as_uri())
    except OSError:
        pass


def _get_logo_path() -> Path:
    p = Path(QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.TempLocation)) / "gd3_logo.png"
    if not p.exists():
        try:
            from PySide6.QtCore import QResource
            with open(p, "wb") as f:
                f.write(QResource(":/image/logo.png").data())
        except Exception:
            pass
    return p


class WindowsToastManager:

    def __init__(self) -> None:
        self._notifier = None
        self._initialized = False
        self._seq: dict[str, int] = {}

    def _init(self) -> None:
        if self._initialized:
            return
        _ensure_aumid_registered()
        try:
            from winrt.windows.ui.notifications import ToastNotificationManager
            self._notifier = ToastNotificationManager.get_default().create_toast_notifier_with_id(_APP_ID)
            self._initialized = True
        except Exception as e:
            logger.opt(exception=e).error("初始化 Windows Toast 通知失败")

    # ── XML 构建 ──────────────────────────────────────────────

    def _progress_xml(self, task_name: str, icon_path: str) -> str:
        from xml.sax.saxutils import escape
        icon_src = Path(icon_path).as_uri() if icon_path else _get_logo_path().as_uri()
        return "\n".join([
            '<?xml version="1.0" encoding="utf-8"?>',
            '<toast duration="long">',
            "  <visual>",
            '    <binding template="ToastGeneric">',
            f'      <image src="{icon_src}" placement="appLogoOverride"/>',
            f"      <text>{escape(task_name)}</text>",
            '      <text>{progressSize}</text>',
            '      <progress title="下载中" value="{progressValue}"'
            ' valueStringOverride="{progressValueString}" status="{progressStatus}"/>',
            "    </binding>",
            "  </visual>",
            "</toast>",
        ])

    def _completed_xml(self, task_name: str, output_path: str, icon_path: str) -> str:
        from xml.sax.saxutils import escape
        icon_src = Path(icon_path).as_uri() if icon_path else _get_logo_path().as_uri()
        safe_path = escape(output_path)
        return "\n".join([
            '<?xml version="1.0" encoding="utf-8"?>',
            '<toast activationType="foreground" launch="action=openFile">',
            "  <visual>",
            '    <binding template="ToastGeneric">',
            f'      <image src="{icon_src}" placement="appLogoOverride"/>',
            "      <text>下载完成</text>",
            f"      <text>{escape(task_name)}</text>",
            "    </binding>",
            "  </visual>",
            "  <actions>",
            f'    <action content="打开文件" activationType="foreground"'
            f' arguments="action=openFile&amp;path={safe_path}"/>',
            f'    <action content="打开目录" activationType="foreground"'
            f' arguments="action=openFolder&amp;path={safe_path}"/>',
            "  </actions>",
            '  <audio src="ms-winsoundevent:Notification.Default"/>',
            "</toast>",
        ])

    def _failed_xml(self, task_name: str, icon_path: str) -> str:
        from xml.sax.saxutils import escape
        icon_src = Path(icon_path).as_uri() if icon_path else _get_logo_path().as_uri()
        return "\n".join([
            '<?xml version="1.0" encoding="utf-8"?>',
            "<toast>",
            "  <visual>",
            '    <binding template="ToastGeneric">',
            f'      <image src="{icon_src}" placement="appLogoOverride"/>',
            "      <text>Ghost Downloader</text>",
            f"      <text>下载失败：{escape(task_name)}</text>",
            "    </binding>",
            "  </visual>",
            '  <audio src="ms-winsoundevent:Notification.Default"/>',
            "</toast>",
        ])

    # ── 公开 API ──────────────────────────────────────────────

    def show_progress(self, tag: str, task_name: str, progress: float,
                      speed: int, received_bytes: int, total_bytes: int,
                      icon_path: str = "") -> None:
        """显示/更新下载进度。首次调用创建 Toast，后续通过数据绑定增量更新。"""
        self._init()
        if self._notifier is None:
            return
        try:
            from winrt.windows.ui.notifications import ToastNotification, NotificationData
            from winrt.windows.data.xml.dom import XmlDocument
            from app.format import toReadableSize, toReadableTime

            progress_pct = f"{progress:.1f}%"
            speed_str = f"{toReadableSize(speed)}/s"
            size_info = (f"{toReadableSize(received_bytes)}/{toReadableSize(total_bytes)}"
                         if total_bytes > 0 else toReadableSize(received_bytes))
            eta = (toReadableTime(int((total_bytes - received_bytes) / speed))
                   if total_bytes > 0 and speed > 0 else "--")

            seq = self._seq.get(tag, -1) + 1
            data = NotificationData()
            data.sequence_number = seq
            data.values["progressValue"] = f"{progress / 100.0:.4f}"
            data.values["progressValueString"] = progress_pct
            data.values["progressStatus"] = f"{speed_str}  |  剩余 {eta}"
            data.values["progressSize"] = size_info

            if seq == 0:
                xml = XmlDocument()
                xml.load_xml(self._progress_xml(task_name, icon_path))
                toast = ToastNotification(xml)
                toast.tag = tag
                toast.group = _GROUP
                toast.data = data
                self._notifier.show(toast)
            else:
                self._notifier.update_with_tag_and_group(data, tag, _GROUP)

            self._seq[tag] = seq
        except Exception:
            pass  # 静默失败，不影响下载功能

    def show_completed(self, tag: str, task_name: str, output_path: str,
                       icon_path: str = "") -> None:
        self._init()
        if self._notifier is None:
            return
        try:
            from winrt.windows.ui.notifications import ToastNotification
            from winrt.windows.data.xml.dom import XmlDocument

            xml = XmlDocument()
            xml.load_xml(self._completed_xml(task_name, output_path, icon_path))
            toast = ToastNotification(xml)
            toast.tag = tag
            toast.group = _GROUP
            toast.add_activated(self._on_activated)
            self._notifier.show(toast)
            self._seq.pop(tag, None)
        except Exception:
            pass

    def show_failed(self, tag: str, task_name: str, icon_path: str = "") -> None:
        self._init()
        if self._notifier is None:
            return
        try:
            from winrt.windows.ui.notifications import ToastNotification
            from winrt.windows.data.xml.dom import XmlDocument

            xml = XmlDocument()
            xml.load_xml(self._failed_xml(task_name, icon_path))
            toast = ToastNotification(xml)
            toast.tag = tag
            toast.group = _GROUP
            self._notifier.show(toast)
            self._seq.pop(tag, None)
        except Exception:
            pass

    def show_text(self, tag: str, task_name: str, subtitle: str = "") -> None:
        self._init()
        if self._notifier is None:
            return
        try:
            from winrt.windows.ui.notifications import ToastNotification
            from winrt.windows.data.xml.dom import XmlDocument
            from xml.sax.saxutils import escape

            icon_src = _get_logo_path().as_uri()
            texts = (f"      <text>{escape(subtitle)}</text>\n"
                     f"      <text>{escape(task_name)}</text>" if subtitle else
                     f"      <text>Ghost Downloader</text>\n"
                     f"      <text>{escape(task_name)}</text>")

            xml = XmlDocument()
            xml.load_xml("\n".join([
                '<?xml version="1.0" encoding="utf-8"?>', "<toast>", "  <visual>",
                '    <binding template="ToastGeneric">',
                f'      <image src="{icon_src}" placement="appLogoOverride"/>',
                texts, "    </binding>", "  </visual>", "</toast>",
            ]))
            toast = ToastNotification(xml)
            toast.tag = tag
            toast.group = _GROUP
            self._notifier.show(toast)
        except Exception:
            pass

    def hide(self, tag: str) -> None:
        self._init()
        if self._notifier is None:
            return
        try:
            self._notifier.hide(tag)
            self._seq.pop(tag, None)
        except Exception:
            pass

    # ── 激活处理 ──────────────────────────────────────────────

    def _on_activated(self, sender, boxed_args) -> None:
        if boxed_args is None:
            return
        try:
            from winrt.windows.ui.notifications import ToastActivatedEventArgs
            args = boxed_args.as_(ToastActivatedEventArgs)
            self._handle_activation(args.arguments if args else "")
        except Exception:
            pass

    def _handle_activation(self, arguments: str) -> None:
        if not arguments:
            return
        from urllib.parse import parse_qs
        from app.platform.desktop import openFile, revealInFolder
        try:
            params = parse_qs(arguments)
            action = params.get("action", [""])[0]
            path = params.get("path", [""])[0]
            if action == "openFile" and path:
                openFile(path)
            elif action == "openFolder" and path:
                revealInFolder(path)
        except Exception:
            pass


windowsToastManager = WindowsToastManager()
