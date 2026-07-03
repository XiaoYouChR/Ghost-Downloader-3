"""Windows Toast 通知（Win10+），含下载进度条。"""
from __future__ import annotations

from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, tostring
from typing import TYPE_CHECKING

from PySide6.QtCore import QFileInfo, QStandardPaths, Qt, QTimer
from PySide6.QtWidgets import QFileIconProvider

if TYPE_CHECKING:
    from app.models.task import Task

_APP_ID = "Ghost Downloader"
_GROUP = "GhostDownloader"

_notifier = None
_running: dict[str, str] = {}   # taskId → icon path
_timer: QTimer | None = None
_seq: dict[str, int] = {}


# ═══ 初始化 ═════════════════════════════════════════════════════════

def init() -> None:
    import winreg
    try:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER,
                                f"SOFTWARE\\Classes\\AppUserModelId\\{_APP_ID}") as k:
            winreg.SetValueEx(k, "DisplayName", 0, winreg.REG_SZ, _APP_ID)
            logo = _logo()
            if logo.exists():
                winreg.SetValueEx(k, "IconUri", 0, winreg.REG_SZ, logo.as_uri())
    except OSError:
        pass
    from winrt.windows.ui.notifications import ToastNotificationManager
    global _notifier
    _notifier = (ToastNotificationManager.get_default()
                 .create_toast_notifier_with_id(_APP_ID))


# ═══ 工具 ═══════════════════════════════════════════════════════════

def _logo() -> Path:
    p = Path(QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.TempLocation)) / "gd3_logo.png"
    if not p.exists():
        from PySide6.QtCore import QResource
        with open(p, "wb") as f:
            f.write(QResource(":/image/logo.png").data())
    return p


def _file_icon(path: str) -> str:
    p = Path(QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.TempLocation)) / "gd_finished_icon.png"
    try:
        QFileIconProvider().icon(QFileInfo(path)).pixmap(48, 48).scaled(
            128, 128, aspectMode=Qt.AspectRatioMode.KeepAspectRatio,
            mode=Qt.TransformationMode.SmoothTransformation,
        ).save(str(p), "PNG")
        return str(p) if p.exists() else ""
    except Exception:
        return ""


def _icon_uri(icon: str) -> str:
    return Path(icon).as_uri() if icon else _logo().as_uri()


# ═══ Toast 发送 ═════════════════════════════════════════════════════

def _show(tag: str, xml: str, on_activated: bool = False) -> None:
    from winrt.windows.ui.notifications import ToastNotification
    from winrt.windows.data.xml.dom import XmlDocument
    doc = XmlDocument()
    doc.load_xml(xml)
    toast = ToastNotification(doc)
    toast.tag = tag
    toast.group = _GROUP
    if on_activated:
        toast.add_activated(_on_activated)
    _notifier.show(toast)


def _on_activated(_sender, boxed_args) -> None:
    if boxed_args is None:
        return
    from winrt.windows.ui.notifications import ToastActivatedEventArgs
    from urllib.parse import parse_qs
    from app.platform.desktop import openFile, revealInFolder
    args = boxed_args.as_(ToastActivatedEventArgs)
    if not (args and args.arguments):
        return
    p = parse_qs(args.arguments)
    a = p.get("action", [""])[0]
    x = p.get("path", [""])[0]
    if a == "openFile" and x:
        openFile(x)
    elif a == "openFolder" and x:
        revealInFolder(x)


# ═══ XML ════════════════════════════════════════════════════════════

def _decl(doc: Element) -> str:
    return '<?xml version="1.0" encoding="utf-8"?>\n' + tostring(doc, encoding="unicode")


def _progress_xml(name: str, icon: str) -> str:
    from xml.sax.saxutils import escape
    t = Element("toast", {"duration": "long"})
    b = SubElement(SubElement(t, "visual"), "binding", {"template": "ToastGeneric"})
    SubElement(b, "image", {"src": _icon_uri(icon), "placement": "appLogoOverride"})
    SubElement(b, "text").text = escape(name)
    SubElement(b, "text").text = "{progressSize}"
    SubElement(b, "progress", {
        "title": "下载中", "value": "{progressValue}",
        "valueStringOverride": "{progressValueString}",
        "status": "{progressStatus}",
    })
    return _decl(t)


def _completed_xml(name: str, path: str, icon: str) -> str:
    from xml.sax.saxutils import escape
    t = Element("toast", {"activationType": "foreground", "launch": "action=openFile"})
    b = SubElement(SubElement(t, "visual"), "binding", {"template": "ToastGeneric"})
    SubElement(b, "image", {"src": _icon_uri(icon), "placement": "appLogoOverride"})
    SubElement(b, "text").text = "下载完成"
    SubElement(b, "text").text = escape(name)
    a = SubElement(t, "actions")
    ep = escape(path)
    SubElement(a, "action", {"content": "打开文件", "activationType": "foreground",
                              "arguments": f"action=openFile&path={ep}"})
    SubElement(a, "action", {"content": "打开目录", "activationType": "foreground",
                              "arguments": f"action=openFolder&path={ep}"})
    SubElement(t, "audio", {"src": "ms-winsoundevent:Notification.Default"})
    return _decl(t)


def _failed_xml(name: str, icon: str) -> str:
    from xml.sax.saxutils import escape
    t = Element("toast")
    b = SubElement(SubElement(t, "visual"), "binding", {"template": "ToastGeneric"})
    SubElement(b, "image", {"src": _icon_uri(icon), "placement": "appLogoOverride"})
    SubElement(b, "text").text = "Ghost Downloader"
    SubElement(b, "text").text = f"下载失败：{escape(name)}"
    SubElement(t, "audio", {"src": "ms-winsoundevent:Notification.Default"})
    return _decl(t)


def _text_xml(title: str, body: str) -> str:
    from xml.sax.saxutils import escape
    t = Element("toast")
    b = SubElement(SubElement(t, "visual"), "binding", {"template": "ToastGeneric"})
    SubElement(b, "image", {"src": _logo().as_uri(), "placement": "appLogoOverride"})
    SubElement(b, "text").text = escape(title)
    SubElement(b, "text").text = escape(body)
    return _decl(t)


# ═══ 公开 API ══════════════════════════════════════════════════════

def show_text(tag: str, title: str, body: str) -> None:
    _show(tag, _text_xml(title, body))


def task_started(task: Task) -> None:
    icon = _file_icon(task.outputPath) if task.outputPath else ""
    _running[task.taskId] = icon
    _push(task)
    global _timer
    if _timer is None:
        _timer = QTimer()
        _timer.setInterval(1500)
        _timer.timeout.connect(_tick)
    if not _timer.isActive():
        _timer.start()


def task_completed(task: Task) -> None:
    icon = _running.pop(task.taskId, "") or _file_icon(task.outputPath)
    _show(task.taskId, _completed_xml(task.name, task.outputPath, icon), on_activated=True)
    _seq.pop(task.taskId, None)


def task_failed(task: Task) -> None:
    icon = _running.pop(task.taskId, "")
    if not icon and task.outputPath:
        icon = _file_icon(task.outputPath)
    _show(task.taskId, _failed_xml(task.name, icon))
    _seq.pop(task.taskId, None)


# ═══ 进度 ═══════════════════════════════════════════════════════════

def _tick() -> None:
    from app.services.task_service import taskService
    for tid in list(_running):
        t = taskService.taskById(tid)
        if t is None:
            _running.pop(tid, None)
        else:
            _push(t)
    if not _running and _timer is not None:
        _timer.stop()


def _push(task: Task) -> None:
    from winrt.windows.ui.notifications import NotificationData, ToastNotification
    from winrt.windows.data.xml.dom import XmlDocument
    from app.format import toReadableSize, toReadableTime

    p, s, r = task.currentSnapshot()
    T = task.fileSize

    seq = _seq.get(task.taskId, -1) + 1
    d = NotificationData()
    d.sequence_number = seq
    d.values["progressValue"] = f"{p / 100:.4f}"
    d.values["progressValueString"] = f"{p:.1f}%"
    d.values["progressStatus"] = (
        f"{toReadableSize(s)}/s  |  剩余 "
        f"{toReadableTime(int((T - r) / s)) if T > 0 and s > 0 else '--'}")
    d.values["progressSize"] = (
        f"{toReadableSize(r)}/{toReadableSize(T)}" if T > 0 else toReadableSize(r))

    if seq == 0:
        doc = XmlDocument()
        doc.load_xml(_progress_xml(task.name, _running.get(task.taskId, "")))
        toast = ToastNotification(doc)
        toast.tag = task.taskId
        toast.group = _GROUP
        toast.data = d
        _notifier.show(toast)
    else:
        _notifier.update_with_tag_and_group(d, task.taskId, _GROUP)
    _seq[task.taskId] = seq
