"""桌面通知模块。Win10+ → 原生 Toast；其他 → desktop_notifier。"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QCoreApplication, QFileInfo, QStandardPaths, Qt
from PySide6.QtWidgets import QFileIconProvider
from loguru import logger

tr = QCoreApplication.translate
from app.platform.desktop import openFile, revealInFolder

if TYPE_CHECKING:
    from app.models.task import Task
    from desktop_notifier import DesktopNotifier

notifier: DesktopNotifier | None = None


def _file_icon(path: str) -> str:
    p = Path(QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.TempLocation)) / "gd_finished_icon.png"
    try:
        QFileIconProvider().icon(QFileInfo(path)).pixmap(48, 48).scaled(
            128, 128, aspectMode=Qt.AspectRatioMode.KeepAspectRatio,
            mode=Qt.TransformationMode.SmoothTransformation,
        ).save(str(p), "PNG")
    except Exception:
        return ""
    return str(p) if p.exists() else ""


# ═══ 初始化 ═════════════════════════════════════════════════════════

async def init() -> None:
    from app.platform.windows import isGreaterEqualWin10
    if isGreaterEqualWin10():
        _init_win()
    else:
        await _init_other()


async def _init_other() -> None:
    from desktop_notifier import DesktopNotifier as DN, Icon
    icon = Path(QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.TempLocation)) / "gd3_logo.png"
    if not icon.exists():
        from PySide6.QtCore import QResource
        with open(icon, "wb") as f:
            f.write(QResource(":/image/logo.png").data())
    global notifier
    notifier = DN(app_name="Ghost Downloader", app_icon=Icon(path=icon))


def _init_win() -> None:
    from app.platform.windows_toast import init as win_init
    win_init()


# ═══ 通知 ═══════════════════════════════════════════════════════════

def notifyDiskSpaceInsufficient(free: int, needed: int) -> None:
    from app.format import toReadableSize
    if notifier is None:
        from app.platform.windows_toast import show_text
        show_text("disk", tr("Notifications", "磁盘空间不足"),
                  tr("Notifications", "剩余 {0}，需要 {1}，任务未自动启动"
                     ).format(toReadableSize(free), toReadableSize(needed)))
        return
    from app.services.coroutine_runner import coroutineRunner
    coroutineRunner.submit(notifier.send(
        title=tr("Notifications", "Disk space insufficient"),
        message=tr("Notifications",
                   "Remaining {0}, need {1}, task not auto-started"
                   ).format(toReadableSize(free), toReadableSize(needed)),
    ))


def notifyTaskStarted(task: Task) -> None:
    if notifier is not None:
        return
    from app.platform.windows_toast import task_started
    task_started(task)


def notifyTaskCompleted(task: Task) -> None:
    if not task.outputPath:
        return
    if notifier is not None:
        icon = _file_icon(task.outputPath)
        from desktop_notifier import Icon, Button
        from app.services.coroutine_runner import coroutineRunner
        path = task.outputPath
        coroutineRunner.submit(notifier.send(
            title=tr("Notifications", "Download completed"),
            message=task.name,
            buttons=[
                Button(title=tr("Notifications", "Open file"),
                       on_pressed=lambda p=path: openFile(p)),
                Button(title=tr("Notifications", "Open folder"),
                       on_pressed=lambda p=path: revealInFolder(p)),
            ],
            on_clicked=lambda p=path: openFile(p),
            icon=Icon(path=icon) if icon else None,
        ))
        return
    from app.platform.windows_toast import task_completed
    task_completed(task)


def notifyTaskFailed(task: Task) -> None:
    if notifier is not None:
        return
    from app.platform.windows_toast import task_failed
    task_failed(task)
