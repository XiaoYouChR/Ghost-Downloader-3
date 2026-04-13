# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportAttributeAccessIssue=false, reportCallIssue=false, reportAny=false, reportImplicitOverride=false, reportMissingTypeStubs=false

"""Default host-owned task cards for Feature Pack V1."""

from __future__ import annotations

from typing import cast
from typing import Protocol
from typing import final

from PySide6.QtCore import Qt
from PySide6.QtCore import Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QHBoxLayout
from PySide6.QtWidgets import QVBoxLayout
from PySide6.QtWidgets import QWidget
from qfluentwidgets import BodyLabel
from qfluentwidgets import CaptionLabel
from qfluentwidgets import CardWidget
from qfluentwidgets import FluentIcon
from qfluentwidgets import ProgressBar
from qfluentwidgets import StrongBodyLabel
from qfluentwidgets import ToolButton

from app.supports.utils import getReadableSize

from ..api.form import EditMode
from ..api.snapshot import TaskSnapshot
from ..api.task import Task


class _SupportsTaskEditing(Protocol):
    """Minimal host interface required by the default cards."""

    def editTask(
        self,
        task: Task,
        mode: EditMode,
        parent: QWidget | None = None,
    ) -> bool:
        """Open the host task editor for the given task."""
        ...


def _progressValue(progress: float) -> int:
    return max(0, min(100, int(round(progress))))


def _progressText(snapshot: TaskSnapshot) -> str:
    totalText = getReadableSize(snapshot.totalBytes) if snapshot.totalBytes > 0 else "--"
    return "{0:.1f}%  {1} / {2}".format(
        max(0.0, min(snapshot.progress, 100.0)),
        getReadableSize(snapshot.doneBytes),
        totalText,
    )


@final
class DefaultTaskCard(CardWidget):
    """Default task card that forwards edit requests and commands to the task."""

    editRequested: Signal = Signal(object, object, object)
    commandRequested: Signal = Signal(object, object)

    def __init__(
        self,
        *,
        task: Task,
        editor: _SupportsTaskEditing,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.task = task
        self._editor = editor
        self._editMode: EditMode = "running"

        self.mainLayout = QHBoxLayout(self)
        self.infoLayout = QVBoxLayout()
        self.metaLayout = QHBoxLayout()
        self.nameLabel = StrongBodyLabel("", self)
        self.stateLabel = CaptionLabel("", self)
        self.targetLabel = CaptionLabel("", self)
        self.progressLabel = BodyLabel("", self)
        self.progressBar = ProgressBar(self)
        self.editButton = ToolButton(FluentIcon.EDIT, self)

        self._initWidget()
        self._connectSignals()
        self.refresh()

    def _initWidget(self) -> None:
        self.setObjectName("defaultTaskCard")
        self.setFixedHeight(110)

        self.progressBar.setObjectName("defaultTaskCardProgressBar")
        self.progressBar.setRange(0, 100)

        self.editButton.setObjectName("defaultTaskCardEditButton")
        self.editButton.setToolTip(self.tr("编辑任务"))

        self.mainLayout.setContentsMargins(16, 12, 16, 12)
        self.mainLayout.setSpacing(12)
        self.infoLayout.setContentsMargins(0, 0, 0, 0)
        self.infoLayout.setSpacing(6)
        self.metaLayout.setContentsMargins(0, 0, 0, 0)
        self.metaLayout.setSpacing(12)

        self.metaLayout.addWidget(self.stateLabel)
        self.metaLayout.addWidget(self.progressLabel)
        self.metaLayout.addStretch(1)

        self.infoLayout.addWidget(self.nameLabel)
        self.infoLayout.addLayout(self.metaLayout)
        self.infoLayout.addWidget(self.targetLabel)
        self.infoLayout.addWidget(self.progressBar)

        self.mainLayout.addLayout(self.infoLayout, 1)
        self.mainLayout.addWidget(self.editButton)

    def _connectSignals(self) -> None:
        _ = self.editButton.clicked.connect(self._requestEdit)
        _ = self.editRequested.connect(self._forwardEditRequest)
        _ = self.commandRequested.connect(self._forwardTaskCommand)
        _ = self.task.stateChanged.connect(self._onTaskStateChanged)
        _ = self.task.progressChanged.connect(self._onTaskProgressChanged)
        _ = self.task.snapshotChanged.connect(self._onSnapshotChanged)

    def _onTaskStateChanged(self, _state: str) -> None:
        self.refresh()

    def _onTaskProgressChanged(self, _progress: float) -> None:
        self.refresh()

    def _onSnapshotChanged(self, snapshot: object) -> None:
        if isinstance(snapshot, TaskSnapshot):
            self.refresh(snapshot)
            return

        self.refresh()

    def _requestEdit(self) -> None:
        self.editRequested.emit(self.task, self._editMode, self)

    def _forwardEditRequest(self, task: object, mode: object, parent: object) -> None:
        if not isinstance(task, Task):
            return
        if mode not in {"before", "running"}:
            return

        parentWidget = parent if isinstance(parent, QWidget) else self
        _ = self._editor.editTask(task, cast(EditMode, mode), parentWidget)

    def requestTaskCommand(
        self,
        command: str,
        payload: object | None = None,
    ) -> None:
        self.commandRequested.emit(command, payload)

    def _forwardTaskCommand(self, command: object, payload: object) -> None:
        if not isinstance(command, str):
            return

        self.task.requestCommand(command, payload)

    def refresh(self, snapshot: TaskSnapshot | None = None) -> None:
        taskSnapshot = snapshot or self.task.snapshot()
        self.nameLabel.setText(taskSnapshot.name)
        self.stateLabel.setText(self.tr("状态: {0}").format(taskSnapshot.state))
        self.progressLabel.setText(_progressText(taskSnapshot))
        self.targetLabel.setText(taskSnapshot.target or self.tr("未设置输出目标"))
        self.progressBar.setValue(_progressValue(taskSnapshot.progress))


@final
class DefaultResultCard(CardWidget):
    """Default parse/result card that delegates editing to the host."""

    editRequested: Signal = Signal(object, object, object)

    def __init__(
        self,
        *,
        task: Task,
        editor: _SupportsTaskEditing,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.task = task
        self._editor = editor
        self._editMode: EditMode = "before"

        self.mainLayout = QHBoxLayout(self)
        self.infoLayout = QVBoxLayout()
        self.nameLabel = StrongBodyLabel("", self)
        self.detailLabel = CaptionLabel("", self)
        self.editButton = ToolButton(FluentIcon.EDIT, self)

        self._initWidget()
        self._connectSignals()
        self.refresh()

    def _initWidget(self) -> None:
        self.setObjectName("defaultResultCard")
        self.setFixedHeight(72)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self.editButton.setObjectName("defaultResultCardEditButton")
        self.editButton.setToolTip(self.tr("编辑任务"))

        self.mainLayout.setContentsMargins(16, 12, 16, 12)
        self.mainLayout.setSpacing(12)
        self.infoLayout.setContentsMargins(0, 0, 0, 0)
        self.infoLayout.setSpacing(4)

        self.infoLayout.addWidget(self.nameLabel)
        self.infoLayout.addWidget(self.detailLabel)

        self.mainLayout.addLayout(self.infoLayout, 1)
        self.mainLayout.addWidget(self.editButton)

    def _connectSignals(self) -> None:
        _ = self.editButton.clicked.connect(self._requestEdit)
        _ = self.editRequested.connect(self._forwardEditRequest)
        _ = self.task.snapshotChanged.connect(self._onSnapshotChanged)

    def _onSnapshotChanged(self, snapshot: object) -> None:
        if isinstance(snapshot, TaskSnapshot):
            self.refresh(snapshot)
            return

        self.refresh()

    def _requestEdit(self) -> None:
        self.editRequested.emit(self.task, self._editMode, self)

    def _forwardEditRequest(self, task: object, mode: object, parent: object) -> None:
        if not isinstance(task, Task):
            return
        if mode not in {"before", "running"}:
            return

        parentWidget = parent if isinstance(parent, QWidget) else self
        _ = self._editor.editTask(task, cast(EditMode, mode), parentWidget)

    def refresh(self, snapshot: TaskSnapshot | None = None) -> None:
        taskSnapshot = snapshot or self.task.snapshot()
        self.nameLabel.setText(taskSnapshot.name)
        self.detailLabel.setText(
            self.tr("目标: {0}").format(taskSnapshot.target or self.tr("未设置输出目标"))
        )

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._requestEdit()
            event.accept()
            return

        super().mouseDoubleClickEvent(event)


__all__ = ["DefaultResultCard", "DefaultTaskCard"]
