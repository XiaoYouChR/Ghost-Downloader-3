# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportAttributeAccessIssue=false, reportCallIssue=false, reportAny=false, reportImplicitOverride=false, reportMissingTypeStubs=false, reportArgumentType=false, reportPrivateUsage=false, reportUnknownLambdaType=false, reportUnusedCallResult=false

"""Default host-owned task cards for Feature Pack V1."""

from __future__ import annotations

from typing import cast
from typing import Protocol
from typing import final

from PySide6.QtCore import Qt
from PySide6.QtCore import Signal
from PySide6.QtCore import QMimeData
from PySide6.QtGui import QContextMenuEvent
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QHBoxLayout
from PySide6.QtWidgets import QVBoxLayout
from PySide6.QtWidgets import QWidget
from PySide6.QtWidgets import QApplication
from qfluentwidgets import BodyLabel
from qfluentwidgets import CaptionLabel
from qfluentwidgets import CardWidget
from qfluentwidgets import CheckBox
from qfluentwidgets import Action
from qfluentwidgets import FluentIcon
from qfluentwidgets import ProgressBar
from qfluentwidgets import RoundMenu
from qfluentwidgets import StrongBodyLabel
from qfluentwidgets import ToolButton

from app.supports.config import GD3_COPY_MIME_TYPE
from app.supports.utils import getReadableSize
from app.supports.utils import openFile

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

    deleted: Signal = Signal()
    finished: Signal = Signal()
    selectionChanged: Signal = Signal(bool, bool)
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
        self._selectionMode = False
        self._finishedEmitted = False

        self.mainLayout = QHBoxLayout(self)
        self.infoLayout = QVBoxLayout()
        self.metaLayout = QHBoxLayout()
        self.checkBox = CheckBox(self)
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

        self.checkBox.setFixedSize(23, 23)
        self.checkBox.hide()
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

        self.mainLayout.addWidget(self.checkBox)
        self.mainLayout.addLayout(self.infoLayout, 1)
        self.mainLayout.addWidget(self.editButton)

    def _connectSignals(self) -> None:
        _ = self.checkBox.clicked.connect(lambda checked: self.selectionChanged.emit(checked, False))
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
        if taskSnapshot.state.lower() == "completed" and not self._finishedEmitted:
            self._finishedEmitted = True
            self.finished.emit()

    def setSelectionMode(self, isSelected: bool) -> None:
        self._selectionMode = isSelected
        self.checkBox.setVisible(isSelected)
        if not isSelected:
            self.checkBox.setChecked(False)
        self.update()

    def isChecked(self) -> bool:
        return self.checkBox.isChecked()

    def setChecked(self, checked: bool) -> None:
        if checked == self.isChecked():
            return
        self.checkBox.setChecked(checked)
        self.update()

    def resumeTask(self) -> None:
        from app.services.core_service import coreService

        coreService.createTask(self.task)

    def pauseTask(self) -> None:
        from app.services.core_service import coreService

        coreService.stopTask(self.task)

    def redownloadTask(self) -> None:
        self.task.requestCommand("reset")
        self.resumeTask()

    def removeTask(self, _deleteFile: bool = False) -> None:
        from app.services.core_service import coreService

        coreService.runCoroutine(
            coreService._stopTask(self.task),
            lambda _result, error: self._onTaskStoppedForDeletion(error),
        )

    def _onTaskStoppedForDeletion(self, error: str | None = None) -> None:
        if error:
            return

        self.deleted.emit()

    def createContextMenu(self) -> RoundMenu:
        menu = RoundMenu(parent=self)
        copyUrlAction = Action(FluentIcon.COPY, self.tr("复制下载链接"), self)
        _ = copyUrlAction.triggered.connect(self._copyTaskSource)
        menu.addAction(copyUrlAction)
        redownloadAction = Action(FluentIcon.UPDATE, self.tr("重新下载"), self)
        _ = redownloadAction.triggered.connect(self.redownloadTask)
        menu.addAction(redownloadAction)
        return menu

    def _copyTaskSource(self) -> None:
        clipboard = QApplication.clipboard()
        mimeData = QMimeData()
        mimeData.setText(self.task.config.source)
        mimeData.setData(GD3_COPY_MIME_TYPE, b"1")
        clipboard.setMimeData(mimeData)

    def mouseReleaseEvent(self, e: QMouseEvent) -> None:
        super().mouseReleaseEvent(e)
        if e.button() != Qt.MouseButton.LeftButton:
            return

        extend = bool(e.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        checked = True if extend or not self._selectionMode else not self.isChecked()
        self.selectionChanged.emit(checked, extend)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            snapshot = self.task.snapshot()
            if snapshot.target:
                openFile(snapshot.target)
            event.accept()
            return

        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        menu = self.createContextMenu()
        menu.exec(event.globalPos())
        event.accept()


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

    def getTask(self) -> Task:
        return self.task

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._requestEdit()
            event.accept()
            return

        super().mouseDoubleClickEvent(event)


__all__ = ["DefaultResultCard", "DefaultTaskCard"]
