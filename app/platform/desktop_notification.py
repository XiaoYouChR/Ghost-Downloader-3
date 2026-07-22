from __future__ import annotations

from pathlib import Path
from typing import Callable, TYPE_CHECKING

from PySide6.QtCore import QCoreApplication, QFileInfo, QStandardPaths, Qt
from PySide6.QtWidgets import QFileIconProvider
from loguru import logger

from app.platform.desktop import openFile, revealInFolder

if TYPE_CHECKING:
    from app.models.task import Task
    from desktop_notifier import DesktopNotifier

notifier: DesktopNotifier | None = None
_submit: Callable | None = None


async def init(submit: Callable) -> None:
    global _submit
    _submit = submit
    from desktop_notifier import DesktopNotifier as DN, Icon

    iconPath = Path(QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.TempLocation
    )) / "gd3_logo.png"
    if not iconPath.exists():
        from PySide6.QtCore import QResource
        with open(iconPath, "wb") as f:
            f.write(QResource(":/image/logo.png").data())

    global notifier
    notifier = DN(app_name="Ghost Downloader", app_icon=Icon(path=iconPath))


def notifyDiskSpaceInsufficient(free: int, needed: int) -> None:
    if notifier is None:
        return
    from app.format import toReadableSize
    _submit(notifier.send(
        title=QCoreApplication.translate("Notifications", "磁盘空间不足"),
        message=QCoreApplication.translate("Notifications", "剩余 {0}，需要 {1}，任务未自动开始").format(
            toReadableSize(free), toReadableSize(needed)),
    ))


def notifyTaskCompleted(task: Task) -> None:
    if notifier is None:
        return

    outputPath = task.outputPath
    if not outputPath:
        return

    iconPath = Path(QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.TempLocation
    )) / "gd_finished_icon.png"

    try:
        QFileIconProvider().icon(QFileInfo(outputPath)).pixmap(48, 48).scaled(
            128, 128,
            aspectMode=Qt.AspectRatioMode.KeepAspectRatio,
            mode=Qt.TransformationMode.SmoothTransformation,
        ).save(str(iconPath), "PNG")
    except Exception as e:
        logger.debug("提取文件图标失败: {}", e)

    from desktop_notifier import Icon, Button

    _submit(notifier.send(
        title=QCoreApplication.translate("Notifications", "下载完成"),
        message=task.name,
        buttons=[
            Button(title=QCoreApplication.translate("Notifications", "打开文件"), on_pressed=lambda: openFile(outputPath)),
            Button(title=QCoreApplication.translate("Notifications", "打开文件夹"), on_pressed=lambda: revealInFolder(outputPath)),
        ],
        on_clicked=lambda: openFile(outputPath),
        icon=Icon(path=iconPath) if iconPath.exists() else None,
    ))
