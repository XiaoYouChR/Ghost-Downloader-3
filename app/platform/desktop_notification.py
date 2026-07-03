from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QCoreApplication, QFileInfo, QStandardPaths, Qt, QTimer
from PySide6.QtWidgets import QFileIconProvider

tr = QCoreApplication.translate

from app.platform.desktop import openFile, revealInFolder

if TYPE_CHECKING:
    from app.models.task import Task
    from desktop_notifier import DesktopNotifier

notifier: DesktopNotifier | None = None
_running_tasks: dict[str, bool] = {}
_progress_timer: QTimer | None = None


def _is_win10() -> bool:
    from app.platform.windows import isGreaterEqualWin10
    return isGreaterEqualWin10()


# ═══ 初始化 ═══════════════════════════════════════════════════════

async def init() -> None:
    if _is_win10():
        from app.platform.windows_toast import _ensure_aumid_registered
        _ensure_aumid_registered()
    else:
        await _init_desktop_notifier()


async def _init_desktop_notifier() -> None:
    from desktop_notifier import DesktopNotifier as DN, Icon
    icon = Path(QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.TempLocation)) / "gd3_logo.png"
    if not icon.exists():
        from PySide6.QtCore import QResource
        with open(icon, "wb") as f:
            f.write(QResource(":/image/logo.png").data())
    global notifier
    notifier = DN(app_name="Ghost Downloader", app_icon=Icon(path=icon))


# ═══ 图标提取 ═════════════════════════════════════════════════════

def _extract_file_icon(outputPath: str) -> str:
    p = Path(QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.TempLocation)) / "gd_finished_icon.png"
    try:
        QFileIconProvider().icon(QFileInfo(outputPath)).pixmap(48, 48).scaled(
            128, 128, aspectMode=Qt.AspectRatioMode.KeepAspectRatio,
            mode=Qt.TransformationMode.SmoothTransformation,
        ).save(str(p), "PNG")
    except Exception:
        return ""
    return str(p) if p.exists() else ""


# ═══ 通知 API ═════════════════════════════════════════════════════

def notifyDiskSpaceInsufficient(free: int, needed: int) -> None:
    from app.format import toReadableSize
    if _is_win10():
        from app.platform.windows_toast import windowsToastManager
        windowsToastManager.show_text(
            tag="disk_space",
            task_name=tr("Notifications", "剩余 {0}，需要 {1}，任务未自动启动"
                         ).format(toReadableSize(free), toReadableSize(needed)),
            subtitle=tr("Notifications", "磁盘空间不足"),
        )
        return
    if notifier is None:
        return
    from app.services.coroutine_runner import coroutineRunner
    coroutineRunner.submit(notifier.send(
        title=tr("Notifications", "Disk space insufficient"),
        message=tr("Notifications", "Remaining {0}, need {1}, task not auto-started"
                   ).format(toReadableSize(free), toReadableSize(needed)),
    ))


def notifyTaskStarted(task: Task) -> None:
    if _is_win10():
        _start_tracking(task.taskId)
        _send_progress(task)


def notifyTaskCompleted(task: Task) -> None:
    outputPath = task.outputPath
    if not outputPath:
        return
    _stop_tracking(task.taskId)
    if _is_win10():
        from app.platform.windows_toast import windowsToastManager
        windowsToastManager.show_completed(
            tag=task.taskId, task_name=task.name,
            output_path=outputPath, icon_path=_extract_file_icon(outputPath),
        )
        return
    if notifier is not None:
        _send_legacy_completed(task, outputPath)


def notifyTaskFailed(task: Task) -> None:
    _stop_tracking(task.taskId)
    if _is_win10():
        from app.platform.windows_toast import windowsToastManager
        windowsToastManager.show_failed(
            tag=task.taskId, task_name=task.name,
            icon_path=_extract_file_icon(task.outputPath) if task.outputPath else "",
        )


def _send_legacy_completed(task: Task, outputPath: str) -> None:
    from desktop_notifier import Icon, Button
    from app.services.coroutine_runner import coroutineRunner
    icon = _extract_file_icon(outputPath)
    coroutineRunner.submit(notifier.send(
        title=tr("Notifications", "Download completed"),
        message=task.name,
        buttons=[
            Button(title=tr("Notifications", "Open file"),
                   on_pressed=lambda: openFile(outputPath)),
            Button(title=tr("Notifications", "Open folder"),
                   on_pressed=lambda: revealInFolder(outputPath)),
        ],
        on_clicked=lambda: openFile(outputPath),
        icon=Icon(path=icon) if icon else None,
    ))


# ═══ 进度追踪（Win10+）═══════════════════════════════════════════

def _start_tracking(task_id: str) -> None:
    global _progress_timer
    _running_tasks[task_id] = True
    if _progress_timer is None:
        _progress_timer = QTimer()
        _progress_timer.setInterval(1500)
        _progress_timer.timeout.connect(_update_all_progress)
    if not _progress_timer.isActive():
        _progress_timer.start()


def _stop_tracking(task_id: str) -> None:
    _running_tasks.pop(task_id, None)
    if not _running_tasks and _progress_timer is not None:
        _progress_timer.stop()


def _update_all_progress() -> None:
    from app.services.task_service import taskService
    for task_id in list(_running_tasks):
        task = taskService.taskById(task_id)
        if task is None:
            _running_tasks.pop(task_id, None)
        else:
            _send_progress(task)


def _send_progress(task: Task) -> None:
    from app.platform.windows_toast import windowsToastManager
    progress, speed, received = task.currentSnapshot()
    icon = _extract_file_icon(task.outputPath) if task.outputPath else ""
    windowsToastManager.show_progress(
        tag=task.taskId, task_name=task.name,
        progress=progress, speed=speed, received_bytes=received,
        total_bytes=task.fileSize, icon_path=icon,
    )
