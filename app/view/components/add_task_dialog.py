# pyright: reportImportCycles=false, reportMissingTypeStubs=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportAny=false, reportExplicitAny=false, reportAttributeAccessIssue=false, reportArgumentType=false, reportAssignmentType=false, reportUnannotatedClassAttribute=false, reportUninitializedInstanceVariable=false, reportInconsistentConstructor=false, reportUnusedCallResult=false, reportImplicitOverride=false, reportIncompatibleMethodOverride=false, reportUnnecessaryComparison=false

from pathlib import Path
from typing import Any, Self

from PySide6.QtCore import QEvent, QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QTextOption
from PySide6.QtWidgets import QDialog, QFileDialog, QVBoxLayout
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
    Slider,
    SubtitleLabel,
)
from qfluentwidgets.common.style_sheet import FluentStyleSheet
from qframelesswindow import FramelessDialog

from app.feature_pack.api import Task
from app.feature_pack.internal import AddTaskDialogSession
from app.feature_pack.internal import AddTaskInputOverride
from app.feature_pack.internal import FeatureServiceTaskRunner
from app.services.core_service import coreService
from app.services.feature_service import featureService
from app.supports.config import DEFAULT_HEADERS, cfg
from app.supports.utils import bringWindowToTop, getProxies
from app.view.components.card_widgets import (
    AddTaskSettingsHeaderCardWidget,
    TaskPreviewHeaderCardWidget,
)
from app.view.components.cards import AddTaskSettingCard
from app.view.components.editors import AutoSizingEdit


class DownloadFolderCard(AddTaskSettingCard):
    def initCustomWidget(self) -> None:
        self.pathEdit = LineEdit(self)
        self.selectFolderAction = Action(FluentIcon.FOLDER, self.tr("选择文件夹"), self)

        self.pathEdit.addAction(self.selectFolderAction)

        self._initWidget()
        self._initLayout()
        self._bind()

    def _initWidget(self) -> None:
        self.pathEdit.setReadOnly(True)
        self.pathEdit.setText(cfg.downloadFolder.value)

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
        self.inputChanged.emit()

    def _currentBrowsePath(self) -> Path:
        path = Path(self.pathEdit.text())
        if path.exists():
            return path.absolute()
        return path.parent

    @property
    def inputOptions(self) -> dict[str, Any]:
        return {"path": Path(self.pathEdit.text())}


class ParallelChunksCard(AddTaskSettingCard):
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
        self.inputChanged.emit()

    @property
    def inputOptions(self) -> dict[str, Any]:
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
        self.parseResultGroup = TaskPreviewHeaderCardWidget(self)
        self.settingGroup = AddTaskSettingsHeaderCardWidget(self)
        self.selectFolderCard = DownloadFolderCard(
            FluentIcon.DOWNLOAD,
            self.tr("选择下载路径"),
            self,
        )
        self.preBlockNumCard = ParallelChunksCard(
            FluentIcon.CLOUD,
            self.tr("预分配线程数"),
            self,
        )

        self._timer = QTimer(self, singleShot=True)
        self._parseSession = AddTaskDialogSession(
            featureService=featureService,
            taskRunner=FeatureServiceTaskRunner(
                featureService=featureService,
                runTaskCoroutine=coreService.runCoroutine,
                cancelTaskRequest=coreService.removeCallback,
            ),
            resultCardParent=self.parseResultGroup,
            parent=self,
        )
        self._standaloneWrapper = _StandaloneWrapper(self)

        # init
        self._initWidget()
        self._initLayout()
        self._syncParseSessionConfig()

        # bind
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
    def _initLayout(self) -> None:
        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addWidget(self.urlEdit)
        self.viewLayout.addWidget(self.parseProgressBar)
        self.viewLayout.addWidget(self.parseResultGroup)
        self.viewLayout.addWidget(self.settingGroup)

    def _bind(self) -> None:
        self._timer.timeout.connect(
            lambda: self._parseSession.updateSources(self._readUrlsFromEditor())
        )
        self.urlEdit.textChanged.connect(self._restartParseTimer)
        self._parseSession.parsingBusyChanged.connect(self.parseProgressBar.setVisible)
        self._parseSession.parseErrorOccurred.connect(self._showParseError)
        self._parseSession.taskConfirmed.connect(self.taskConfirmed.emit)
        for card in self.settingGroup.cards:
            card.inputChanged.connect(
                self._syncParseSessionConfig
            )

    def _restartParseTimer(self) -> None:
        self._timer.stop()
        self._timer.start(1000)

    def _readUrlsFromEditor(self) -> list[str]:
        text = self.urlEdit.toPlainText()
        if not text:
            return []
        return [line.strip() for line in text.splitlines() if line.strip()]

    def addUrls(self, urls: list[str]) -> None:
        if not urls:
            return

        existingUrls = set(self._readUrlsFromEditor())
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
        self._parseSession.updateSources(self._readUrlsFromEditor())
        self._timer.stop()

    def addUrlWithInputOverride(
        self,
        url: str,
        inputOverride: dict[str, Any],
    ) -> None:
        self._parseSession.setSourceOverride(
            url,
            self._buildInputOverride(inputOverride),
        )
        self.addUrls([url])

    def addParsedTasks(self, tasks: list[Task]) -> None:
        if not tasks:
            return

        newUrls = self._parseSession.addParsedTasks(tasks)
        if newUrls:
            self.urlEdit.appendPlainText("\n".join(newUrls))
        self._timer.stop()

    def buildCurrentInputOptions(self) -> dict[str, Any]:
        inputOptions = {
            "headers": DEFAULT_HEADERS.copy(),
            "proxies": getProxies(),
        }
        inputOptions.update(self.settingGroup.inputOptions)
        return inputOptions

    def _syncParseSessionConfig(self) -> None:
        inputOptions = self.buildCurrentInputOptions()
        rawFolder = inputOptions.get("path")
        rawHeaders = inputOptions.get("headers")
        rawProxies = inputOptions.get("proxies")
        rawChunks = inputOptions.get("preBlockNum")

        self._parseSession.setBaseConfig(
            folder=Path(rawFolder) if isinstance(rawFolder, (str, Path)) else Path(cfg.downloadFolder.value),
            headers=rawHeaders if isinstance(rawHeaders, dict) else DEFAULT_HEADERS,
            proxies=rawProxies if isinstance(rawProxies, dict) else getProxies(),
            chunks=rawChunks if isinstance(rawChunks, int) else cfg.preBlockNum.value,
        )

    def _buildInputOverride(
        self,
        inputOverride: dict[str, Any],
    ) -> AddTaskInputOverride:
        rawFolder = inputOverride.get("path")
        rawHeaders = inputOverride.get("headers")
        rawProxies = inputOverride.get("proxies")
        rawChunks = inputOverride.get("preBlockNum")
        rawSize = inputOverride.get("size")
        rawName = inputOverride.get("filename")
        hints = {
            key: value
            for key, value in inputOverride.items()
            if key not in {"path", "headers", "proxies", "preBlockNum", "size", "filename", "url"}
        }

        return AddTaskInputOverride(
            folder=Path(rawFolder) if isinstance(rawFolder, (str, Path)) else None,
            name=rawName if isinstance(rawName, str) else None,
            headers=rawHeaders if isinstance(rawHeaders, dict) else None,
            proxies=rawProxies if isinstance(rawProxies, dict) else None,
            chunks=rawChunks if isinstance(rawChunks, int) else None,
            size=rawSize if isinstance(rawSize, int) else None,
            hints=(hints,) if hints else (),
        )

    def _showParseError(self, url: str, error: str) -> None:
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

    def showStandalone(self) -> None:
        if self.isStandaloneMode and self._standaloneWrapper.isVisible():
            bringWindowToTop(self._standaloneWrapper)
            return

        if self.isVisible() and not self.isStandaloneMode:
            self.setGraphicsEffect(None)
            self.widget.setGraphicsEffect(None)
            QDialog.done(self, QDialog.DialogCode.Rejected)

        if not self.isStandaloneMode:
            self._hBoxLayout.removeWidget(self.widget)
            self._standaloneWrapper.setContent(self.widget)
            self.widget.setStyleSheet("#centerWidget { border: none; border-radius: 0; }")
            self.widget.show()
            self.titleLabel.hide()

        bringWindowToTop(self._standaloneWrapper)

    def showMask(self) -> int:
        if self.isStandaloneMode:
            self._standaloneWrapper.hide()
            self._standaloneWrapper.takeContent(self.widget)
            self.widget.setStyleSheet("")
            self._hBoxLayout.addWidget(self.widget, 1, Qt.AlignmentFlag.AlignCenter)
            self.widget.show()
            self.titleLabel.show()

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
        elif code == QDialog.DialogCode.Accepted:
            confirmedTasks = self._parseSession.accept()
            self.urlEdit.clear()
            self._timer.stop()

        for task in confirmedTasks:
            self.taskConfirmed.emit(task)

        if self.isStandaloneMode:
            self._standaloneWrapper.hide()
            self._standaloneWrapper.takeContent(self.widget)
            self.widget.setStyleSheet("")
            self._hBoxLayout.addWidget(self.widget, 1, Qt.AlignmentFlag.AlignCenter)
            self.widget.show()
            self.titleLabel.show()
            return

        super().done(code)

    def validate(self) -> bool:
        self._timer.stop()
        self._parseSession.updateSources(self._readUrlsFromEditor())
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
