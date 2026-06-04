from typing import Final
from urllib.parse import urlsplit

from PySide6.QtCore import Qt, Signal, QEvent
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QButtonGroup,
    QHBoxLayout,
    QSpacerItem,
    QSizePolicy,
    QFileDialog,
)
from qfluentwidgets import (
    SettingCard,
    RangeConfigItem,
    SpinBox,
    ExpandGroupSettingCard,
    ConfigItem,
    FluentIcon,
    BodyLabel,
    RadioButton,
    ComboBox,
    LineEdit,
    ToolButton,
    ToolTipFilter,
)

from app.supports.config import cfg
from app.supports.utils import getProxies
from app.view.components.editors import AutoSizingComboBox


class SpinBoxSettingCard(SettingCard):
    """支持自定义倍数的 SpinBox 设置卡片"""

    def __init__(
        self,
        icon,
        title,
        content=None,
        suffix: str = None,
        configItem: RangeConfigItem = None,
        parent=None,
        singleStep: int = 50,
        division: float = 1,
        blockWheelEvent: bool = True,
    ):
        super().__init__(icon, title, content, parent)
        self.division = division
        self.configItem = configItem

        self.spinBox = SpinBox(self)
        self.spinBox.setObjectName("spinBox")
        self.spinBox.setSingleStep(singleStep)
        self.spinBox.setMinimumWidth(180)
        self.spinBox.setSuffix(suffix)
        if blockWheelEvent:
            self.spinBox.installEventFilter(self)

        if configItem:
            _ = configItem.range
            self.spinBox.setRange(_[0] * division, _[1] * division)

        self.hBoxLayout.addWidget(self.spinBox)
        self.hBoxLayout.addSpacing(24)

        self.spinBox.setValue(self.configItem.value * division)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Wheel:
            return True
        return super().eventFilter(watched, event)

    def leaveEvent(self, event):
        if self.configItem:
            cfg.set(self.configItem, self.spinBox.value() / self.division)


class LineEditSettingCard(SettingCard):
    """绑定字符串 ConfigItem 的行编辑设置卡"""

    def __init__(
        self,
        icon,
        title,
        content=None,
        configItem: ConfigItem = None,
        parent=None,
        placeholder: str = "",
    ):
        super().__init__(icon, title, content, parent)
        self.configItem = configItem

        self.lineEdit = LineEdit(self)

        self._initWidget(placeholder)
        self._initLayout()
        self._bind()

    def _initWidget(self, placeholder: str):
        self.lineEdit.setMinimumWidth(180)
        self.lineEdit.setClearButtonEnabled(True)
        self.lineEdit.setPlaceholderText(placeholder)
        if self.configItem:
            self.lineEdit.setText(self.configItem.value)

    def _initLayout(self):
        self.hBoxLayout.addWidget(self.lineEdit)
        self.hBoxLayout.addSpacing(16)

    def _bind(self):
        self.lineEdit.editingFinished.connect(self._onEditingFinished)

    def _onEditingFinished(self):
        if self.configItem:
            cfg.set(self.configItem, self.lineEdit.text())


class ProxySettingCard(ExpandGroupSettingCard):
    """Custom proxyServer setting card"""

    def __init__(self, configItem: ConfigItem, parent=None):
        """
        Parameters
        ----------
        configItem: ColorConfigItem
            options config item

        parent: QWidget
            parent window
        """
        super().__init__(
            FluentIcon.GLOBE,
            self.tr("代理"),
            self.tr("设置下载时希望使用的代理"),
            parent=parent,
        )

        self.configItem = configItem

        self.choiceLabel = BodyLabel(self)
        self.radioWidget = QWidget(self.view)
        self.radioLayout = QVBoxLayout(self.radioWidget)

        self.buttonGroup = QButtonGroup(self)
        self.offRadioButton = RadioButton(self.tr("不使用代理"), self.radioWidget)
        self.defaultRadioButton = RadioButton(
            self.tr("自动检测系统代理"), self.radioWidget
        )
        self.customRadioButton = RadioButton(
            self.tr("使用自定义代理"), self.radioWidget
        )

        self.customProxyWidget = QWidget(self.view)
        self.customProxyLayout = QHBoxLayout(self.customProxyWidget)
        self.customLabel = BodyLabel(
            self.tr("编辑代理服务器: "), self.customProxyWidget
        )
        self.customProtocolComboBox = ComboBox(self.customProxyWidget)
        self.customProtocolComboBox.addItems(["socks4", "socks5", "http", "https"])
        self.label_1 = BodyLabel("://", self.customProxyWidget)
        self.customIPLineEdit = LineEdit(self.customProxyWidget)
        self.customIPLineEdit.setPlaceholderText(self.tr("代理 IP 地址"))
        self.label_2 = BodyLabel(":", self.customProxyWidget)
        self.customPortLineEdit = LineEdit(self.customProxyWidget)
        self.customPortLineEdit.setPlaceholderText(self.tr("端口"))

        # 代理账号和密码
        self.credentialsWidget = QWidget(self.view)
        self.credentialsLayout = QHBoxLayout(self.credentialsWidget)
        self.credentialsLabel = BodyLabel(self.tr("认证信息: "), self.credentialsWidget)
        self.usernameLineEdit = LineEdit(self.credentialsWidget)
        self.usernameLineEdit.setPlaceholderText(self.tr("用户名（可选）"))
        self.label_3 = BodyLabel(" : ", self.credentialsWidget)
        self.passwordLineEdit = LineEdit(self.credentialsWidget)
        self.passwordLineEdit.setPlaceholderText(self.tr("密码（可选）"))
        self.passwordLineEdit.setEchoMode(LineEdit.EchoMode.Password)

        self.__initWidget()
        configValue = self.configItem.value

        if configValue == "Auto":
            self.defaultRadioButton.setChecked(True)
            self.__onRadioButtonClicked(self.defaultRadioButton)
        elif configValue == "Off":
            self.offRadioButton.setChecked(True)
            self.__onRadioButtonClicked(self.offRadioButton)
        else:
            self.customRadioButton.setChecked(True)
            self.__onRadioButtonClicked(self.customRadioButton)
            self._applyProxyUrl(configValue)

            self.choiceLabel.setText(self.buttonGroup.checkedButton().text())
            self.choiceLabel.adjustSize()

    def _applyProxyUrl(self, proxyUrl: str | None):
        if not proxyUrl:
            self.customProtocolComboBox.setCurrentText("")
            self.customIPLineEdit.setText(self.tr("未检测到代理"))
            self.customPortLineEdit.setText("")
            self.usernameLineEdit.setText("")
            self.passwordLineEdit.setText("")
            return

        parsed = urlsplit(proxyUrl)
        self.customProtocolComboBox.setCurrentText(parsed.scheme)
        self.customIPLineEdit.setText(parsed.hostname or "")
        self.customPortLineEdit.setText(str(parsed.port or ""))
        self.usernameLineEdit.setText(parsed.username or "")
        self.passwordLineEdit.setText(parsed.password or "")

    def __initWidget(self):
        self.__initLayout()
        self.buttonGroup.buttonClicked.connect(self.__onRadioButtonClicked)

    def __initLayout(self):
        self.addWidget(self.choiceLabel)

        self.radioLayout.setSpacing(19)
        self.radioLayout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.radioLayout.setContentsMargins(48, 5, 0, 18)

        self.buttonGroup.addButton(self.offRadioButton)
        self.buttonGroup.addButton(self.defaultRadioButton)
        self.buttonGroup.addButton(self.customRadioButton)

        self.radioLayout.addWidget(self.offRadioButton)
        self.radioLayout.addWidget(self.defaultRadioButton)
        self.radioLayout.addWidget(self.customRadioButton)
        self.radioLayout.setSizeConstraint(QVBoxLayout.SizeConstraint.SetMinimumSize)

        self.customProxyLayout.setContentsMargins(48, 5, 44, 10)
        self.customProxyLayout.addWidget(
            self.customLabel, 0, Qt.AlignmentFlag.AlignLeft
        )
        self.customProxyLayout.addSpacerItem(
            QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        )
        self.customProxyLayout.addWidget(
            self.customProtocolComboBox, 0, Qt.AlignmentFlag.AlignLeft
        )
        self.customProxyLayout.addWidget(self.label_1, 0, Qt.AlignmentFlag.AlignLeft)
        self.customProxyLayout.addWidget(
            self.customIPLineEdit, 0, Qt.AlignmentFlag.AlignLeft
        )
        self.customProxyLayout.addWidget(self.label_2, 0, Qt.AlignmentFlag.AlignLeft)
        self.customProxyLayout.addWidget(
            self.customPortLineEdit, 0, Qt.AlignmentFlag.AlignLeft
        )
        self.customProxyLayout.setSizeConstraint(
            QHBoxLayout.SizeConstraint.SetMinimumSize
        )

        self.credentialsLayout.setContentsMargins(48, 5, 44, 18)
        self.credentialsLayout.addWidget(
            self.credentialsLabel, 0, Qt.AlignmentFlag.AlignLeft
        )
        self.credentialsLayout.addSpacerItem(
            QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        )
        self.credentialsLayout.addWidget(
            self.usernameLineEdit, 0, Qt.AlignmentFlag.AlignLeft
        )
        self.credentialsLayout.addWidget(self.label_3, 0, Qt.AlignmentFlag.AlignLeft)
        self.credentialsLayout.addWidget(
            self.passwordLineEdit, 0, Qt.AlignmentFlag.AlignLeft
        )
        self.credentialsLayout.setSizeConstraint(
            QHBoxLayout.SizeConstraint.SetMinimumSize
        )

        self.viewLayout.setSpacing(0)
        self.viewLayout.setContentsMargins(0, 0, 0, 0)
        self.addGroupWidget(self.radioWidget)
        self.addGroupWidget(self.customProxyWidget)
        self.addGroupWidget(self.credentialsWidget)

    def __onRadioButtonClicked(self, button: RadioButton):
        """radio button clicked slot"""
        if button.text() == self.choiceLabel.text():
            return

        self.choiceLabel.setText(button.text())
        self.choiceLabel.adjustSize()

        if button is self.defaultRadioButton:  # 自动
            # 禁用 Custom 编辑器
            self.customProxyWidget.setDisabled(True)
            self.credentialsWidget.setDisabled(True)

            cfg.set(self.configItem, "Auto")
            proxies = getProxies()
            self._applyProxyUrl(
                next(
                    (
                        proxies.get(protocol)
                        for protocol in ("https", "http", "ftp")
                        if proxies and proxies.get(protocol)
                    ),
                    None,
                )
            )

        elif button is self.offRadioButton:  # 关闭
            # 禁用 Custom 编辑器
            self.customProxyWidget.setDisabled(True)
            self.credentialsWidget.setDisabled(True)

            cfg.set(self.configItem, "Off")

        elif button is self.customRadioButton:
            # 启用 Custom 编辑器
            self.customProxyWidget.setDisabled(False)
            self.credentialsWidget.setDisabled(False)

    def leaveEvent(self, event):  # 鼠标离开时检测 Custom 选项是否合法并保存配置
        if self.customRadioButton.isChecked():
            protocol = self.customProtocolComboBox.currentText()
            ip = self.customIPLineEdit.text()
            port = self.customPortLineEdit.text()
            username = self.usernameLineEdit.text()
            password = self.passwordLineEdit.text()

            # 构建代理字符串：protocol://[username:password@]ip:port
            if username or password:
                credentials = f"{username}:{password}@"
            else:
                credentials = ""

            proxyServer = f"{protocol}://{credentials}{ip}:{port}"
            if cfg.proxyServer.validator.validate(proxyServer):
                cfg.set(self.configItem, proxyServer)
            else:
                self.defaultRadioButton.click()
                self.defaultRadioButton.setChecked(True)


class InstallFolderCard(SettingCard):
    pathChanged = Signal(str)

    def __init__(self, configItem: ConfigItem, defaultPath: str,
                 title: str, browseTitle: str, parent=None):
        super().__init__(FluentIcon.FOLDER, title, configItem.value, parent)
        self.configItem = configItem
        self.defaultPath = defaultPath
        self.browseTitle = browseTitle
        self.chooseFolderButton = ToolButton(FluentIcon.FOLDER, self)
        self.restoreDefaultButton = ToolButton(FluentIcon.CANCEL, self)

        self._initWidget()
        self._initLayout()
        self._bind()

    def _initWidget(self):
        self.chooseFolderButton.setToolTip(self.tr("浏览文件夹"))
        self.chooseFolderButton.installEventFilter(ToolTipFilter(self.chooseFolderButton))
        self.restoreDefaultButton.setToolTip(self.tr("恢复默认路径"))
        self.restoreDefaultButton.installEventFilter(ToolTipFilter(self.restoreDefaultButton))

    def _initLayout(self):
        self.hBoxLayout.addWidget(self.chooseFolderButton, 0, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.addSpacing(8)
        self.hBoxLayout.addWidget(self.restoreDefaultButton, 0, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.addSpacing(16)

    def _bind(self):
        self.chooseFolderButton.clicked.connect(self._chooseFolder)
        self.restoreDefaultButton.clicked.connect(self._restoreDefault)

    def _updatePath(self, path: str):
        cfg.set(self.configItem, path)
        self.setContent(self.configItem.value)
        self.pathChanged.emit(self.configItem.value)

    def _chooseFolder(self):
        folder = QFileDialog.getExistingDirectory(self.window(), self.browseTitle)
        if folder:
            self._updatePath(folder)

    def _restoreDefault(self):
        self._updatePath(self.defaultPath)


class SelectFileCard(SettingCard):
    pathChanged = Signal(str)

    def __init__(self, configItem: ConfigItem, icon, title: str, hint: str,
                 browseTitle: str, parent=None):
        super().__init__(icon, title, configItem.value or hint, parent)
        self.configItem = configItem
        self.hint = hint
        self.browseTitle = browseTitle
        self.chooseFileButton = ToolButton(FluentIcon.FOLDER, self)
        self.clearButton = ToolButton(FluentIcon.CANCEL, self)

        self._initWidget()
        self._initLayout()
        self._bind()

    def _initWidget(self):
        self.chooseFileButton.setToolTip(self.tr("选择文件"))
        self.chooseFileButton.installEventFilter(ToolTipFilter(self.chooseFileButton))
        self.clearButton.setToolTip(self.tr("清除路径"))
        self.clearButton.installEventFilter(ToolTipFilter(self.clearButton))

    def _initLayout(self):
        self.hBoxLayout.addWidget(self.chooseFileButton, 0, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.addSpacing(8)
        self.hBoxLayout.addWidget(self.clearButton, 0, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.addSpacing(16)

    def _bind(self):
        self.chooseFileButton.clicked.connect(self._onChooseFile)
        self.clearButton.clicked.connect(lambda: self._updatePath(""))

    def _onChooseFile(self):
        path, _ = QFileDialog.getOpenFileName(self.window(), self.browseTitle)
        if path:
            self._updatePath(path)

    def _updatePath(self, path: str):
        cfg.set(self.configItem, path)
        self.setContent(path or self.hint)
        self.pathChanged.emit(path)


_MAX_HISTORY: Final[int] = 7


class SelectFolderSettingCard(SettingCard):
    pathChanged = Signal(str)

    def __init__(
        self,
        initialPath: str,
        historyConfig: ConfigItem,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            FluentIcon.DOWNLOAD, self.tr("下载路径"), cfg.downloadFolder.value, parent
        )
        self._initialPath = initialPath
        self._historyConfig = historyConfig
        self._history: list[str] = list(
            dict.fromkeys(p for p in historyConfig.value if p)
        )
        if self._history != historyConfig.value:
            cfg.set(historyConfig, self._history)

        self.pathComboBox = AutoSizingComboBox(self)
        self.chooseFolderButton = ToolButton(FluentIcon.FOLDER, self)
        self.restoreDefaultButton = ToolButton(FluentIcon.CANCEL, self)

        self._initWidget()
        self._initLayout()
        self._bind()

    def _initWidget(self) -> None:
        # ReadOnly 避免编辑中间态触发 currentTextChanged 把变体写入历史
        self.pathComboBox.setReadOnly(True)
        self.chooseFolderButton.setToolTip(self.tr("浏览文件夹"))
        self.restoreDefaultButton.setToolTip(self.tr("恢复默认路径"))
        # initialPath 可能也存在于 history（用户曾把当前路径加入过），用 dict 去重
        items = list(dict.fromkeys(p for p in [self._initialPath, *self._history] if p))
        self.pathComboBox.addItems(items)
        self.pathComboBox.setCurrentText(cfg.downloadFolder.value)

    def _initLayout(self) -> None:
        self.hBoxLayout.addWidget(self.pathComboBox)
        self.hBoxLayout.addSpacing(5)
        self.hBoxLayout.addWidget(self.chooseFolderButton)
        self.hBoxLayout.addSpacing(5)
        self.hBoxLayout.addWidget(self.restoreDefaultButton)
        self.hBoxLayout.addSpacing(16)

    def _bind(self) -> None:
        # textActivated 只在用户主动选中时触发，setCurrentText 等程序操作不触发——无递归隐患
        self.pathComboBox.textActivated.connect(self._setPath)
        self.chooseFolderButton.clicked.connect(self._onChooseFolderClicked)
        self.restoreDefaultButton.clicked.connect(self._onRestoreDefaultClicked)

    def _onChooseFolderClicked(self) -> None:
        folder = QFileDialog.getExistingDirectory(None, self.tr("选择文件夹"))
        if folder:
            self._setPath(folder)

    def _onRestoreDefaultClicked(self) -> None:
        self._setPath(self._initialPath)

    def _setPath(self, path: str) -> None:
        if not path:
            return
        if path not in self._history:
            self._history.append(path)
            if len(self._history) > _MAX_HISTORY:
                evicted = self._history.pop(0)
                self.pathComboBox.removeItem(self.pathComboBox.findText(evicted))
            cfg.set(self._historyConfig, self._history)
            if self.pathComboBox.findText(path) == -1:
                self.pathComboBox.addItem(path)
        self.pathComboBox.setCurrentText(path)
        self.setContent(path)
        self.pathChanged.emit(path)
