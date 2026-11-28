from __future__ import annotations

from collections.abc import Callable, Coroutine
from dataclasses import replace
from typing import TYPE_CHECKING

from app.config.cfg import NoticeStyle, TaskPopupPlace, cfg
from app.platform.desktop_notification import (
    DoNotDisturb, PopupNotifier, PopupStack, SystemNotifier,
    buildDiskSpaceInsufficient, buildTaskCompleted, buildTaskFailed,
    createDoNotDisturb, toFileIcon,
)

if TYPE_CHECKING:
    from desktop_notifier.common import Notification

    from app.models.task import Task
    from app.services.task_service import TaskService
    from app.signal import Signal

MAX_SHOWN_TASK_POPUPS = 3
TASK_POPUP_PREFIX = "task:"


class Notifier:
    def __init__(
        self,
        taskService: TaskService,
        speedChanged: Signal,
        submit: Callable[[Coroutine], object],
        activate: Callable[[], None],
        isWindowAway: Callable[[], bool],
    ) -> None:
        self._taskService = taskService
        self._speedChanged = speedChanged
        self._activate = activate
        self._isWindowAway = isWindowAway
        self._isClosed = False
        self._candidates: set[str] = set()

        systemNotifier = SystemNotifier(submit)
        self._sendTo: dict[NoticeStyle, Callable[[Notification], None]] = {
            NoticeStyle.SYSTEM: systemNotifier.send,
            NoticeStyle.OFF: lambda _: None,
        }
        self._doNotDisturb: DoNotDisturb | None = None
        self._popupStack: PopupStack | None = None
        self._popupNotifier: PopupNotifier | None = None
        if NoticeStyle.POPUP in cfg.noticeStyle.options:
            self._doNotDisturb = createDoNotDisturb()
            self._popupStack = PopupStack(self._doNotDisturb)
            self._popupNotifier = PopupNotifier(self._popupStack)
            self._sendTo[NoticeStyle.POPUP] = self._popupNotifier.send

        if self._popupStack is not None:
            taskService.taskAdded.connect(self._onTaskAdded)
            taskService.taskStarted.connect(self._onTaskStarted)
            taskService.taskRemoved.connect(self._onTaskRemoved)
            taskService.taskFailed.connect(self._onTaskFailed)
        taskService.taskCompleted.connect(self._onTaskCompleted)
        taskService.diskSpaceInsufficient.connect(self._onDiskSpaceInsufficient)

    def send(self, notification: Notification) -> None:
        if self._isClosed:
            return
        self._sendTo[cfg.noticeStyle.value](self._applySoundPolicy(notification))

    def request(
        self,
        requestId: str,
        notification: Notification | None,
        fallback: Callable[[], None] | None = None,
    ) -> None:
        if self._isClosed:
            return
        if notification is not None and self._popupNotifier is not None and self._isWindowAway():
            self._popupNotifier.send(notification, requestId)
            return
        if self._popupStack is not None:
            self._popupStack.close(requestId)
        if fallback is not None:
            fallback()

    def openTaskPopup(self, task: Task) -> None:
        self._openTaskPopup(task, minimized=False)

    def close(self) -> None:
        if self._isClosed:
            return
        self._isClosed = True
        self._candidates.clear()
        if self._popupStack is not None:
            self._taskService.taskAdded.disconnect(self._onTaskAdded)
            self._taskService.taskStarted.disconnect(self._onTaskStarted)
            self._taskService.taskRemoved.disconnect(self._onTaskRemoved)
            self._taskService.taskFailed.disconnect(self._onTaskFailed)
        self._taskService.taskCompleted.disconnect(self._onTaskCompleted)
        self._taskService.diskSpaceInsufficient.disconnect(self._onDiskSpaceInsufficient)
        if self._doNotDisturb is not None:
            self._doNotDisturb.close()
        if self._popupStack is not None:
            self._popupStack.clear()

    def _applySoundPolicy(self, notification: Notification) -> Notification:
        if not cfg.isNoticeSoundEnabled.value:
            return replace(notification, sound=None)
        return notification

    def _openTaskPopup(self, task: Task, minimized: bool) -> None:
        if self._isClosed or self._popupStack is None:
            return
        popupId = f"{TASK_POPUP_PREFIX}{task.taskId}"
        if (popup := self._popupStack.popup(popupId)) is not None:
            if minimized or not popup.isMinimized():
                return
            if self._popupStack.countShown(TASK_POPUP_PREFIX) >= MAX_SHOWN_TASK_POPUPS:
                return
            popup.showNormal()
            return
        if not minimized and self._popupStack.countShown(TASK_POPUP_PREFIX) >= MAX_SHOWN_TASK_POPUPS:
            return
        from app.view.shell.task_popup import TaskPopup
        popup = TaskPopup(task, self._taskService, self._speedChanged)
        popup.openOnTaskbar = minimized
        self._popupStack.add(popup)

    def _onTaskAdded(self, task: Task) -> None:
        self._candidates.add(task.taskId)

    def _onTaskStarted(self, task: Task) -> None:
        if task.taskId not in self._candidates:
            return
        self._candidates.discard(task.taskId)
        if cfg.noticeStyle.value != NoticeStyle.POPUP or cfg.taskPopupPlace.value == TaskPopupPlace.OFF:
            return
        self._openTaskPopup(task, minimized=cfg.taskPopupPlace.value == TaskPopupPlace.TASKBAR)

    def _onTaskRemoved(self, taskId: str) -> None:
        self._candidates.discard(taskId)
        if self._popupStack is not None:
            self._popupStack.close(f"{TASK_POPUP_PREFIX}{taskId}")

    def _onTaskCompleted(self, task: Task) -> None:
        if self._isClosed:
            return
        notice = buildTaskCompleted(task, toFileIcon(task.outputPath))
        popupId = f"{TASK_POPUP_PREFIX}{task.taskId}"
        if self._popupNotifier is not None and self._popupStack is not None and self._popupStack.has(popupId):
            self._popupNotifier.send(self._applySoundPolicy(notice), popupId)
            return
        self.send(notice)

    def _onTaskFailed(self, task: Task) -> None:
        if self._isClosed:
            return
        popupId = f"{TASK_POPUP_PREFIX}{task.taskId}"
        if self._popupNotifier is not None and self._popupStack is not None and self._popupStack.has(popupId):
            self._popupNotifier.send(buildTaskFailed(task, self._activate), popupId)

    def _onDiskSpaceInsufficient(self, free: int, needed: int) -> None:
        self.send(buildDiskSpaceInsufficient(free, needed, self._activate))
