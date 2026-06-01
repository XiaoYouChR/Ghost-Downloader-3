from pathlib import Path
from typing import Any, Self

from PySide6.QtCore import QEvent, QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QTextOption
from PySide6.QtWidgets import QDialog, QFileDialog, QHBoxLayout, QVBoxLayout
from qfluentwidgets import (
    Action,
    BodyLabel,
    FluentIcon,
    FluentTitleBar,
    IndeterminateProgressBar,
    InfoBar,
    InfoBarPosition,
    LineEdit,
    MessageBoxBase,
    PushButton,
    Slider,
    SubtitleLabel,
)
from qfluentwidgets.common.style_sheet import FluentStyleSheet
from qframelesswindow import FramelessDialog

from app.bases.models import Task
from app.services.feature_service import featureService
from app.supports.config import cfg
from app.supports.utils import bringWindowToTop
from app.view.components.add_task_dialog_session import AddTaskParseSession
from app.view.components.card_widgets import (
    ParseResultHeaderCardWidget,
    ParseSettingHeaderCardWidget,
)
from app.view.components.cards import ParseSettingCard, ResultCard
from app.view.components.editors import AutoSizingEdit


class SelectFolderCard(ParseSettingCard):
    def __init__(self, icon, title: str, parent=None, *, initial: Path | None = None) -> None:
        self._initial = str(initial) if initial is not None else cfg.downloadFolder.value
        super().__init__(icon, title, parent)

    def initCustomWidget(self) -> None:
        self.pathEdit = LineEdit(self)
        self.selectFolderAction = Action(FluentIcon.FOLDER, self.tr("选择文件夹"), self)

        self.pathEdit.addAction(self.selectFolderAction)

        self._initWidget()
        self._initLayout()
        self._bind()

    def _initWidget(self) -> None:
        self.pathEdit.setReadOnly(True)
        self.pathEdit.setText(self._initial)

    def _initLayout(self) -> None:
        self.hBoxLayout.addWidget(self.pathEdit, stretch=3)

    def _bind(self) -> None:
        self.selectFolderAction.triggered.connect(self._selectFolder)

    def _selectFolder(self) -> None:
        path = self._currentBrowsePath()
        selectedPath = QFileDialog.getExistingDirectory(
            self,
            self.tr("选择下载路径"),
            str(path),
        )
        if not selectedPath:
            return

        self.pathEdit.setText(selectedPath)
        self.payloadChanged.emit()

    def _currentBrowsePath(self) -> Path:
        path = Path(self.pathEdit.text())
        if path.exists():
            return path.absolute()
        return path.parent

    def reset(self) -> None:
        self.pathEdit.setText(self._initial)

    @property
    def payload(self) -> dict[str, Any]:
        return {"path": Path(self.pathEdit.text())}


class PreBlockNumCard(ParseSettingCard):
    def initCustomWidget(self) -> None:
        self.slider = Slider(Qt.Orientation.Horizontal, self)
        self.valueLabel = BodyLabel(self)

        self._initWidget()
        self._initLayout()
        self._bind()

    def _initWidget(self) -> None:
        self.slider.setMinimumWidth(268)
        self.slider.setSingleStep(1)
        self.slider.setRange(*cfg.preBlockNum.range)
        self.slider.setValue(cfg.preBlockNum.value)
        self.valueLabel.setNum(cfg.preBlockNum.value)

    def _initLayout(self) -> None:
        self.hBoxLayout.addWidget(self.valueLabel)
        self.hBoxLayout.addSpacing(6)
        self.hBoxLayout.addWidget(self.slider)
        self.hBoxLayout.addSpacing(16)

    def _bind(self) -> None:
        self.slider.valueChanged.connect(self._onValueChanged)

    def _onValueChanged(self, value: int) -> None:
        self.valueLabel.setNum(value)
        self.valueLabel.adjustSize()
        self.payloadChanged.emit()

    @property
    def payload(self) -> dict[str, Any]:
        return {"preBlockNum": self.slider.value()}


class _StandaloneWrapper(FramelessDialog):
    def __init__(self, dialog: "AddTaskDialog") -> None:
        super().__init__()
        self._dialog = dialog

        self.contentLayout = QVBoxLayout(self)

        self._initWidget()
        self._initLayout()

    def _initWidget(self) -> None:
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


class AddTaskDialog(MessageBoxBase):
    taskConfirmed = Signal(object)

    instance: Self = None

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        # instant widget
        self.titleLabel = SubtitleLabel(self.tr("添加任务"), self)
        self.urlEdit = AutoSizingEdit(self)
        self.parseProgressBar = IndeterminateProgressBar(self)
        self.parseResultGroup = ParseResultHeaderCardWidget(self)
        self.settingGroup = ParseSettingHeaderCardWidget(self)
        self.selectFolderCard = SelectFolderCard(
            FluentIcon.DOWNLOAD,
            self.tr("选择下载路径"),
            self,
        )
        self.preBlockNumCard = PreBlockNumCard(
            FluentIcon.CLOUD,
            self.tr("预分配线程数"),
            self,
        )
        self.importButton = PushButton(FluentIcon.FOLDER_ADD, self.tr("导入文件"), self)

        self.headerLayout = QHBoxLayout()

        self._timer = QTimer(self, singleShot=True)
        self._parseSession = AddTaskParseSession(parent=self)
        self._standaloneWrapper = _StandaloneWrapper(self)
        self._resultCards: dict[str, ResultCard] = {}

        self._initWidget()
        self._initLayout()
        self._parseSession.setPayload(self._settingsPayload())
        self._bind()

    def _initWidget(self) -> None:
        self.setObjectName("AddTaskDialog")
        self.widget.setFixedWidth(700)

        self.urlEdit.setPlaceholderText(
            self.tr("添加多个下载链接时，请确保每行只有一个下载链接")
        )
        self.urlEdit.setWordWrapMode(QTextOption.WrapMode.NoWrap)
        self.parseProgressBar.hide()

        self.settingGroup.addCard(self.selectFolderCard)
        self.settingGroup.addCard(self.preBlockNumCard)
        for card in featureService.dialogCards(self.settingGroup):
            self.settingGroup.addCard(card)

        self._fileTypes = featureService.fileTypes()
        self.importButton.setVisible(bool(self._fileTypes))

    def _initLayout(self) -> None:
        self.headerLayout.addWidget(self.titleLabel)
        self.headerLayout.addStretch(1)
        self.headerLayout.addWidget(self.importButton)
        self.viewLayout.addLayout(self.headerLayout)
        self.viewLayout.addWidget(self.urlEdit)
        self.viewLayout.addWidget(self.parseProgressBar)
        self.viewLayout.addWidget(self.parseResultGroup)
        self.viewLayout.addWidget(self.settingGroup)

    def _bind(self) -> None:
        self._timer.timeout.connect(
            lambda: self._parseSession.updateUrls(self._urls())
        )
        self.urlEdit.textChanged.connect(self._restartParseTimer)

        self._parseSession.parsingBusyChanged.connect(self.parseProgressBar.setVisible)
        self._parseSession.parseSucceeded.connect(self._onParseSucceeded)
        self._parseSession.parseFailed.connect(self._onParseError)
        self._parseSession.lineRemoved.connect(self._onLineRemoved)
        self._parseSession.linesReordered.connect(self._onLinesReordered)
        self._parseSession.cleared.connect(self._onSessionCleared)
        self._parseSession.taskConfirmed.connect(self.taskConfirmed.emit)

        self.importButton.clicked.connect(self._onImportClicked)

        for card in self.settingGroup.cards:
            card.payloadChanged.connect(
                lambda: self._parseSession.setPayload(self._settingsPayload())
            )

    def _onParseSucceeded(self, url: str, task: Task) -> None:
        card = featureService.resultCard(task, self.parseResultGroup)
        card.categoryPicked.connect(
            lambda categoryId: self._parseSession.setUrlCategoryOverride(url, categoryId)
        )
        card.editRequested.connect(
            lambda: self._onResultCardEditRequested(url)
        )
        self.parseResultGroup.scrollLayout.addWidget(card, alignment=Qt.AlignmentFlag.AlignTop)
        self._resultCards[url] = card

    def _onLineRemoved(self, url: str) -> None:
        card = self._resultCards.pop(url, None)
        if card is None:
            return
        self.parseResultGroup.scrollLayout.removeWidget(card)
        card.deleteLater()
        self.parseResultGroup.updateGeometry()

    def _onLinesReordered(self) -> None:
        for i, url in enumerate(self._parseSession.urls()):
            card = self._resultCards.get(url)
            if card is None:
                continue
            if self.parseResultGroup.scrollLayout.indexOf(card) != i:
                self.parseResultGroup.scrollLayout.insertWidget(
                    i, card, alignment=Qt.AlignmentFlag.AlignTop,
                )
        self.parseResultGroup.updateGeometry()

    def _onSessionCleared(self) -> None:
        self._resultCards.clear()
        self.parseResultGroup.clearResults()

    def _onResultCardEditRequested(self, url: str) -> None:
        from app.view.components.edit_task_dialog import EditTaskDialog

        task = self._parseSession.taskByUrl(url)
        if task is None:
            return

        dialog = EditTaskDialog(task, context="result", parent=self.window())
        dialog.urlReplaced.connect(self._onUrlReplaced)
        dialog.exec()
        dialog.deleteLater()

    def _onUrlReplaced(self, oldUrl: str, newUrl: str) -> None:
        self._replaceUrlInTextarea(oldUrl, newUrl)
        self._parseSession.replaceUrl(oldUrl, newUrl)
        # setPlainText 会触发 textChanged → timer; session 这边已经在重 parse 了, 关掉避免跑两遍
        self._timer.stop()

    def _replaceUrlInTextarea(self, oldUrl: str, newUrl: str) -> None:
        lines = self.urlEdit.toPlainText().splitlines()
        for i, line in enumerate(lines):
            if line.strip() == oldUrl:
                lines[i] = newUrl
                break
        self.urlEdit.setPlainText("\n".join(lines))

    def _restartParseTimer(self) -> None:
        self._timer.stop()
        self._timer.start(1000)

    def _urls(self) -> list[str]:
        text = self.urlEdit.toPlainText()
        if not text:
            return []
        return [line.strip() for line in text.splitlines() if line.strip()]

    def _onImportClicked(self) -> None:
        globs = [f"*{ext}" for fileType in self._fileTypes for ext in fileType.extensions]
        nameFilters = [self.tr("所有可导入文件 ({0})").format(" ".join(globs))]
        nameFilters += [
            "{0} ({1})".format(fileType.displayName, " ".join(f"*{ext}" for ext in fileType.extensions))
            for fileType in self._fileTypes
        ]

        paths, _ = QFileDialog.getOpenFileNames(self, self.tr("导入文件"), "", ";;".join(nameFilters))
        if not paths:
            return

        # 裸路径会被 featureService._toUrl 当成 http:// 处理而失效, 必须转成 file:// URI 才能命中本地文件解析
        self.addUrls([Path(path).as_uri() for path in paths])

    def addUrls(self, urls: list[str]) -> None:
        if not urls:
            return

        existingUrls = set(self._urls())
        urlsToAdd: list[str] = []

        for url in urls:
            normalizedUrl = url.strip()
            if not normalizedUrl or normalizedUrl in existingUrls:
                continue
            existingUrls.add(normalizedUrl)
            urlsToAdd.append(normalizedUrl)

        if not urlsToAdd:
            return

        self.urlEdit.appendPlainText("\n".join(urlsToAdd))
        self._parseSession.updateUrls(self._urls())
        self._timer.stop()

    def addParsedTasks(self, tasks: list[Task]) -> None:
        if not tasks:
            return

        newUrls = self._parseSession.addParsedTasks(tasks)
        if newUrls:
            self.urlEdit.appendPlainText("\n".join(newUrls))
        self._timer.stop()

    def _settingsPayload(self) -> dict[str, Any]:
        # 故意只回 cards 里的字段, 不混 defaultHeaders/getProxies — 否则浏览器插件已 parse
        # 出来带自定义 headers 的 task, 一进 setPayload → applySettings 就被默认值覆盖了
        return dict(self.settingGroup.payload)

    def _onParseError(self, url: str, error: str) -> None:
        displayUrl = url if len(url) <= 48 else f"{url[:45]}..."
        content = self.tr("{0}\n{1}").format(displayUrl, error)

        InfoBar.error(
            self.tr("链接解析失败"),
            content,
            duration=-1,
            position=InfoBarPosition.BOTTOM_RIGHT,
            parent=self._standaloneWrapper if self.isStandaloneMode else self,
        )

    @property
    def isStandaloneMode(self) -> bool:
        return self.widget.parentWidget() is self._standaloneWrapper

    def _toStandalone(self) -> None:
        self._hBoxLayout.removeWidget(self.widget)
        self._standaloneWrapper.setContent(self.widget)
        self.widget.setStyleSheet("#centerWidget { border: none; border-radius: 0; }")
        self.widget.show()
        self.titleLabel.hide()

    def _toMask(self) -> None:
        self._standaloneWrapper.hide()
        self._standaloneWrapper.takeContent(self.widget)
        self.widget.setStyleSheet("")
        self._hBoxLayout.addWidget(self.widget, 1, Qt.AlignmentFlag.AlignCenter)
        self.widget.show()
        self.titleLabel.show()

    def showStandalone(self) -> None:
        if self.isStandaloneMode and self._standaloneWrapper.isVisible():
            bringWindowToTop(self._standaloneWrapper)
            return

        if self.isVisible() and not self.isStandaloneMode:
            self.setGraphicsEffect(None)
            self.widget.setGraphicsEffect(None)
            QDialog.done(self, QDialog.DialogCode.Rejected)

        if not self.isStandaloneMode:
            self._toStandalone()

        bringWindowToTop(self._standaloneWrapper)

    def showMask(self) -> int:
        if self.isStandaloneMode:
            self._toMask()

        parent = self.parentWidget()
        if parent is not None:
            self.setGeometry(0, 0, parent.width(), parent.height())
            self.windowMask.resize(self.size())

        self.setShadowEffect(60, (0, 10), QColor(0, 0, 0, 50))
        self.setMaskColor(QColor(0, 0, 0, 76))
        return self.exec()

    def done(self, code) -> None:
        confirmedTasks: list[Task] = []
        if code == QDialog.DialogCode.Rejected:
            self._parseSession.clear()
            self.urlEdit.clear()
            self._timer.stop()
            self.selectFolderCard.reset()
        elif code == QDialog.DialogCode.Accepted:
            confirmedTasks = self._parseSession.accept()
            self.urlEdit.clear()
            self._timer.stop()
            self.selectFolderCard.reset()

        for task in confirmedTasks:
            self.taskConfirmed.emit(task)

        if self.isStandaloneMode:
            self._toMask()
            return

        super().done(code)

    def validate(self) -> bool:
        self._timer.stop()
        self._parseSession.updateUrls(self._urls())
        return self._parseSession.canAccept()

    @classmethod
    def initialize(cls, mainWindow) -> Self:
        if cls.instance is None:
            cls.instance = cls(mainWindow)
            cls.instance.taskConfirmed.connect(mainWindow.addTask)
        return cls.instance

    def eventFilter(self, obj, event: QEvent):
        if obj is not self.windowMask:
            return super().eventFilter(obj, event)

        if (
            event.type() == QEvent.Type.MouseButtonPress
            and event.button() == Qt.MouseButton.LeftButton
        ):
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
