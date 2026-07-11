from __future__ import annotations

from re import compile
from urllib.parse import urlsplit
import weakref

from PySide6.QtCore import Qt, QEvent, QRectF, Signal
from PySide6.QtGui import QPainter, QPainterPath
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QButtonGroup, QHBoxLayout, QLineEdit,
    QSpacerItem, QSizePolicy, QFileDialog,
)
from qfluentwidgets import (
    SettingCard, PushSettingCard, RangeConfigItem, SpinBox, DoubleSpinBox,
    ConfigItem, FluentIcon, BodyLabel, CaptionLabel,
    RadioButton, ComboBox, LineEdit, ToolButton, ToolTipFilter,
    PrimaryPushButton, InfoBar, InfoBarPosition,
    IconWidget,
)

from app.view.components.setting_card_group import CollapsibleSettingCard

from app.config.cfg import cfg, proxy, BASE_HEADERS
from app.view.components.banners import WarningBanner

HOST_PATTERN = compile(
    r"^(?:(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)"
    r"|(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,6})$"
)
PORT_PATTERN = compile(r"^\d{1,5}$")


class ErrorVisibleLineEdit(LineEdit):

    def paintEvent(self, e):
        QLineEdit.paintEvent(self, e)
        if not self.hasFocus() and not self.isError():
            return
        painter = QPainter(self)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        m = self.contentsMargins()
        path = QPainterPath()
        w, h = self.width() - m.left() - m.right(), self.height()
        path.addRoundedRect(QRectF(m.left(), h - 10, w, 10), 5, 5)
        rectPath = QPainterPath()
        rectPath.addRect(m.left(), h - 10, w, 8)
        path = path.subtracted(rectPath)
        painter.fillPath(path, self.focusedBorderColor())


class SpinBoxSettingCard(SettingCard):

    def __init__(self, icon, title: str, content: str = "",
                 suffix: str = "", configItem: RangeConfigItem = None,
                 parent=None, singleStep: int = 50, division: float = 1):
        super().__init__(icon, title, content, parent)
        self._configItem = configItem
        self._division = division

        self.spinBox = SpinBox(self)
        self.spinBox.setSingleStep(singleStep)
        self.spinBox.setMinimumWidth(180)
        self.spinBox.setSuffix(suffix)
        self.spinBox.installEventFilter(self)
        r = configItem.range
        self.spinBox.setRange(int(r[0] * division), int(r[1] * division))
        self.spinBox.setValue(int(configItem.value * division))

        self.hBoxLayout.addWidget(self.spinBox)
        self.hBoxLayout.addSpacing(24)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Wheel:
            return True
        return super().eventFilter(watched, event)

    def leaveEvent(self, event):
        cfg.set(self._configItem, int(self.spinBox.value() / self._division))


class PercentSpinBoxSettingCard(SettingCard):

    def __init__(self, icon, title: str, content: str = "",
                 configItem: RangeConfigItem = None, parent=None,
                 singleStep: float = 25):
        super().__init__(icon, title, content, parent)
        self._configItem = configItem

        self.spinBox = DoubleSpinBox(self)
        self.spinBox.setDecimals(0)
        self.spinBox.setSingleStep(singleStep)
        self.spinBox.setMinimumWidth(180)
        self.spinBox.setSuffix(" %")
        self.spinBox.installEventFilter(self)
        r = configItem.range
        self.spinBox.setRange(r[0] * 100, r[1] * 100)
        self.spinBox.setValue(configItem.value * 100)

        self.hBoxLayout.addWidget(self.spinBox)
        self.hBoxLayout.addSpacing(24)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Wheel:
            return True
        return super().eventFilter(watched, event)

    def leaveEvent(self, event):
        cfg.set(self._configItem, self.spinBox.value() / 100)


class LineEditSettingCard(SettingCard):

    def __init__(self, icon, title: str, content: str = "",
                 configItem: ConfigItem = None, parent=None,
                 placeholder: str = "", isPassword: bool = False):
        super().__init__(icon, title, content, parent)
        self._configItem = configItem

        from qfluentwidgets import PasswordLineEdit
        self.lineEdit = PasswordLineEdit(self) if isPassword else LineEdit(self)
        self.lineEdit.setMinimumWidth(180)
        self.lineEdit.setClearButtonEnabled(True)
        self.lineEdit.setPlaceholderText(placeholder)
        if configItem:
            self.lineEdit.setText(configItem.value)

        self.hBoxLayout.addWidget(self.lineEdit)
        self.hBoxLayout.addSpacing(16)

        self.lineEdit.editingFinished.connect(
            lambda: cfg.set(self._configItem, self.lineEdit.text())
        )


class ProxySettingCard(CollapsibleSettingCard):

    def __init__(self, configItem: ConfigItem, parent=None):
        super().__init__(FluentIcon.GLOBE, self.tr("代理"),
                         self.tr("设置下载时希望使用的代理"), parent=parent)
        self._configItem = configItem

        self.choiceLabel = BodyLabel(self)
        self.radioWidget = QWidget(self.view)
        self.radioLayout = QVBoxLayout(self.radioWidget)

        self.buttonGroup = QButtonGroup(self)
        self.offRadio = RadioButton(self.tr("不使用代理"), self.radioWidget)
        self.autoRadio = RadioButton(self.tr("自动检测系统代理"), self.radioWidget)
        self.customRadio = RadioButton(self.tr("使用自定义代理"), self.radioWidget)

        self.customWidget = QWidget(self.view)
        self.customLayout = QHBoxLayout(self.customWidget)
        self.protocolCombo = ComboBox(self.customWidget)
        self.protocolCombo.addItems(["socks4", "socks5", "socks5h", "http", "https"])
        self.ipEdit = ErrorVisibleLineEdit(self.customWidget)
        self.ipEdit.setPlaceholderText(self.tr("代理 IP 地址"))
        self.portEdit = ErrorVisibleLineEdit(self.customWidget)
        self.portEdit.setPlaceholderText(self.tr("端口"))

        self.credWidget = QWidget(self.view)
        self.credLayout = QHBoxLayout(self.credWidget)
        self.userEdit = LineEdit(self.credWidget)
        self.userEdit.setPlaceholderText(self.tr("用户名（可选）"))
        self.passEdit = LineEdit(self.credWidget)
        self.passEdit.setPlaceholderText(self.tr("密码（可选）"))
        self.passEdit.setEchoMode(LineEdit.EchoMode.Password)

        self.compatBanner = WarningBanner(self.view)
        self.compatBanner.setContentsMargins(48, 0, 44, 10)
        bannerLayout = QHBoxLayout(self.compatBanner)
        bannerLayout.setContentsMargins(10, 8, 10, 8)
        bannerLayout.setSpacing(8)
        bannerIcon = IconWidget(FluentIcon.INFO, self.compatBanner)
        bannerIcon.setFixedSize(16, 16)
        bannerLayout.addWidget(bannerIcon)
        self._compatLabel = CaptionLabel("", self.compatBanner)
        self._compatLabel.setWordWrap(True)
        bannerLayout.addWidget(self._compatLabel, 1)

        self._initLayout()
        self._loadProxy()

        self.buttonGroup.buttonClicked.connect(self._onRadioClicked)
        self.protocolCombo.activated.connect(self._onProxyFieldChanged)
        self.ipEdit.textEdited.connect(self._onProxyFieldChanged)
        self.portEdit.textEdited.connect(self._onProxyFieldChanged)
        self.userEdit.textEdited.connect(self._onProxyFieldChanged)
        self.passEdit.textEdited.connect(self._onProxyFieldChanged)
        self._refreshCompatBanner()

    def _initLayout(self) -> None:
        self.addWidget(self.choiceLabel)

        self.radioLayout.setSpacing(19)
        self.radioLayout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.radioLayout.setContentsMargins(48, 18, 0, 18)
        for btn in (self.offRadio, self.autoRadio, self.customRadio):
            self.buttonGroup.addButton(btn)
            self.radioLayout.addWidget(btn)

        self.customLayout.setContentsMargins(48, 5, 44, 10)
        self.customLayout.addWidget(BodyLabel(self.tr("编辑代理服务器: "), self.customWidget))
        self.customLayout.addSpacerItem(QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))
        self.customLayout.addWidget(self.protocolCombo)
        self.customLayout.addWidget(BodyLabel("://", self.customWidget))
        self.customLayout.addWidget(self.ipEdit)
        self.customLayout.addWidget(BodyLabel(":", self.customWidget))
        self.customLayout.addWidget(self.portEdit)

        self.credLayout.setContentsMargins(48, 5, 44, 18)
        self.credLayout.addWidget(BodyLabel(self.tr("认证信息: "), self.credWidget))
        self.credLayout.addSpacerItem(QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))
        self.credLayout.addWidget(self.userEdit)
        self.credLayout.addWidget(BodyLabel(" : ", self.credWidget))
        self.credLayout.addWidget(self.passEdit)

        self.viewLayout.setSpacing(0)
        self.viewLayout.setContentsMargins(0, 0, 0, 0)
        self.addGroupWidget(self.compatBanner)
        self.addGroupWidget(self.radioWidget)
        self.addGroupWidget(self.customWidget)
        self.addGroupWidget(self.credWidget)

    def _loadProxy(self) -> None:
        value = self._configItem.value
        if value == "Auto":
            self.autoRadio.setChecked(True)
            self._onRadioClicked(self.autoRadio)
        elif value == "Off":
            self.offRadio.setChecked(True)
            self._onRadioClicked(self.offRadio)
        else:
            self.customRadio.setChecked(True)
            self._showProxyUrl(value)
            self._onRadioClicked(self.customRadio)

    def setExpand(self, isExpand):
        super().setExpand(isExpand)
        if not isExpand:
            self._loadProxy()

    def _onRadioClicked(self, button) -> None:
        self.choiceLabel.setText(button.text())
        isCustom = button is self.customRadio
        self.customWidget.setEnabled(isCustom)
        self.credWidget.setEnabled(isCustom)

        if button is self.autoRadio:
            cfg.set(self._configItem, "Auto")
            self._showProxyUrl(proxy())
        elif button is self.offRadio:
            cfg.set(self._configItem, "Off")
        elif button is self.customRadio:
            if self.ipEdit.text() == self.tr("未检测到代理"):
                self.ipEdit.clear()
            self._onProxyFieldChanged()
        self._refreshCompatBanner()

    def _showProxyUrl(self, url: str | None) -> None:
        if not url:
            self.protocolCombo.setCurrentText("")
            self.ipEdit.setText(self.tr("未检测到代理"))
            self.portEdit.setText("")
            self.userEdit.setText("")
            self.passEdit.setText("")
            return
        parsed = urlsplit(url)
        self.protocolCombo.setCurrentText(parsed.scheme)
        self.ipEdit.setText(parsed.hostname or "")
        self.portEdit.setText(str(parsed.port or ""))
        self.userEdit.setText(parsed.username or "")
        self.passEdit.setText(parsed.password or "")

    def _refreshCompatBanner(self) -> None:
        if self.offRadio.isChecked():
            scheme = ""
        elif self.autoRadio.isChecked():
            url = proxy()
            scheme = urlsplit(url).scheme.lower() if url else ""
        else:
            scheme = self.protocolCombo.currentText().lower()

        if scheme == "socks5h":
            scheme = "socks5"
        if scheme:
            from app.services.feature_service import featureService
            incompatible = [
                p.packId.upper() for p in featureService.packs
                if p.proxySchemes is not None and scheme not in p.proxySchemes
            ]
            if incompatible:
                names = "、".join(incompatible)
                self._compatLabel.setText(
                    self.tr("{0} 不支持当前代理协议，建议使用 SOCKS5 以兼容全部下载方式").format(names)
                )
                self.compatBanner.show()
            else:
                self.compatBanner.hide()
        else:
            self.compatBanner.hide()

    def _buildProxyUrl(self) -> str:
        protocol = self.protocolCombo.currentText()
        ip = self.ipEdit.text()
        port = self.portEdit.text()
        user = self.userEdit.text()
        password = self.passEdit.text()
        cred = f"{user}:{password}@" if user or password else ""
        return f"{protocol}://{cred}{ip}:{port}"

    def _onProxyFieldChanged(self) -> None:
        if not self.customRadio.isChecked():
            self.ipEdit.setError(False)
            self.portEdit.setError(False)
            return

        url = self._buildProxyUrl()
        if cfg.proxyServer.validator.validate(url):
            self.choiceLabel.setText(url)
            self.ipEdit.setError(False)
            self.portEdit.setError(False)
        else:
            self.choiceLabel.setText(self.customRadio.text())
            ip = self.ipEdit.text().strip()
            port = self.portEdit.text().strip()
            self.ipEdit.setError(bool(ip) and not HOST_PATTERN.match(ip))
            self.portEdit.setError(bool(port) and not PORT_PATTERN.match(port))
        self._refreshCompatBanner()

    def leaveEvent(self, event):
        if self.customRadio.isChecked():
            url = self._buildProxyUrl()
            if cfg.proxyServer.validator.validate(url):
                cfg.set(self._configItem, url)


class SelectFolderSettingCard(SettingCard):
    pathChanged = Signal(str)

    def __init__(self, configItem: ConfigItem, defaultPath: str,
                 title: str, parent=None):
        super().__init__(FluentIcon.FOLDER, title, configItem.value, parent)
        self._configItem = configItem
        self._defaultPath = defaultPath

        self.browseButton = ToolButton(FluentIcon.FOLDER, self)
        self.restoreButton = ToolButton(FluentIcon.CANCEL, self)
        self.browseButton.setToolTip(self.tr("浏览文件夹"))
        self.browseButton.installEventFilter(ToolTipFilter(self.browseButton))
        self.restoreButton.setToolTip(self.tr("恢复默认路径"))
        self.restoreButton.installEventFilter(ToolTipFilter(self.restoreButton))

        self.hBoxLayout.addWidget(self.browseButton, 0, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.addSpacing(8)
        self.hBoxLayout.addWidget(self.restoreButton, 0, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.addSpacing(16)

        self.browseButton.clicked.connect(self._onBrowseClicked)
        self.restoreButton.clicked.connect(lambda: self._setPath(self._defaultPath))

    def _onBrowseClicked(self) -> None:
        folder = QFileDialog.getExistingDirectory(self.window(), self.tr("选择文件夹"), self._configItem.value)
        if folder:
            self._setPath(folder)

    def _setPath(self, path: str) -> None:
        cfg.set(self._configItem, path)
        self.setContent(path)
        self.pathChanged.emit(path)


class ClientProfileSettingCard(SettingCard):

    def __init__(self, parent=None):
        from qfluentwidgets import DropDownPushButton
        from app.view.components.option_cards import toProfileLabel
        super().__init__(FluentIcon.ROBOT, self.tr("模拟身份"), self.tr("浏览器 TLS 指纹与 User-Agent"), parent)
        self.button = DropDownPushButton(toProfileLabel(cfg.clientProfile.value), self)
        self._initWidget()
        self._initLayout()
        self._bind()

    def _initWidget(self) -> None:
        from qfluentwidgets import Action, RoundMenu
        from app.client import profileFamilies, profileVersions
        from app.view.components.option_cards import PROFILE_FAMILY_LABELS, toProfileLabel

        self.button.setMinimumWidth(200)
        menu = RoundMenu(parent=self)

        for value, icon in (("auto", FluentIcon.ROBOT), ("raw", FluentIcon.CANCEL)):
            action = Action(icon, toProfileLabel(value), self)
            action.triggered.connect(lambda checked=False, v=value: self._onPick(v))
            menu.addAction(action)

        for family in profileFamilies():
            submenu = RoundMenu(PROFILE_FAMILY_LABELS.get(family, family), self)
            latest = Action(toProfileLabel(family), self)
            latest.triggered.connect(lambda checked=False, v=family: self._onPick(v))
            submenu.addAction(latest)
            submenu.addSeparator()
            for name in profileVersions(family):
                action = Action(toProfileLabel(name), self)
                action.triggered.connect(lambda checked=False, v=name: self._onPick(v))
                submenu.addAction(action)
            menu.addMenu(submenu)

        self.button.setMenu(menu)

    def _initLayout(self) -> None:
        self.hBoxLayout.addWidget(self.button, 0, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.addSpacing(16)

    def _bind(self) -> None:
        cfg.clientProfile.valueChanged.connect(self._onProfileChanged)

    def _onProfileChanged(self, value: str) -> None:
        from app.view.components.option_cards import toProfileLabel
        self.button.setText(toProfileLabel(value))

    def _onPick(self, value: str) -> None:
        cfg.set(cfg.clientProfile, value)


class DefaultHeadersSettingCard(PushSettingCard):
    def __init__(self, icon, title: str, content: str = "", parent=None):
        super().__init__(self.tr("编辑"), icon, title, content, parent)
        self.clicked.connect(self._onClicked)

    def _onClicked(self) -> None:
        from qfluentwidgets import MessageBoxBase, SubtitleLabel, TransparentToolButton
        from app.view.components.editors import HeadersEditor

        dialog = MessageBoxBase(self.window())
        dialog.widget.setMinimumWidth(500)

        titleRow = QHBoxLayout()
        titleRow.addWidget(SubtitleLabel(self.tr("编辑默认请求头"), dialog))
        titleRow.addStretch(1)
        resetButton = TransparentToolButton(FluentIcon.HISTORY, dialog)
        resetButton.setToolTip(self.tr("恢复默认"))
        resetButton.installEventFilter(ToolTipFilter(resetButton))
        titleRow.addWidget(resetButton)
        dialog.viewLayout.addLayout(titleRow)

        editor = HeadersEditor(dialog)
        editor.setHeaders(dict(cfg.defaultRequestHeaders.value))
        dialog.viewLayout.addWidget(editor)

        resetButton.clicked.connect(
            lambda: editor.setHeaders(dict(BASE_HEADERS))
        )

        if dialog.exec():
            headers = editor.headers()
            if headers:
                cfg.set(cfg.defaultRequestHeaders, headers)


class SelectFileCard(SettingCard):
    pathChanged = Signal(str)

    def __init__(self, icon, title: str, hint: str = "",
                 configItem: ConfigItem = None, parent=None):
        super().__init__(icon, title, configItem.value or hint if configItem else hint, parent)
        self._configItem = configItem
        self._hint = hint

        self.chooseFileButton = ToolButton(FluentIcon.FOLDER, self)
        self.clearButton = ToolButton(FluentIcon.CANCEL, self)
        self.chooseFileButton.setToolTip(self.tr("选择文件"))
        self.chooseFileButton.installEventFilter(ToolTipFilter(self.chooseFileButton))
        self.clearButton.setToolTip(self.tr("清除路径"))
        self.clearButton.installEventFilter(ToolTipFilter(self.clearButton))

        self.hBoxLayout.addWidget(self.chooseFileButton, 0, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.addSpacing(8)
        self.hBoxLayout.addWidget(self.clearButton, 0, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.addSpacing(16)

        self.chooseFileButton.clicked.connect(self._onChooseFile)
        self.clearButton.clicked.connect(lambda: self._setPath(""))

    def _onChooseFile(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self.window(), self.tr("选择文件"))
        if path:
            self._setPath(path)

    def _setPath(self, path: str) -> None:
        cfg.set(self._configItem, path)
        self.setContent(path or self._hint)
        self.pathChanged.emit(path)


class RuntimeCard(SettingCard):

    def __init__(self, runtime, parent=None):
        from app.models.pack import BinaryRuntime
        from app.services.runtime_status import runtimeStatusService

        self._runtime: BinaryRuntime = runtime
        super().__init__(FluentIcon.INFO, runtime.name, self.tr("正在检测运行时..."), parent)

        self.installButton = PrimaryPushButton(self.tr("一键安装"), self)
        self.refreshButton = ToolButton(FluentIcon.SYNC, self)

        self._initWidget()
        self._initLayout()
        self._bind()
        self.updateStatus(runtimeStatusService.status(runtime))

    def _initWidget(self) -> None:
        if not self._runtime.canInstall:
            self.installButton.hide()
        self.refreshButton.setToolTip(self.tr("刷新"))
        self.refreshButton.installEventFilter(ToolTipFilter(self.refreshButton))

    def _initLayout(self) -> None:
        self.hBoxLayout.addWidget(self.installButton, 0, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.addSpacing(8)
        self.hBoxLayout.addWidget(self.refreshButton, 0, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.addSpacing(16)

    def _bind(self) -> None:
        from app.services.runtime_status import runtimeStatusService

        runtimeStatusService.statusChanged.connect(self._onRuntimeStatusChanged)
        self.installButton.clicked.connect(self._onInstallClicked)
        self.refreshButton.clicked.connect(self._onRefreshClicked)

    def refreshStatus(self, force: bool = False) -> None:
        from app.services.runtime_status import runtimeStatusService

        runtimeStatusService.refresh(self._runtime, force=force)

    def updateStatus(self, status) -> None:
        self.refreshButton.setEnabled(not status.isBusy)
        if status.isBusy:
            self.setContent(self.tr("正在检测运行时..."))
        elif status.error:
            self.setContent(self.tr("检测运行时失败"))
        elif status.version and status.path:
            self.setContent(self.tr("版本: {0}\n路径: {1}").format(status.version, status.path))
        elif status.path:
            self.setContent(self.tr("路径: {0}").format(status.path))
        else:
            self.setContent(self.tr("未检测到可用的 {0}").format(status.name))

    def _onRefreshClicked(self, *_args) -> None:
        self.refreshStatus(force=True)

    def _onInstallFolderChanged(self, *_args) -> None:
        self.refreshStatus()

    def _onRuntimeStatusChanged(self, status) -> None:
        if status.runtimeId == self._runtime.runtimeId:
            self.updateStatus(status)

    def _onInstallClicked(self) -> None:
        from app.services.coroutine_runner import coroutineRunner

        self.installButton.setEnabled(False)
        cardRef = weakref.ref(self)

        def onCreated(task) -> None:
            from shiboken6 import isValid
            from app.services.task_service import taskService

            taskService.add(task)
            card = cardRef()
            if card is not None and isValid(card):
                card.installButton.setEnabled(True)
                InfoBar.success(
                    card.tr("安装任务已创建"),
                    card.tr("请前往任务页查看安装进度"),
                    duration=3000,
                    position=InfoBarPosition.TOP,
                    parent=card.window(),
                )

        def onFailed(error: str) -> None:
            from shiboken6 import isValid

            card = cardRef()
            if card is not None and isValid(card):
                card._onInstallTaskFailed(error)

        coroutineRunner.submit(self._runtime.installTask(), done=onCreated, failed=onFailed)

    def _onInstallTaskFailed(self, error: str) -> None:
        self.installButton.setEnabled(True)
        InfoBar.error(
            self.tr("安装失败"),
            error,
            duration=-1,
            position=InfoBarPosition.TOP,
            parent=self.window(),
        )
