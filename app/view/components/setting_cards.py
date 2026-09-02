from __future__ import annotations

from re import compile
from urllib.parse import urlsplit

from PySide6.QtCore import Qt, QEvent, QRectF, Signal
from PySide6.QtGui import QPainter, QPainterPath
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QButtonGroup, QHBoxLayout, QLineEdit,
    QSpacerItem, QSizePolicy, QFileDialog,
)
from qfluentwidgets import (
    SettingCard, RangeConfigItem, SpinBox, DoubleSpinBox,
    ConfigItem, FluentIcon, BodyLabel, CaptionLabel,
    RadioButton, ComboBox, LineEdit, ToolButton, ToolTipFilter,
    PrimaryPushButton, InfoBar, InfoBarPosition,
    IconWidget,
)

from app.view.components.setting_card_group import CollapsibleSettingCard

from app.config.cfg import cfg, proxy, currentHeaders, currentHeadersPresetIndex
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

    def __init__(self, configItem: ConfigItem, featureService=None, parent=None):
        super().__init__(FluentIcon.GLOBE, self.tr("代理"),
                         self.tr("设置下载时希望使用的代理"), parent=parent)
        self._configItem = configItem
        self._featureService = featureService

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
            incompatible = [
                p.packId.upper() for p in self._featureService.packs
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


class PresetRowWidget(QWidget):
    editRequested = Signal(int)
    removeRequested = Signal(int)
    toggled = Signal(int, bool)

    def __init__(self, index: int, preset: dict, parent=None):
        from qfluentwidgets import IconWidget, PrimaryToolButton, SwitchButton, StrongBodyLabel, ToolButton
        super().__init__(parent)
        self._index = index
        self._preset = preset

        self.iconWidget = IconWidget(FluentIcon.VPN, self)
        self.nameLabel = StrongBodyLabel(preset.get("name", ""), self)
        self.descLayout = QHBoxLayout()
        self.switchButton = SwitchButton(self)
        self.editButton = PrimaryToolButton(FluentIcon.EDIT, self)
        self.removeButton = ToolButton(FluentIcon.DELETE, self)

        self._initWidget(preset)
        self._initLayout()
        self._bind()

    def _initWidget(self, preset: dict) -> None:
        self.iconWidget.setFixedSize(16, 16)
        self.switchButton.setChecked(preset.get("isEnabled", True))
        self.switchButton.setOnText("")
        self.switchButton.setOffText("")
        self.editButton.setToolTip(self.tr("编辑"))
        self.editButton.installEventFilter(ToolTipFilter(self.editButton))
        self.removeButton.setToolTip(self.tr("删除"))
        self.removeButton.installEventFilter(ToolTipFilter(self.removeButton))
        self._refreshOpacity(preset.get("isEnabled", True))

    def _initLayout(self) -> None:
        from app.view.components.labels import IconBodyLabel
        from app.view.components.option_cards import toProfileLabel

        self.descLayout.setContentsMargins(0, 0, 0, 0)
        self.descLayout.setSpacing(0)

        hosts = self._preset.get("hosts", [])
        if hosts:
            self.descLayout.addWidget(
                IconBodyLabel(", ".join(hosts[:3]), FluentIcon.GLOBE, self, size=12))
            self.descLayout.addSpacing(8)
        profile = self._preset.get("clientProfile", "")
        if profile:
            self.descLayout.addWidget(
                IconBodyLabel(toProfileLabel(profile), FluentIcon.FINGERPRINT, self, size=12))
            self.descLayout.addSpacing(8)
        ua = self._preset.get("userAgent", "")
        if ua:
            display = ua if len(ua) <= 24 else ua[:21] + "..."
            self.descLayout.addWidget(
                IconBodyLabel(display, FluentIcon.PEOPLE, self, size=12))
        self.descLayout.addStretch(1)

        textLayout = QVBoxLayout()
        textLayout.setContentsMargins(0, 0, 0, 0)
        textLayout.setSpacing(2)
        textLayout.addWidget(self.nameLabel)
        textLayout.addLayout(self.descLayout)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(48, 12, 24, 12)
        layout.setSpacing(12)
        layout.addWidget(self.iconWidget)
        layout.addLayout(textLayout, 1)
        layout.addWidget(self.switchButton)
        layout.addWidget(self.editButton)
        layout.addWidget(self.removeButton)

    def _bind(self) -> None:
        self.editButton.clicked.connect(lambda: self.editRequested.emit(self._index))
        self.removeButton.clicked.connect(lambda: self.removeRequested.emit(self._index))
        self.switchButton.checkedChanged.connect(
            lambda checked: self._onToggled(checked))

    def _onToggled(self, checked: bool) -> None:
        self._refreshOpacity(checked)
        self.toggled.emit(self._index, checked)

    def _refreshOpacity(self, enabled: bool) -> None:
        self.nameLabel.setEnabled(enabled)
        for i in range(self.descLayout.count()):
            w = self.descLayout.itemAt(i).widget()
            if w:
                w.setEnabled(enabled)


class IdentitySettingCard(CollapsibleSettingCard):

    def __init__(self, parent=None):
        from qfluentwidgets import DropDownPushButton
        from app.view.components.option_cards import toProfileLabel

        super().__init__(FluentIcon.ROBOT, self.tr("模拟身份"),
                         self.tr("TLS 指纹与 User-Agent 预设"), parent=parent)
        self._rowWidgets: list[PresetRowWidget] = []

        from qfluentwidgets import IconWidget
        from app.view.components.labels import IconBodyLabel

        self.choiceLabel = BodyLabel(self)
        self.profileButton = DropDownPushButton(toProfileLabel(cfg.clientProfile.value), self.view)
        self.profileButton.setMinimumWidth(200)

        self.profileWidget = QWidget(self.view)
        self.profileLayout = QHBoxLayout(self.profileWidget)
        self.profileIcon = IconWidget(FluentIcon.ROBOT, self.profileWidget)
        self.profileIcon.setFixedSize(16, 16)
        self.profileTitleLabel = BodyLabel(self.tr("全局默认"), self.profileWidget)
        self.profileDescLabel = CaptionLabel(self.tr("未被预设匹配时使用"), self.profileWidget)

        self.buttonContainer = QWidget(self.view)
        self.buttonLayout = QHBoxLayout(self.buttonContainer)
        from qfluentwidgets import PrimaryPushButton
        self.addButton = PrimaryPushButton(FluentIcon.ADD, self.tr("添加预设"), self.buttonContainer)

        self._initWidget()
        self._initLayout()
        self._bind()
        self._reload()

    def _initWidget(self) -> None:
        from app.view.components.option_cards import buildProfileMenu

        self.profileButton.setMenu(
            buildProfileMenu(self, self._onPick, includeAuto=True)
        )
        self._refreshChoiceLabel()

    def _initLayout(self) -> None:
        self.addWidget(self.choiceLabel)

        profileTextLayout = QVBoxLayout()
        profileTextLayout.setContentsMargins(0, 0, 0, 0)
        profileTextLayout.setSpacing(2)
        profileTextLayout.addWidget(self.profileTitleLabel)
        profileTextLayout.addWidget(self.profileDescLabel)

        self.profileLayout.setContentsMargins(48, 12, 24, 12)
        self.profileLayout.setSpacing(12)
        self.profileLayout.addWidget(self.profileIcon)
        self.profileLayout.addLayout(profileTextLayout, 1)
        self.profileLayout.addWidget(self.profileButton)

        self.buttonLayout.setContentsMargins(48, 8, 24, 8)
        self.buttonLayout.addStretch(1)
        self.buttonLayout.addWidget(self.addButton)

        self.viewLayout.setSpacing(0)
        self.viewLayout.setContentsMargins(0, 0, 0, 0)
        self.addGroupWidget(self.profileWidget)

    def _bind(self) -> None:
        cfg.clientProfile.valueChanged.connect(self._onProfileChanged)
        self.addButton.clicked.connect(self._onAddClicked)

    def _onProfileChanged(self, value: str) -> None:
        from app.view.components.option_cards import toProfileLabel
        self.profileButton.setText(toProfileLabel(value))
        self._refreshChoiceLabel()

    def _onPick(self, value: str) -> None:
        cfg.set(cfg.clientProfile, value)

    def _refreshChoiceLabel(self) -> None:
        from app.view.components.option_cards import toProfileLabel
        self.choiceLabel.setText(toProfileLabel(cfg.clientProfile.value))

    def _reload(self) -> None:
        for row in self._rowWidgets:
            self.viewLayout.removeWidget(row)
            row.deleteLater()
        self._rowWidgets.clear()
        self.viewLayout.removeWidget(self.buttonContainer)

        for i, preset in enumerate(cfg.identityPresets.value):
            row = PresetRowWidget(i, preset, self.view)
            row.editRequested.connect(self._onEditClicked)
            row.removeRequested.connect(self._onRemoveClicked)
            row.toggled.connect(self._onToggled)
            self.viewLayout.addWidget(row)
            self._rowWidgets.append(row)

        self.viewLayout.addWidget(self.buttonContainer)
        self._refreshChoiceLabel()

    def _onAddClicked(self) -> None:
        from app.view.dialogs.preset_edit import PresetEditDialog
        dialog = PresetEditDialog(self.window())
        if dialog.exec():
            presets = list(cfg.identityPresets.value)
            presets.append(dialog.preset())
            cfg.set(cfg.identityPresets, presets)
            self._reload()
            if not self.isExpand:
                self.setExpand(True)

    def _onEditClicked(self, index: int) -> None:
        presets = list(cfg.identityPresets.value)
        if index < 0 or index >= len(presets):
            return
        from app.view.dialogs.preset_edit import PresetEditDialog
        dialog = PresetEditDialog(self.window(), preset=presets[index])
        if dialog.exec():
            presets[index] = dialog.preset()
            cfg.set(cfg.identityPresets, presets)
            self._reload()

    def _onToggled(self, index: int, checked: bool) -> None:
        presets = list(cfg.identityPresets.value)
        if index < 0 or index >= len(presets):
            return
        presets[index] = {**presets[index], "isEnabled": checked}
        cfg.set(cfg.identityPresets, presets)

    def _onRemoveClicked(self, index: int) -> None:
        from qfluentwidgets import MessageBox
        presets = list(cfg.identityPresets.value)
        if index < 0 or index >= len(presets):
            return
        name = presets[index].get("name", self.tr("未命名预设"))
        dialog = MessageBox(
            self.tr("删除预设"),
            self.tr("确定要删除 {0} 吗？").format(name),
            self.window(),
        )
        if not dialog.exec():
            return
        row = self._rowWidgets.pop(index)
        self.viewLayout.removeWidget(row)
        row.deleteLater()
        for i in range(index, len(self._rowWidgets)):
            self._rowWidgets[i]._index = i
        presets.pop(index)
        cfg.set(cfg.identityPresets, presets)
        self._refreshChoiceLabel()


class HeadersPresetRow(QWidget):

    def __init__(self, index: int, preset: dict, parent=None, *,
                 isCurrent: bool, canRemove: bool, onPick, onEdit, onRemove):
        from qfluentwidgets import PrimaryToolButton
        super().__init__(parent)
        self._index = index
        self._onPick = onPick
        self._onEdit = onEdit
        self._onRemove = onRemove

        self.radioButton = RadioButton(preset["name"], self)
        self.countLabel = CaptionLabel(
            self.tr("{0} 条标头").format(len(preset["headers"])), self)
        self.editButton = PrimaryToolButton(FluentIcon.EDIT, self)
        self.removeButton = ToolButton(FluentIcon.DELETE, self)

        self._initWidget(isCurrent, canRemove)
        self._initLayout()
        self._bind()

    def _initWidget(self, isCurrent: bool, canRemove: bool) -> None:
        self.radioButton.setChecked(isCurrent)
        self.editButton.setToolTip(self.tr("编辑"))
        self.editButton.installEventFilter(ToolTipFilter(self.editButton))
        self.removeButton.setToolTip(self.tr("删除"))
        self.removeButton.installEventFilter(ToolTipFilter(self.removeButton))
        self.removeButton.setEnabled(canRemove)

    def _initLayout(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(48, 12, 24, 12)
        layout.setSpacing(12)
        layout.addWidget(self.radioButton)
        layout.addStretch(1)
        layout.addWidget(self.countLabel)
        layout.addWidget(self.editButton)
        layout.addWidget(self.removeButton)

    def _bind(self) -> None:
        self.radioButton.clicked.connect(lambda: self._onPick(self._index))
        self.editButton.clicked.connect(lambda: self._onEdit(self._index))
        self.removeButton.clicked.connect(lambda: self._onRemove(self._index))


class HeadersPresetSettingCard(CollapsibleSettingCard):

    def __init__(self, parent=None):
        super().__init__(FluentIcon.DICTIONARY, self.tr("请求标头预设"),
                         self.tr("新建任务的标头起点"), parent=parent)
        self._rowWidgets: list[HeadersPresetRow] = []

        self.choiceLabel = BodyLabel(self)
        self.buttonContainer = QWidget(self.view)
        self.buttonLayout = QHBoxLayout(self.buttonContainer)
        self.addButton = PrimaryPushButton(
            FluentIcon.ADD, self.tr("添加预设"), self.buttonContainer)

        self._initLayout()
        self._bind()
        self._reload()

    def _initLayout(self) -> None:
        self.addWidget(self.choiceLabel)

        self.buttonLayout.setContentsMargins(48, 8, 24, 8)
        self.buttonLayout.addStretch(1)
        self.buttonLayout.addWidget(self.addButton)

        self.viewLayout.setSpacing(0)
        self.viewLayout.setContentsMargins(0, 0, 0, 0)

    def _bind(self) -> None:
        self.addButton.clicked.connect(self._onAddClicked)

    def _reload(self) -> None:
        for row in self._rowWidgets:
            self.viewLayout.removeWidget(row)
            row.deleteLater()
        self._rowWidgets.clear()
        self.viewLayout.removeWidget(self.buttonContainer)

        presets = cfg.headersPresets.value
        current = currentHeadersPresetIndex()
        for i, preset in enumerate(presets):
            row = HeadersPresetRow(
                i, preset, self.view,
                isCurrent=i == current, canRemove=len(presets) > 1,
                onPick=self._onPick, onEdit=self._onEditClicked,
                onRemove=self._onRemoveClicked,
            )
            self.viewLayout.addWidget(row)
            self._rowWidgets.append(row)

        self.viewLayout.addWidget(self.buttonContainer)
        self.choiceLabel.setText(presets[current]["name"])

    def _onPick(self, index: int) -> None:
        cfg.set(cfg.currentHeadersPreset, index)
        self._reload()

    def _onAddClicked(self) -> None:
        from app.view.dialogs.headers_preset_edit import HeadersPresetEditDialog
        dialog = HeadersPresetEditDialog(
            self.window(), preset={"name": "", "headers": currentHeaders()})
        if dialog.exec():
            cfg.set(cfg.headersPresets, [*cfg.headersPresets.value, dialog.preset()])
            self._reload()
            if not self.isExpand:
                self.setExpand(True)

    def _onEditClicked(self, index: int) -> None:
        from app.view.dialogs.headers_preset_edit import HeadersPresetEditDialog
        presets = list(cfg.headersPresets.value)
        dialog = HeadersPresetEditDialog(self.window(), preset=presets[index])
        if dialog.exec():
            presets[index] = dialog.preset()
            cfg.set(cfg.headersPresets, presets)
            self._reload()

    def _onRemoveClicked(self, index: int) -> None:
        from qfluentwidgets import MessageBox
        presets = list(cfg.headersPresets.value)
        name = presets[index].get("name", self.tr("未命名预设"))
        dialog = MessageBox(
            self.tr("删除预设"),
            self.tr("确定要删除 {0} 吗？").format(name),
            self.window(),
        )
        if not dialog.exec():
            return
        row = self._rowWidgets.pop(index)
        self.viewLayout.removeWidget(row)
        row.deleteLater()
        for i in range(index, len(self._rowWidgets)):
            self._rowWidgets[i]._index = i
        presets.pop(index)
        cfg.set(cfg.headersPresets, presets)
        current = cfg.currentHeadersPreset.value
        if index <= current:
            cfg.set(cfg.currentHeadersPreset, max(0, current - 1))
        newCurrent = currentHeadersPresetIndex()
        canRemove = len(self._rowWidgets) > 1
        for i, r in enumerate(self._rowWidgets):
            r.radioButton.setChecked(i == newCurrent)
            r.removeButton.setEnabled(canRemove)
        self.choiceLabel.setText(presets[newCurrent]["name"])


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

    def __init__(self, runtimeStatusService, runtime, parent=None):
        from app.models.pack import BinaryRuntime

        self._runtimeStatusService = runtimeStatusService
        self._runtime: BinaryRuntime = runtime
        super().__init__(FluentIcon.INFO, runtime.name, self.tr("正在检测运行时..."), parent)

        self.installButton = PrimaryPushButton(self.tr("一键安装"), self)
        self.cancelButton = ToolButton(FluentIcon.CLOSE, self)
        self.refreshButton = ToolButton(FluentIcon.SYNC, self)
        self.deleteButton = ToolButton(FluentIcon.DELETE, self)

        self._initWidget()
        self._initLayout()
        self._bind()
        self.updateStatus(self._runtimeStatusService.status(runtime))

    def _initWidget(self) -> None:
        if not self._runtime.canInstall:
            self.installButton.hide()
        self.cancelButton.hide()
        self.cancelButton.setToolTip(self.tr("取消安装"))
        self.cancelButton.installEventFilter(ToolTipFilter(self.cancelButton))
        self.deleteButton.hide()
        self.deleteButton.setToolTip(self.tr("卸载"))
        self.deleteButton.installEventFilter(ToolTipFilter(self.deleteButton))
        self.refreshButton.setToolTip(self.tr("刷新"))
        self.refreshButton.installEventFilter(ToolTipFilter(self.refreshButton))

    def _initLayout(self) -> None:
        self._buttonLayout = QHBoxLayout()
        self._buttonLayout.setContentsMargins(0, 0, 0, 0)
        self._buttonLayout.setSpacing(8)
        self._buttonLayout.addWidget(self.installButton)
        self._buttonLayout.addWidget(self.cancelButton)
        self._buttonLayout.addWidget(self.refreshButton)
        self._buttonLayout.addWidget(self.deleteButton)
        self.hBoxLayout.addLayout(self._buttonLayout)
        self.hBoxLayout.addSpacing(16)

    def _bind(self) -> None:
        self._runtimeStatusService.statusChanged.connect(self._onRuntimeStatusChanged)
        self.installButton.clicked.connect(self._onInstallClicked)
        self.cancelButton.clicked.connect(self._onCancelClicked)
        self.deleteButton.clicked.connect(self._onDeleteClicked)
        self.refreshButton.clicked.connect(self._onRefreshClicked)

    def refreshStatus(self) -> None:
        self._runtimeStatusService.refreshStatus(self._runtime)

    def updateStatus(self, status) -> None:
        from app.update import isNewer

        self.refreshButton.setEnabled(not status.isBusy and not status.isInstalling)
        isInstalled = bool(status.path)
        isManaged = self._runtime.isAppManaged()
        isUpdateAvailable = (
            isInstalled and isManaged
            and status.latestVersion
            and (not status.version or isNewer(status.version, status.latestVersion))
        )

        if status.isInstalling:
            if status.progress > 0:
                self.setContent(self.tr("正在安装... {0}%").format(f"{status.progress:.0f}"))
            else:
                self.setContent(self.tr("正在安装..."))
            self.installButton.hide()
            self.cancelButton.setVisible(self._runtime.canInstall)
            self.deleteButton.hide()
            return

        if status.isBusy:
            self.setContent(self.tr("正在检测运行时..."))
            self.installButton.hide()
            self.cancelButton.hide()
            self.deleteButton.hide()
            return

        self.cancelButton.hide()

        if status.error:
            self.setContent(status.error)
        elif isInstalled:
            versionDisplay = status.version
            if status.detail:
                versionDisplay = f"{versionDisplay} | {status.detail}" if versionDisplay else status.detail
            if versionDisplay and status.latestVersion:
                line1 = self.tr("版本: {0}（最新: {1}）").format(versionDisplay, status.latestVersion)
            elif versionDisplay:
                line1 = self.tr("版本: {0}").format(versionDisplay)
            elif status.latestVersion:
                line1 = self.tr("最新版本: {0}").format(status.latestVersion)
            else:
                line1 = ""
            line2 = self.tr("路径: {0}").format(status.path)
            self.setContent(f"{line1}\n{line2}" if line1 else line2)
        else:
            self.setContent(self.tr("未检测到可用的 {0}").format(status.name))

        if isUpdateAvailable:
            self.installButton.setText(self.tr("更新到 {0}").format(status.latestVersion))
            self.installButton.setVisible(True)
        elif not isInstalled or not isManaged:
            self.installButton.setText(self.tr("一键安装"))
            self.installButton.setVisible(self._runtime.canInstall)
        else:
            self.installButton.hide()

        self.deleteButton.setVisible(isInstalled and isManaged)

    def _onRefreshClicked(self, *_args) -> None:
        self._runtimeStatusService.invalidate(self._runtime)

    def _onInstallFolderChanged(self, *_args) -> None:
        self.refreshStatus()

    def _onRuntimeStatusChanged(self, status) -> None:
        if status.runtimeId == self._runtime.runtimeId:
            self.updateStatus(status)

    def _onInstallClicked(self) -> None:
        self._runtimeStatusService.install(self._runtime)

    def _onCancelClicked(self) -> None:
        self._runtimeStatusService.cancelInstall(self._runtime)

    def _onDeleteClicked(self) -> None:
        from qfluentwidgets import MessageBox

        dialog = MessageBox(
            self.tr("确认卸载"),
            self.tr("确定要卸载 {0} 吗？").format(self._runtime.name),
            self.window(),
        )
        if not dialog.exec():
            return
        try:
            self._runtime.delete()
        except Exception as e:
            InfoBar.error(
                self.tr("卸载失败"), str(e),
                duration=-1, position=InfoBarPosition.TOP, parent=self.window(),
            )
            return
        self._runtimeStatusService.invalidate(self._runtime)
