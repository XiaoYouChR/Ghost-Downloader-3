from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QEvent, QPoint, Qt, QTimer
from PySide6.QtGui import QColor, QTextOption
from PySide6.QtWidgets import QDialog, QFileDialog, QHBoxLayout, QVBoxLayout
from qframelesswindow import FramelessDialog
from qfluentwidgets import (
    FluentIcon, FluentStyleSheet, FluentTitleBar,
    IndeterminateProgressBar, InfoBar, InfoBarPosition,
    MessageBoxBase, PushButton, SubtitleLabel,
)

from app.platform.android import IS_ANDROID
from app.view.components.card_groups import DraftCardGroup, OptionCardGroup
from app.view.components.editors import AutoSizingEdit
from app.view.components.option_cards import OutputFolderCard, SubworkerCountCard

if TYPE_CHECKING:
    from app.models.task import Task
    from app.services.category_service import CategoryService
    from app.services.feature_service import FeatureService
    from app.services.task_draft import TaskDraft


class StandaloneWrapper(FramelessDialog):

    def __init__(self, dialog: TaskDraftDialog):
        super().__init__()
        self._dialog = dialog
        self.contentLayout = QVBoxLayout(self)

        self._initWidget()
        self._initLayout()

    def _initWidget(self) -> None:
        self.setResizeEnabled(False)
        titleBar = FluentTitleBar(self)
        self.setTitleBar(titleBar)
        self.titleBar.maxBtn.hide()
        self.titleBar.iconLabel.hide()
        self.titleBar.setDoubleClickEnabled(False)
        self.titleBar.setFixedHeight(30)
        self.setWindowTitle(self._dialog.tr("添加任务"))
        FluentStyleSheet.DIALOG.apply(self)

    def _initLayout(self) -> None:
        self.contentLayout.setContentsMargins(0, 30, 0, 0)
        self.contentLayout.setSpacing(0)

    def setContent(self, widget) -> None:
        self.contentLayout.addWidget(widget)

    def takeContent(self, widget) -> None:
        self.contentLayout.removeWidget(widget)

    def closeEvent(self, event) -> None:
        event.ignore()
        self._dialog.reject()


class TaskDraftDialog(MessageBoxBase):

    def __init__(self, draft: TaskDraft, featureService: FeatureService, categoryService: CategoryService, parent: QWidget | None = None):
        self._isDragEnabled = not IS_ANDROID
        super().__init__(parent)
        self._draft = draft
        self._featureService = featureService
        self._categoryService = categoryService
        self._parseTimer = QTimer(self, singleShot=True)
        self._standaloneWrapper = StandaloneWrapper(self)
        self.destroyed.connect(self._standaloneWrapper.deleteLater)
        self._isStandalone = False
        self._dragPos = QPoint()
        self._cardByUrl: dict[str, object] = {}
        self._failCount = 0

        self.titleLabel = SubtitleLabel(self.tr("添加任务"), self)
        self.urlEdit = AutoSizingEdit(self)
        self.progressBar = IndeterminateProgressBar(self)
        self.draftGroup = DraftCardGroup(self)
        self.optionGroup = OptionCardGroup(self)
        self.batchButton = PushButton(FluentIcon.COPY, self.tr("批量添加"), self)
        self.importButton = PushButton(FluentIcon.FOLDER_ADD, self.tr("导入文件"), self)
        self.headerLayout = QHBoxLayout()

        self._initWidget()
        self._initLayout()
        self._bind()

    @property
    def isActive(self) -> bool:
        return self.isVisible() or (self._isStandalone and self._standaloneWrapper.isVisible())

    def _initWidget(self) -> None:
        self.hide()
        self.widget.setFixedWidth(700)
        self.urlEdit.setPlaceholderText(self.tr("添加多个下载链接时，请确保每行只有一个下载链接"))
        self.urlEdit.setWordWrapMode(QTextOption.WrapMode.NoWrap)
        self.progressBar.hide()
        self._fileTypes = self._featureService.fileTypes()
        self.importButton.setVisible(bool(self._fileTypes))

        self.optionGroup.addCard(OutputFolderCard(self.optionGroup))
        self.optionGroup.addCard(SubworkerCountCard(self.optionGroup))

    def _initLayout(self) -> None:
        self.headerLayout.addWidget(self.titleLabel)
        self.headerLayout.addStretch(1)
        self.headerLayout.addWidget(self.batchButton)
        self.headerLayout.addWidget(self.importButton)
        self.viewLayout.addLayout(self.headerLayout)
        self.viewLayout.addWidget(self.urlEdit)
        self.viewLayout.addWidget(self.progressBar)
        self.viewLayout.addWidget(self.draftGroup)
        self.viewLayout.addWidget(self.optionGroup)

    def _bind(self) -> None:
        self._parseTimer.setInterval(1000)
        self._parseTimer.timeout.connect(self._onParseNeeded)
        self.urlEdit.textChanged.connect(self._parseTimer.start)

        self._draft.parsingBusyChanged.connect(self.progressBar.setVisible)
        self._draft.parseSucceeded.connect(self._onParseSucceeded)
        self._draft.parseFailed.connect(self._onParseFailed)
        self._draft.itemsChanged.connect(self._onItemsChanged)
        self._draft.itemsCleared.connect(self._onCleared)

        self.batchButton.clicked.connect(self._onBatchClicked)
        self.importButton.clicked.connect(self._onImportClicked)

    def showStandalone(self) -> None:
        from app.platform.desktop import raiseWindow

        if self._isStandalone and self._standaloneWrapper.isVisible():
            raiseWindow(self._standaloneWrapper)
            return

        if self.isVisible() and not self._isStandalone:
            self.setGraphicsEffect(None)
            self.widget.setGraphicsEffect(None)
            QDialog.done(self, QDialog.DialogCode.Rejected)

        if not self._isStandalone:
            self._toStandalone()

        raiseWindow(self._standaloneWrapper)

    def showMask(self) -> int:
        if self._isStandalone:
            self._toMask()

        parent = self.parentWidget()
        if parent is not None:
            self.setGeometry(0, 0, parent.width(), parent.height())
            self.windowMask.resize(self.size())
        self.setShadowEffect(60, (0, 10), QColor(0, 0, 0, 50))
        self.setMaskColor(QColor(0, 0, 0, 76))
        return self.exec()

    def addUrls(self, urls: list[str]) -> None:
        if not urls:
            return
        existing = set(self._urls())
        toAdd = [stripped for u in urls if (stripped := u.strip()) and stripped not in existing]
        if not toAdd:
            return
        self.urlEdit.appendPlainText("\n".join(toAdd))
        self._parseTimer.stop()
        self._onParseNeeded()

    def addParsedTasks(self, tasks: list[Task]) -> None:
        if not tasks:
            return
        newUrls = self._draft.addParsedTasks(tasks)
        if newUrls:
            self.urlEdit.appendPlainText("\n".join(newUrls))
        self._parseTimer.stop()

    def done(self, code: int) -> None:
        if code == QDialog.DialogCode.Accepted:
            self._draft.confirm()
        else:
            self._draft.clear()

        self.urlEdit.clear()
        self.optionGroup.reset()
        self._parseTimer.stop()
        self._cardByUrl.clear()
        self._failCount = 0
        self.draftGroup.clear()
        self.draftGroup.updateStats(0, 0, 0)

        if self._isStandalone:
            self._standaloneWrapper.hide()
        else:
            super().done(code)

    def validate(self) -> bool:
        self._parseTimer.stop()
        self._onParseNeeded()
        return self._draft.canConfirm()

    def eventFilter(self, obj, event: QEvent):
        if obj is not self.windowMask or not self._isDragEnabled:
            return super().eventFilter(obj, event)

        if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            self._dragPos = event.pos()
            return True

        if event.type() == QEvent.Type.MouseMove and not self._dragPos.isNull():
            window = self.window()
            if window.isMaximized():
                window.showNormal()
            position = window.pos() + event.pos() - self._dragPos
            position.setX(max(0, position.x()))
            position.setY(max(0, position.y()))
            window.move(position)
            return True

        if event.type() == QEvent.Type.MouseButtonRelease:
            self._dragPos = QPoint()

        return super().eventFilter(obj, event)

    def _toStandalone(self) -> None:
        self._hBoxLayout.removeWidget(self.widget)
        self._standaloneWrapper.setContent(self.widget)
        self.widget.setStyleSheet("#centerWidget { border: none; border-radius: 0; }")
        self.widget.show()
        self._isStandalone = True

    def _toMask(self) -> None:
        self._standaloneWrapper.hide()
        self._standaloneWrapper.takeContent(self.widget)
        self.widget.setStyleSheet("")
        self._hBoxLayout.addWidget(self.widget, 1, Qt.AlignmentFlag.AlignCenter)
        self.widget.show()
        self._isStandalone = False

    def _onParseNeeded(self) -> None:
        self._draft.setBaseOptions(self.optionGroup.options())
        self._draft.setUrls(self._urls())

    def _onParseSucceeded(self, url: str, task: Task) -> None:
        card = self._featureService.draftCard(task, self.draftGroup)
        card.categoryPicked.connect(lambda cid: self._draft.setUrlCategory(url, cid))
        card.editRequested.connect(lambda u=url: self._onEditRequested(u))
        self.draftGroup.addCard(url, card)
        self._cardByUrl[url] = card
        self._refreshStats()

    def _onEditRequested(self, url: str) -> None:
        from app.view.dialogs.edit_task import DraftEditDialog

        task = self._draft.taskByUrl(url)
        if task is None:
            return
        dialog = DraftEditDialog(task, self._featureService.optionCards(task, self.window()), self.window())
        dialog.exec()

    def _onParseFailed(self, url: str, error: str) -> None:
        self._failCount += 1
        self._refreshStats()
        displayUrl = url if len(url) <= 48 else f"{url[:45]}..."
        InfoBar.error(
            self.tr("链接解析失败"),
            f"{displayUrl}\n{error}",
            duration=5000,
            position=InfoBarPosition.BOTTOM_RIGHT,
            parent=self,
        )

    def _onItemsChanged(self) -> None:
        self.draftGroup.setUrls(self._draft.urls())
        self._refreshStats()

    def _onCleared(self) -> None:
        self._cardByUrl.clear()
        self._failCount = 0
        self.draftGroup.clear()
        self.draftGroup.updateStats(0, 0, 0)

    def _refreshStats(self) -> None:
        tasks = [self._draft.taskByUrl(url) for url in self._draft.urls()]
        successCount = sum(1 for t in tasks if t is not None)
        totalSize = sum(t.fileSize for t in tasks if t is not None and t.fileSize > 0)
        self.draftGroup.updateStats(successCount, self._failCount, totalSize)

    def _urls(self) -> list[str]:
        text = self.urlEdit.toPlainText()
        if not text:
            return []
        return [line.strip() for line in text.splitlines() if line.strip()]

    def _onBatchClicked(self) -> None:
        from app.view.dialogs.batch_url import BatchUrlDialog
        parent = self._standaloneWrapper if self._isStandalone else self.window()
        dialog = BatchUrlDialog(parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.addUrls(dialog.urls())
        dialog.deleteLater()

    def _onImportClicked(self) -> None:
        globs = [f"*{ext}" for ft in self._fileTypes for ext in ft.extensions]
        nameFilters = [self.tr("所有可导入文件 ({0})").format(" ".join(globs))]
        nameFilters += [
            f"{ft.displayName} ({' '.join(f'*{ext}' for ext in ft.extensions)})"
            for ft in self._fileTypes
        ]
        paths, _ = QFileDialog.getOpenFileNames(self, self.tr("导入文件"), "", ";;".join(nameFilters))
        if paths:
            self.addUrls([Path(p).as_uri() for p in paths])
